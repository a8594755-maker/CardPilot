import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { RoomSettings } from "@cardpilot/shared-types";

const ENV_FILES_BY_PRIORITY = [
  ".env",
  ".env.local",
  "apps/game-server/.env",
  "apps/game-server/.env.local",
] as const;

const ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
const ROOM_CODE_LENGTH = 6;

const ROOM_LIMITS = {
  minPlayers: 2,
  maxPlayers: 9,
} as const;

const DEFAULT_SMALL_BLIND = 50;
const DEFAULT_BIG_BLIND = 100;
const DEFAULT_BUY_IN_MIN = 2_000;
const DEFAULT_BUY_IN_MAX = 20_000;

const DEFAULTS: RoomSettings = {
  gameType: "texas",
  maxPlayers: 6,
  spectatorAllowed: true,
  smallBlind: DEFAULT_SMALL_BLIND,
  bigBlind: DEFAULT_BIG_BLIND,
  ante: 0,
  blindStructure: null,
  buyInMin: DEFAULT_BUY_IN_MIN,
  buyInMax: DEFAULT_BUY_IN_MAX,
  rebuyAllowed: true,
  addOnAllowed: false,
  straddleAllowed: false,
  runItTwice: false,
  runItTwiceMode: "off",
  visibility: "public",
  password: null,
  hostStartRequired: false,
  actionTimerSeconds: 15,
  timeBankSeconds: 60,
  timeBankRefillPerHand: 5,
  timeBankHandsToFill: 10,
  thinkExtensionSecondsPerUse: 10,
  thinkExtensionQuotaPerHour: 3,
  disconnectGracePeriod: 30,
  maxConsecutiveTimeouts: 3,
  useCentsValues: false,
  rabbitHunting: false,
  autoStartNextHand: true,
  showdownSpeed: "normal",
  dealToAwayPlayers: false,
  revealAllAtShowdown: true,
  autoRevealOnAllInCall: true,
  autoRevealWinningHands: true,
  autoMuckLosingHands: true,
  allowShowAfterFold: false,
  allowShowCalledHandRequest: false,
  bombPotEnabled: false,
  bombPotFrequency: 0,
  doubleBoardMode: "off",
  sevenTwoBounty: 0,
  simulatedFeeEnabled: false,
  simulatedFeePercent: 5,
  simulatedFeeCap: 0,
  allowGuestChat: true,
  autoTrimExcessBets: true,
  roomFundsTracking: false,
};

export type RuntimeConfig = {
  version: string;
  envName: string;
  port: number;
  corsOrigin: string[] | true;
  handIdleTimeoutMs: number;
  showdownDecisionTimeoutMs: number;
  runCountDecisionTimeoutMs: number;
  roomEmptyTtlMs: number;
  roomCodeLength: number;
  roomCodeAlphabet: string;
  minPlayers: number;
  maxPlayers: number;
  defaultRoomName: string;
  defaultRoomSettings: RoomSettings;
  defaultCreateRoom: {
    maxPlayers: number;
    smallBlind: number;
    bigBlind: number;
    buyInMinMultiplierBb: number;
    buyInMaxMultiplierBb: number;
  };
};

let loaded = false;
let cachedConfig: RuntimeConfig | null = null;

function loadEnvFilesOnce(): void {
  if (loaded) return;

  const cwd = process.cwd();
  const candidateRoots = [cwd, resolve(cwd, "../..")];

  for (const root of candidateRoots) {
    for (const relPath of ENV_FILES_BY_PRIORITY) {
      const fullPath = resolve(root, relPath);
      if (!existsSync(fullPath)) continue;
      parseDotEnv(readFileSync(fullPath, "utf-8"));
    }
  }

  loaded = true;
}

function parseDotEnv(content: string): void {
  for (const rawLine of content.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const idx = line.indexOf("=");
    if (idx < 1) continue;
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    if (!process.env[key]) {
      process.env[key] = value;
    }
  }
}

function parsePositiveInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isFinite(value) || value <= 0 || !Number.isInteger(value)) {
    throw new Error(`[config] ${name} must be a positive integer, received "${raw}"`);
  }
  return value;
}

function parseSupabaseEnvGuard(): void {
  if ((process.env.NODE_ENV || "").toLowerCase() === "test") {
    return;
  }

  const keys = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
  ] as const;

  const defined = keys.filter((key) => typeof process.env[key] === "string" && process.env[key]!.length > 0);
  if (defined.length > 0 && defined.length < keys.length) {
    throw new Error(
      "[config] Incomplete Supabase env: set SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY together (or leave all unset)."
    );
  }
}

function parseCorsOrigin(): string[] | true {
  const raw = process.env.CORS_ORIGIN?.trim();
  if (!raw) return true;
  return raw.split(",").map((value) => value.trim()).filter((value) => value.length > 0);
}

function buildConfig(): RuntimeConfig {
  loadEnvFilesOnce();
  parseSupabaseEnvGuard();

  const handIdleSeconds = parsePositiveInt("HAND_IDLE_TIMEOUT_SECONDS", 60);
  const showdownDecisionSeconds = parsePositiveInt("SHOWDOWN_DECISION_TIMEOUT_SECONDS", 4);
  const runCountDecisionSeconds = parsePositiveInt("RUN_COUNT_DECISION_TIMEOUT_SECONDS", 15);
  const roomEmptyTtlMinutes = parsePositiveInt("ROOM_EMPTY_TTL_MINUTES", 10);

  const port = parsePositiveInt("PORT", 4000);

  return {
    version: "v1",
    envName: process.env.NODE_ENV || "development",
    port,
    corsOrigin: parseCorsOrigin(),
    handIdleTimeoutMs: handIdleSeconds * 1_000,
    showdownDecisionTimeoutMs: showdownDecisionSeconds * 1_000,
    runCountDecisionTimeoutMs: runCountDecisionSeconds * 1_000,
    roomEmptyTtlMs: roomEmptyTtlMinutes * 60_000,
    roomCodeLength: ROOM_CODE_LENGTH,
    roomCodeAlphabet: ROOM_CODE_ALPHABET,
    minPlayers: ROOM_LIMITS.minPlayers,
    maxPlayers: ROOM_LIMITS.maxPlayers,
    defaultRoomName: "Training Room",
    defaultRoomSettings: { ...DEFAULTS },
    defaultCreateRoom: {
      maxPlayers: 6,
      smallBlind: DEFAULT_SMALL_BLIND,
      bigBlind: DEFAULT_BIG_BLIND,
      buyInMinMultiplierBb: 20,
      buyInMaxMultiplierBb: 200,
    },
  };
}

export function getRuntimeConfig(): RuntimeConfig {
  if (!cachedConfig) {
    cachedConfig = buildConfig();
  }
  return cachedConfig;
}
