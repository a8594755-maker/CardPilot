#!/usr/bin/env node
// Generate preflop GTO charts for 6-max cash 100bb
// Output: data/preflop_charts.json

import { writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const RANKS = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"];

// Generate all 169 hand combos
function all169() {
  const hands = [];
  for (let i = 0; i < RANKS.length; i++) {
    for (let j = i; j < RANKS.length; j++) {
      if (i === j) {
        hands.push(`${RANKS[i]}${RANKS[j]}`); // pair
      } else {
        hands.push(`${RANKS[i]}${RANKS[j]}s`); // suited
        hands.push(`${RANKS[i]}${RANKS[j]}o`); // offsuit
      }
    }
  }
  return hands;
}

// Hand strength tier (0 = strongest, 7 = weakest)
function handTier(hand) {
  const r1 = RANKS.indexOf(hand[0]);
  const r2 = RANKS.indexOf(hand.length === 2 ? hand[1] : hand[1]);
  const suited = hand.endsWith("s");
  const pair = hand.length === 2 || hand[0] === hand[1];
  const gap = Math.abs(r1 - r2);
  const highRank = Math.min(r1, r2); // lower index = higher rank

  if (pair) {
    if (highRank <= 2) return 0; // AA-QQ
    if (highRank <= 4) return 1; // JJ-TT
    if (highRank <= 6) return 2; // 99-88
    if (highRank <= 8) return 3; // 77-66
    return 4; // 55-22
  }

  // Non-pair
  const suitBonus = suited ? 1 : 0;
  const connectedness = gap <= 3 ? 1 : 0;

  if (highRank === 0) { // Ax
    if (r2 <= 4) return suited ? 0 : 1; // AK-AT
    if (suited) return r2 <= 8 ? 2 : 3; // A9s-A6s / A5s-A2s
    return r2 <= 6 ? 3 : 5; // A9o-A8o / A7o-A2o
  }
  if (highRank === 1) { // Kx
    if (r2 <= 4) return suited ? 1 : 2; // KQ-KT
    if (suited) return r2 <= 8 ? 3 : 4;
    return r2 <= 6 ? 4 : 6;
  }
  if (highRank === 2) { // Qx
    if (r2 <= 4) return suited ? 2 : 3;
    if (suited) return r2 <= 7 ? 4 : 5;
    return r2 <= 5 ? 4 : 6;
  }
  if (highRank === 3) { // Jx
    if (r2 <= 5) return suited ? 3 : 4;
    if (suited) return 5;
    return 6;
  }

  // Middle cards
  if (suited && connectedness) return Math.min(4 + highRank - 4, 5);
  if (suited) return Math.min(5 + gap, 7);
  if (connectedness && highRank <= 6) return 5;
  return Math.min(6 + gap, 7);
}

// Tags based on hand properties
function getTags(hand) {
  const tags = [];
  const r1 = RANKS.indexOf(hand[0]);
  const r2 = RANKS.indexOf(hand.length === 2 ? hand[1] : hand[1]);
  const suited = hand.endsWith("s");
  const pair = hand.length === 2 || (hand.length >= 2 && hand[0] === hand[1]);
  const gap = Math.abs(r1 - r2);
  const highRank = Math.min(r1, r2);

  if (hand[0] === "A") tags.push("A_BLOCKER");
  if (hand[0] === "K") tags.push("K_BLOCKER");
  if (suited) tags.push("SUITED_PLAYABILITY");
  if (gap <= 2 && !pair && highRank >= 4) tags.push("WHEEL_PLAYABILITY");
  if (gap <= 3 && !pair) tags.push("CONNECTED");
  if (highRank <= 3 && !pair) tags.push("BROADWAY_STRENGTH");
  if (pair) tags.push("PAIR_VALUE");
  if (pair && highRank <= 2) tags.push("PREMIUM_PAIR");
  if (highRank >= 8 && !suited && !pair) tags.push("LOW_PLAYABILITY");
  if (highRank >= 6 && !suited && gap >= 4) tags.push("DOMINATION_RISK");

  return tags.length > 0 ? tags : ["LOW_PLAYABILITY"];
}

// Generate mix for a spot based on position advantage and hand tier
function generateMix(tier, spotType) {
  // spotType: "open_ep", "open_mp", "open_co", "open_btn", "defend_bb_vs_btn", "defend_bb_vs_co", "3bet_btn_vs_co"
  const configs = {
    // UTG open: tight
    open_ep: [
      { raise: 1.00, call: 0, fold: 0.00 },   // tier 0
      { raise: 0.95, call: 0, fold: 0.05 },   // tier 1
      { raise: 0.75, call: 0, fold: 0.25 },   // tier 2
      { raise: 0.40, call: 0, fold: 0.60 },   // tier 3
      { raise: 0.15, call: 0, fold: 0.85 },   // tier 4
      { raise: 0.05, call: 0, fold: 0.95 },   // tier 5
      { raise: 0.00, call: 0, fold: 1.00 },   // tier 6
      { raise: 0.00, call: 0, fold: 1.00 },   // tier 7
    ],
    // HJ open
    open_mp: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.85, call: 0, fold: 0.15 },
      { raise: 0.55, call: 0, fold: 0.45 },
      { raise: 0.25, call: 0, fold: 0.75 },
      { raise: 0.10, call: 0, fold: 0.90 },
      { raise: 0.00, call: 0, fold: 1.00 },
      { raise: 0.00, call: 0, fold: 1.00 },
    ],
    // CO open
    open_co: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.90, call: 0, fold: 0.10 },
      { raise: 0.70, call: 0, fold: 0.30 },
      { raise: 0.45, call: 0, fold: 0.55 },
      { raise: 0.25, call: 0, fold: 0.75 },
      { raise: 0.08, call: 0, fold: 0.92 },
      { raise: 0.00, call: 0, fold: 1.00 },
    ],
    // BTN open: widest
    open_btn: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.95, call: 0, fold: 0.05 },
      { raise: 0.80, call: 0, fold: 0.20 },
      { raise: 0.60, call: 0, fold: 0.40 },
      { raise: 0.40, call: 0, fold: 0.60 },
      { raise: 0.15, call: 0, fold: 0.85 },
      { raise: 0.05, call: 0, fold: 0.95 },
    ],
    // BB defend vs BTN open
    defend_bb_vs_btn: [
      { raise: 0.55, call: 0.45, fold: 0.00 },
      { raise: 0.30, call: 0.60, fold: 0.10 },
      { raise: 0.15, call: 0.65, fold: 0.20 },
      { raise: 0.08, call: 0.52, fold: 0.40 },
      { raise: 0.05, call: 0.40, fold: 0.55 },
      { raise: 0.03, call: 0.30, fold: 0.67 },
      { raise: 0.00, call: 0.15, fold: 0.85 },
      { raise: 0.00, call: 0.05, fold: 0.95 },
    ],
    // BB defend vs CO open (tighter)
    defend_bb_vs_co: [
      { raise: 0.50, call: 0.50, fold: 0.00 },
      { raise: 0.25, call: 0.55, fold: 0.20 },
      { raise: 0.12, call: 0.50, fold: 0.38 },
      { raise: 0.05, call: 0.35, fold: 0.60 },
      { raise: 0.03, call: 0.25, fold: 0.72 },
      { raise: 0.00, call: 0.15, fold: 0.85 },
      { raise: 0.00, call: 0.05, fold: 0.95 },
      { raise: 0.00, call: 0.00, fold: 1.00 },
    ],
    // BB defend vs UTG open (tightest)
    defend_bb_vs_ep: [
      { raise: 0.40, call: 0.55, fold: 0.05 },
      { raise: 0.20, call: 0.50, fold: 0.30 },
      { raise: 0.08, call: 0.40, fold: 0.52 },
      { raise: 0.03, call: 0.25, fold: 0.72 },
      { raise: 0.00, call: 0.15, fold: 0.85 },
      { raise: 0.00, call: 0.05, fold: 0.95 },
      { raise: 0.00, call: 0.00, fold: 1.00 },
      { raise: 0.00, call: 0.00, fold: 1.00 },
    ],
    // SB vs BB (steal)
    open_sb: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.95, call: 0, fold: 0.05 },
      { raise: 0.85, call: 0, fold: 0.15 },
      { raise: 0.65, call: 0, fold: 0.35 },
      { raise: 0.45, call: 0, fold: 0.55 },
      { raise: 0.30, call: 0, fold: 0.70 },
      { raise: 0.10, call: 0, fold: 0.90 },
      { raise: 0.00, call: 0, fold: 1.00 },
    ],
  };

  const cfg = configs[spotType] || configs.open_co;
  const mix = cfg[Math.min(tier, cfg.length - 1)];
  return { raise: round4(mix.raise), call: round4(mix.call), fold: round4(mix.fold) };
}

function round4(n) {
  return Math.round(n * 10000) / 10000;
}

// Ensure mix sums to 1
function normalizeMix(mix) {
  const sum = mix.raise + mix.call + mix.fold;
  if (Math.abs(sum - 1) < 0.001) {
    // Fix rounding: adjust fold
    const diff = round4(1 - mix.raise - mix.call);
    return { raise: mix.raise, call: mix.call, fold: Math.max(0, diff) };
  }
  return { raise: round4(mix.raise / sum), call: round4(mix.call / sum), fold: round4(mix.fold / sum) };
}

// Define spots
const SPOTS = [
  { spot: "UTG_unopened_open2.5x", spotType: "open_ep", heroPos: "UTG", villainPos: "BB", tags_extra: [] },
  { spot: "HJ_unopened_open2.5x", spotType: "open_mp", heroPos: "HJ", villainPos: "BB", tags_extra: [] },
  { spot: "CO_unopened_open2.5x", spotType: "open_co", heroPos: "CO", villainPos: "BB", tags_extra: ["IP_ADVANTAGE"] },
  { spot: "BTN_unopened_open2.5x", spotType: "open_btn", heroPos: "BTN", villainPos: "BB", tags_extra: ["IP_ADVANTAGE", "FOLD_EQUITY"] },
  { spot: "SB_unopened_open2.5x", spotType: "open_sb", heroPos: "SB", villainPos: "BB", tags_extra: ["FOLD_EQUITY"] },
  { spot: "BB_vs_BTN_facing_open2.5x", spotType: "defend_bb_vs_btn", heroPos: "BB", villainPos: "BTN", tags_extra: ["DEFEND_RANGE"] },
  { spot: "BB_vs_CO_facing_open2.5x", spotType: "defend_bb_vs_co", heroPos: "BB", villainPos: "CO", tags_extra: ["DEFEND_RANGE"] },
  { spot: "BB_vs_UTG_facing_open2.5x", spotType: "defend_bb_vs_ep", heroPos: "BB", villainPos: "UTG", tags_extra: ["DEFEND_RANGE"] },
];

const hands = all169();
const rows = [];

for (const spotDef of SPOTS) {
  for (const hand of hands) {
    const tier = handTier(hand);
    const rawMix = generateMix(tier, spotDef.spotType);
    const mix = normalizeMix(rawMix);
    const baseTags = getTags(hand);
    const notes = [...new Set([...baseTags, ...spotDef.tags_extra])];

    rows.push({
      format: "cash_6max_100bb",
      spot: spotDef.spot,
      hand,
      mix,
      notes,
    });
  }
}

const outPath = join(__dirname, "preflop_charts.json");
writeFileSync(outPath, JSON.stringify(rows, null, 2), "utf-8");
console.log(`Generated ${rows.length} chart entries for ${SPOTS.length} spots × ${hands.length} hands`);
console.log(`Output: ${outPath}`);
