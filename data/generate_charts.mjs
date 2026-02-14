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

// Hand strength tier with improved granularity (0 = strongest, 7 = weakest)
function handTier(hand) {
  const r1 = RANKS.indexOf(hand[0]);
  const r2 = RANKS.indexOf(hand.length === 2 ? hand[1] : hand[1]);
  const suited = hand.endsWith("s");
  const pair = hand.length === 2 || hand[0] === hand[1];
  const gap = Math.abs(r1 - r2);
  const highRank = Math.min(r1, r2);
  const lowRank = Math.max(r1, r2);

  // Pocket pairs
  if (pair) {
    if (highRank <= 2) return 0;  // AA-QQ (premium)
    if (highRank <= 4) return 1;  // JJ-TT (strong)
    if (highRank <= 6) return 2;  // 99-88 (medium)
    if (highRank <= 8) return 3;  // 77-66 (small)
    if (highRank <= 10) return 4; // 55-44 (very small)
    return 5;                     // 33-22 (micro)
  }

  // Broadway hands (AK, AQ, KQ)
  if (highRank === 0 && lowRank <= 2) return suited ? 0 : 1; // AKs/AKo, AQs/AQo
  if (highRank === 1 && lowRank === 2) return suited ? 1 : 2; // KQs/KQo
  
  // Ace-x hands
  if (highRank === 0) {
    if (lowRank <= 4) return suited ? 1 : 2;  // AJs/AJo, ATs/ATo
    if (suited) {
      if (lowRank <= 7) return 2;              // A9s-A7s
      if (lowRank <= 9) return 3;              // A6s-A5s (wheel value)
      return 4;                                // A4s-A2s (wheel draws)
    }
    return lowRank <= 6 ? 4 : 6;              // A9o-A2o (weak offsuit)
  }
  
  // King-x hands
  if (highRank === 1) {
    if (lowRank <= 4) return suited ? 2 : 3;  // KJs/KJo, KTs/KTo
    if (suited) return lowRank <= 8 ? 3 : 4;  // K9s-K2s
    return 5;                                 // K9o-K2o
  }
  
  // Queen-x hands
  if (highRank === 2) {
    if (lowRank <= 4) return suited ? 3 : 4;  // QJs/QJo, QTs/QTo
    if (suited) return lowRank <= 7 ? 4 : 5;  // Q9s-Q2s
    return 5;
  }
  
  // Jack-x hands
  if (highRank === 3) {
    if (lowRank <= 5) return suited ? 3 : 4;  // JTs/JTo, J9s/J9o
    if (suited) return 5;
    return 6;
  }
  
  // Suited connectors and one-gappers
  if (suited) {
    if (gap === 0 && highRank >= 4 && highRank <= 7) return 3;  // T9s-76s
    if (gap === 1 && highRank >= 4 && highRank <= 7) return 4;  // T8s-75s
    if (gap === 0 && highRank >= 8) return 4;                   // 65s-54s
    if (gap <= 2) return 5;                                     // Other suited semi-connected
    return 6;                                                   // Weak suited
  }
  
  // Offsuit connectors (limited value)
  if (gap === 0 && highRank <= 6) return 5;  // T9o-87o
  if (gap <= 1 && highRank <= 5) return 6;   // T8o-98o
  
  return 7; // Trash offsuit
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

// Generate mix with improved calibration and position sensitivity
function generateMix(tier, spotType) {
  const configs = {
    // UTG open: tight, disciplined range
    open_ep: [
      { raise: 1.00, call: 0, fold: 0.00 },   // tier 0: premium
      { raise: 0.98, call: 0, fold: 0.02 },   // tier 1: very strong
      { raise: 0.80, call: 0, fold: 0.20 },   // tier 2: strong
      { raise: 0.45, call: 0, fold: 0.55 },   // tier 3: medium
      { raise: 0.18, call: 0, fold: 0.82 },   // tier 4: marginal
      { raise: 0.05, call: 0, fold: 0.95 },   // tier 5: rare bluffs
      { raise: 0.00, call: 0, fold: 1.00 },   // tier 6: fold
      { raise: 0.00, call: 0, fold: 1.00 },   // tier 7: fold
    ],
    // HJ open: moderately wider
    open_mp: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.88, call: 0, fold: 0.12 },
      { raise: 0.60, call: 0, fold: 0.40 },
      { raise: 0.30, call: 0, fold: 0.70 },
      { raise: 0.12, call: 0, fold: 0.88 },
      { raise: 0.03, call: 0, fold: 0.97 },
      { raise: 0.00, call: 0, fold: 1.00 },
    ],
    // CO open: wider, aggressive
    open_co: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.92, call: 0, fold: 0.08 },
      { raise: 0.75, call: 0, fold: 0.25 },
      { raise: 0.52, call: 0, fold: 0.48 },
      { raise: 0.30, call: 0, fold: 0.70 },
      { raise: 0.12, call: 0, fold: 0.88 },
      { raise: 0.02, call: 0, fold: 0.98 },
    ],
    // BTN open: widest range with maximum fold equity
    open_btn: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.96, call: 0, fold: 0.04 },
      { raise: 0.85, call: 0, fold: 0.15 },
      { raise: 0.68, call: 0, fold: 0.32 },
      { raise: 0.48, call: 0, fold: 0.52 },
      { raise: 0.25, call: 0, fold: 0.75 },
      { raise: 0.08, call: 0, fold: 0.92 },
    ],
    // BB defend vs BTN: wide defense with mixed strategy
    defend_bb_vs_btn: [
      { raise: 0.50, call: 0.50, fold: 0.00 },  // tier 0: balanced 3bet/call
      { raise: 0.28, call: 0.68, fold: 0.04 },  // tier 1: mostly call
      { raise: 0.18, call: 0.68, fold: 0.14 },  // tier 2: call-heavy
      { raise: 0.10, call: 0.58, fold: 0.32 },  // tier 3: defend wide
      { raise: 0.06, call: 0.48, fold: 0.46 },  // tier 4: marginal defense
      { raise: 0.04, call: 0.35, fold: 0.61 },  // tier 5: selective
      { raise: 0.02, call: 0.20, fold: 0.78 },  // tier 6: bluff 3bets + some calls
      { raise: 0.00, call: 0.08, fold: 0.92 },  // tier 7: mostly fold
    ],
    // BB defend vs CO: tighter defense vs stronger range
    defend_bb_vs_co: [
      { raise: 0.48, call: 0.52, fold: 0.00 },
      { raise: 0.24, call: 0.62, fold: 0.14 },
      { raise: 0.14, call: 0.56, fold: 0.30 },
      { raise: 0.07, call: 0.42, fold: 0.51 },
      { raise: 0.04, call: 0.30, fold: 0.66 },
      { raise: 0.02, call: 0.18, fold: 0.80 },
      { raise: 0.00, call: 0.08, fold: 0.92 },
      { raise: 0.00, call: 0.02, fold: 0.98 },
    ],
    // BB defend vs UTG: tight defense vs nutted range
    defend_bb_vs_ep: [
      { raise: 0.42, call: 0.56, fold: 0.02 },
      { raise: 0.22, call: 0.60, fold: 0.18 },
      { raise: 0.10, call: 0.48, fold: 0.42 },
      { raise: 0.04, call: 0.32, fold: 0.64 },
      { raise: 0.02, call: 0.20, fold: 0.78 },
      { raise: 0.00, call: 0.10, fold: 0.90 },
      { raise: 0.00, call: 0.03, fold: 0.97 },
      { raise: 0.00, call: 0.00, fold: 1.00 },
    ],
    // SB vs BB: aggressive stealing with limp option removed
    open_sb: [
      { raise: 1.00, call: 0, fold: 0.00 },
      { raise: 0.96, call: 0, fold: 0.04 },
      { raise: 0.88, call: 0, fold: 0.12 },
      { raise: 0.70, call: 0, fold: 0.30 },
      { raise: 0.50, call: 0, fold: 0.50 },
      { raise: 0.32, call: 0, fold: 0.68 },
      { raise: 0.15, call: 0, fold: 0.85 },
      { raise: 0.04, call: 0, fold: 0.96 },
    ],
  };

  const cfg = configs[spotType] || configs.open_co;
  const mix = cfg[Math.min(tier, cfg.length - 1)];
  return { raise: round4(mix.raise), call: round4(mix.call), fold: round4(mix.fold) };
}

function round4(n) {
  return Math.round(n * 10000) / 10000;
}

// Apply sizing adjustments: larger sizes = tighter/polarized ranges
function applySizingAdjustment(mix, multiplier, tier) {
  if (multiplier === 1.0) return mix;
  
  // Larger sizes: reduce raise frequency on marginal hands, increase on premium/bluffs
  const isPremium = tier <= 1;
  const isBluff = tier >= 6;
  const isMarginal = !isPremium && !isBluff;
  
  let raiseAdj = 1.0;
  if (isPremium) {
    raiseAdj = Math.min(1.5, 1 + (multiplier - 1) * 0.5); // Raise more with premium
  } else if (isBluff) {
    raiseAdj = Math.max(0.7, 1 - (multiplier - 1) * 0.3); // Bluff slightly less
  } else if (isMarginal) {
    raiseAdj = Math.max(0.5, 1 - (multiplier - 1) * 0.8); // Fold more marginal
  }
  
  const newRaise = mix.raise * raiseAdj;
  const diff = mix.raise - newRaise;
  
  return {
    raise: newRaise,
    call: mix.call,
    fold: mix.fold + diff
  };
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

// Define base spots (without sizing suffix)
const BASE_SPOTS = [
  { spotBase: "UTG_unopened", spotType: "open_ep", heroPos: "UTG", villainPos: "BB", tags_extra: [] },
  { spotBase: "HJ_unopened", spotType: "open_mp", heroPos: "HJ", villainPos: "BB", tags_extra: [] },
  { spotBase: "CO_unopened", spotType: "open_co", heroPos: "CO", villainPos: "BB", tags_extra: ["IP_ADVANTAGE"] },
  { spotBase: "BTN_unopened", spotType: "open_btn", heroPos: "BTN", villainPos: "BB", tags_extra: ["IP_ADVANTAGE", "FOLD_EQUITY"] },
  { spotBase: "SB_unopened", spotType: "open_sb", heroPos: "SB", villainPos: "BB", tags_extra: ["FOLD_EQUITY"] },
  { spotBase: "BB_vs_BTN_facing", spotType: "defend_bb_vs_btn", heroPos: "BB", villainPos: "BTN", tags_extra: ["DEFEND_RANGE"] },
  { spotBase: "BB_vs_CO_facing", spotType: "defend_bb_vs_co", heroPos: "BB", villainPos: "CO", tags_extra: ["DEFEND_RANGE"] },
  { spotBase: "BB_vs_UTG_facing", spotType: "defend_bb_vs_ep", heroPos: "BB", villainPos: "UTG", tags_extra: ["DEFEND_RANGE"] },
];

// Sizings to generate
const SIZINGS = [
  { suffix: "open2.5x", multiplier: 1.0 },   // Standard
  { suffix: "open3x", multiplier: 1.1 },     // Slightly tighter
  { suffix: "open4x", multiplier: 1.2 },     // Tighter, polarized
];

const hands = all169();
const rows = [];

for (const spotDef of BASE_SPOTS) {
  for (const sizing of SIZINGS) {
    const spot = `${spotDef.spotBase}_${sizing.suffix}`;
    
    for (const hand of hands) {
      const tier = handTier(hand);
      const rawMix = generateMix(tier, spotDef.spotType);
      
      // Apply sizing adjustment
      const adjustedMix = applySizingAdjustment(rawMix, sizing.multiplier, tier);
      const mix = normalizeMix(adjustedMix);
      
      const baseTags = getTags(hand);
      const notes = [...new Set([...baseTags, ...spotDef.tags_extra])];

      rows.push({
        format: "cash_6max_100bb",
        spot,
        hand,
        mix,
        notes,
      });
    }
  }
}

const outPath = join(__dirname, "preflop_charts.json");
writeFileSync(outPath, JSON.stringify(rows, null, 2), "utf-8");
console.log(`Generated ${rows.length} chart entries`);
console.log(`  ${BASE_SPOTS.length} base spots × ${SIZINGS.length} sizings × ${hands.length} hands`);
console.log(`Output: ${outPath}`);
