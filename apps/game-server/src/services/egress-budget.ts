/**
 * Supabase Egress Budget Tracker
 *
 * Tracks estimated Supabase egress per billing period (calendar month).
 * When the budget is exceeded, `isOverBudget()` returns true and ALL
 * Supabase queries are hard-stopped (auth excluded).
 *
 * The tracker persists state to a local JSON file so it survives restarts.
 * It uses conservative byte estimates per query type — the goal is a
 * rough guardrail, not precise metering.
 *
 * Configure via env vars:
 *   SUPABASE_EGRESS_BUDGET_GB  — monthly budget in GB (default: 125 = 50% of Pro plan)
 */

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TRACKER_PATH = join(__dirname, "..", "..", ".egress-tracker.json");

const BUDGET_GB = parseFloat(process.env.SUPABASE_EGRESS_BUDGET_GB ?? "125");
const BUDGET_BYTES = BUDGET_GB * 1024 * 1024 * 1024;

interface TrackerState {
  month: string;           // "2026-02"
  estimatedBytes: number;
  queryCount: number;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function loadState(): TrackerState {
  try {
    const raw = readFileSync(TRACKER_PATH, "utf-8");
    const state = JSON.parse(raw) as TrackerState;
    if (state.month === currentMonth()) return state;
  } catch {
    // file missing or corrupt — start fresh
  }
  return { month: currentMonth(), estimatedBytes: 0, queryCount: 0 };
}

let state = loadState();
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let overBudget = state.estimatedBytes >= BUDGET_BYTES;
let loggedOverBudget = false;

function scheduleSave(): void {
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = null;
    try {
      mkdirSync(dirname(TRACKER_PATH), { recursive: true });
      writeFileSync(TRACKER_PATH, JSON.stringify(state, null, 2));
    } catch {
      // non-critical — best effort persistence
    }
  }, 5_000);
}

/**
 * Record estimated egress bytes from a Supabase query.
 * Call this after every Supabase read that returns data.
 */
export function recordEgress(estimatedBytes: number): void {
  // Auto-reset on month rollover
  const month = currentMonth();
  if (state.month !== month) {
    state = { month, estimatedBytes: 0, queryCount: 0 };
    overBudget = false;
    loggedOverBudget = false;
  }

  state.estimatedBytes += estimatedBytes;
  state.queryCount++;
  scheduleSave();

  if (!overBudget && state.estimatedBytes >= BUDGET_BYTES) {
    overBudget = true;
    const usedGB = (state.estimatedBytes / (1024 ** 3)).toFixed(2);
    console.error(
      `[egress-budget] BUDGET EXCEEDED: estimated ${usedGB} GB / ${BUDGET_GB} GB ` +
      `(${state.queryCount} queries this month). ALL Supabase queries are now disabled (auth excluded).`,
    );
  }
}

/**
 * Returns true if the estimated egress budget is exceeded.
 * Callers should skip non-essential Supabase queries when this returns true.
 */
export function isOverBudget(): boolean {
  // Log once per startup when already over budget
  if (overBudget && !loggedOverBudget) {
    const usedGB = (state.estimatedBytes / (1024 ** 3)).toFixed(2);
    console.warn(
      `[egress-budget] Already over budget on startup: ${usedGB} GB / ${BUDGET_GB} GB. ` +
      `Non-essential Supabase queries are disabled. Delete ${TRACKER_PATH} to reset.`,
    );
    loggedOverBudget = true;
  }
  return overBudget;
}

/** Current usage stats for diagnostics. */
export function getEgressStats(): { month: string; estimatedGB: string; budgetGB: number; queryCount: number; overBudget: boolean } {
  return {
    month: state.month,
    estimatedGB: (state.estimatedBytes / (1024 ** 3)).toFixed(3),
    budgetGB: BUDGET_GB,
    queryCount: state.queryCount,
    overBudget,
  };
}
