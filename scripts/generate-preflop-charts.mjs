// Generate preflop chart JSONs for the GTO Strategy page from curated public GTO ranges.
//
// Replaces the cardpilot-preflop-cfr-v1 solver output (equity-realization model produced
// frequencies far from real GTO — see reports/preflop-chart-audit-2026-07-09.md).
// Ranges here are hand-curated from published 100bb 6-max cash GTO solutions
// (GTO Wizard free preflop solutions, public "implementable GTO" chart sets),
// simplified to mostly-pure strategies with 25/50/75% mixes.
//
// Structural fixes vs the old data:
//   - facing_open for BTN gets a cold-call action (was 3bet-or-fold)
//   - facing_4bet gets an allin (5-bet jam) action (was fold/call only)
//   - facing_3bet grids only contain hands in the hero's RFI opening range
//   - facing_4bet grids only contain hands in the hero's 3-bet range
//
// Usage:
//   node scripts/generate-preflop-charts.mjs           # dry run: validation table only
//   node scripts/generate-preflop-charts.mjs --write   # write JSONs into public dir

import fs from 'node:fs';
import path from 'node:path';

const OUT_DIR = 'apps/web/public/data/preflop/solutions/cash_6max_100bb';
const SOLVE_DATE = '2026-07-09';
const SOLVER_TAG = 'public-gto-charts-v1';
const WRITE = process.argv.includes('--write');

const RANKS = 'AKQJT98765432';

// ── Hand-class helpers ──────────────────────────────────────────────────────

function combos(hc) {
  if (hc.length === 2) return 6;
  return hc[2] === 's' ? 4 : 12;
}

function allHandClasses() {
  const out = [];
  for (let i = 0; i < 13; i++) {
    for (let j = 0; j < 13; j++) {
      if (i === j) out.push(RANKS[i] + RANKS[j]);
      else if (i < j) out.push(RANKS[i] + RANKS[j] + 's');
      else out.push(RANKS[j] + RANKS[i] + 'o');
    }
  }
  return out;
}
const ALL_HANDS = allHandClasses();

// ── Range DSL ───────────────────────────────────────────────────────────────
// "TT+" pairs TT..AA | "77-33" pair run | "ATs+" ATs..A(K-1)s | "A5s-A2s" kicker run
// "AQo+" like suited | single classes "K9s" | weight suffix ":0.5"

function expandSpec(spec) {
  const out = [];
  const ri = (c) => RANKS.indexOf(c);

  let m;
  if ((m = spec.match(/^([2-9TJQKA])\1\+$/))) {
    for (let i = ri(m[1]); i >= 0; i--) out.push(RANKS[i] + RANKS[i]);
  } else if ((m = spec.match(/^([2-9TJQKA])\1-([2-9TJQKA])\2$/))) {
    const [a, b] = [ri(m[1]), ri(m[2])].sort((x, y) => x - y);
    for (let i = a; i <= b; i++) out.push(RANKS[i] + RANKS[i]);
  } else if ((m = spec.match(/^([2-9TJQKA])\1$/))) {
    out.push(spec);
  } else if ((m = spec.match(/^([2-9TJQKA])([2-9TJQKA])([so])\+$/))) {
    const hi = ri(m[1]);
    for (let k = ri(m[2]); k > hi; k--) out.push(m[1] + RANKS[k] + m[3]);
  } else if ((m = spec.match(/^([2-9TJQKA])([2-9TJQKA])([so])-\1([2-9TJQKA])\3$/))) {
    const [a, b] = [ri(m[2]), ri(m[4])].sort((x, y) => x - y);
    for (let k = a; k <= b; k++) out.push(m[1] + RANKS[k] + m[3]);
  } else if ((m = spec.match(/^([2-9TJQKA])([2-9TJQKA])([so])$/))) {
    out.push(spec);
  } else {
    throw new Error(`Bad range spec: ${spec}`);
  }
  return out;
}

function R(str) {
  const range = new Map();
  if (!str) return range;
  for (const tok of str.split(',').map((s) => s.trim()).filter(Boolean)) {
    const [spec, w] = tok.split(':');
    const weight = w !== undefined ? parseFloat(w) : 1;
    for (const hc of expandSpec(spec)) {
      range.set(hc, Math.min(1, (range.get(hc) ?? 0) + weight));
    }
  }
  return range;
}

// ── Spot strategy definitions ───────────────────────────────────────────────
// Each spot: { [actionName]: rangeString }. Fold is the residual.
// For facing_3bet / facing_4bet, strategies are clipped to the arrival range.

// ---- RFI (2.5bb open) ----
const RFI = {
  UTG_RFI: {
    'open_2.5':
      '66+,55-22:0.5,ATs+,A9s,A5s,A4s,A3s:0.5,A2s:0.5,KTs+,K9s:0.5,QTs+,Q9s:0.5,' +
      'JTs,J9s:0.5,T9s,98s,87s,76s,65s,54s:0.5,AJo+,KQo',
  },
  HJ_RFI: {
    'open_2.5':
      '22+,A2s+,K9s+,K8s:0.5,Q9s+,J9s+,T9s,T8s:0.5,98s,97s:0.5,87s,76s,65s,54s,' +
      'AJo+,ATo:0.5,KQo,KJo:0.5,QJo:0.5',
  },
  CO_RFI: {
    'open_2.5':
      '22+,A2s+,K6s+,K5s:0.5,K4s:0.5,K3s:0.5,K2s:0.5,Q8s+,Q7s:0.5,Q6s:0.5,J8s+,' +
      'T8s+,97s+,86s+,76s,75s:0.5,65s,64s:0.5,54s,53s:0.5,43s:0.5,' +
      'ATo+,A9o:0.5,KTo+,QTo+,JTo:0.5',
  },
  BTN_RFI: {
    'open_2.5':
      '22+,A2s+,K2s+,Q6s+,Q5s:0.5,Q4s:0.5,Q3s:0.5,Q2s:0.5,J4s+,J3s:0.5,J2s:0.5,' +
      'T6s+,T5s:0.5,T4s:0.5,96s+,95s:0.5,85s+,84s:0.5,75s+,74s:0.5,64s+,53s+,43s,' +
      'A5o+,A4o:0.5,A3o:0.5,A2o:0.5,K9o+,K8o:0.5,QTo+,Q9o:0.5,JTo,J9o:0.5,T9o,T8o:0.5,98o:0.5',
  },
  SB_RFI: {
    'open_2.5':
      '22+,A2s+,K2s+,Q2s+,J5s+,J4s:0.5,J3s:0.5,J2s:0.5,T6s+,T5s:0.5,96s+,95s:0.5,' +
      '85s+,84s:0.5,75s+,74s:0.5,64s+,53s+,43s,' +
      'A2o+,K7o+,K6o:0.5,K5o:0.5,Q9o+,Q8o:0.5,J9o+,J8o:0.5,T8o+,98o,87o:0.5',
  },
};

// ---- BB facing opens: fold / call / 3bet ----
const BB_VS_OPEN = {
  BB_vs_SB_open: {
    '3bet_7.5':
      'TT+,99:0.5,ATs+,A9s:0.5,A8s:0.5,A7s:0.5,A6s:0.5,A5s-A2s:0.5,KQs,KJs:0.5,KTs:0.5,K9s:0.5,K8s:0.5,' +
      'QJs:0.5,QTs:0.5,JTs:0.5,T9s:0.5,T8s:0.25,98s:0.5,87s:0.5,76s:0.5,65s:0.5,54s:0.5,' +
      'AKo,AQo:0.5,AJo:0.25,A5o:0.5,A4o:0.5,KTo:0.5,KJo:0.5,QJo:0.5',
    fold:
      '32o,42o,52o,62o,72o,82o,92o,43o,53o,63o,73o,83o,93o,T2o,T3o,' +
      '64o,74o,84o,94o,T4o:0.5,95o:0.5,85o:0.5,75o:0.5,65o:0.5,J2o:0.5,J3o:0.5,T5o:0.5',
  },
  BB_vs_BTN_open: {
    '3bet_8.75':
      'JJ+,TT:0.75,99:0.5,AQs+,AJs:0.75,ATs:0.75,A9s:0.5,A5s-A2s:0.5,KQs:0.75,KJs:0.5,KTs:0.5,' +
      'QJs:0.5,JTs:0.5,T9s:0.25,98s:0.25,87s:0.25,76s:0.25,65s:0.25,' +
      'AKo,AQo:0.5,AJo:0.25,A5o:0.5,A4o:0.5,KJo:0.25,KQo:0.25',
    fold:
      '32o,42o,52o,62o,72o,82o,92o,43o,53o,63o,73o,83o,93o,54o:0.5,64o,74o,84o,94o,' +
      'T2o,T3o,T4o,T5o,T6o,95o,85o,75o,65o,J2o,J3o,J4o,J5o:0.5,96o,86o,76o,87o:0.25,97o:0.5,' +
      'Q2o,Q3o,Q4o:0.5,32s:0.5,42s:0.5,52s:0.25',
  },
  BB_vs_CO_open: {
    '3bet_8.75':
      'JJ+,TT:0.75,99:0.25,AQs+,AJs,ATs:0.5,A5s:0.5,A4s:0.5,KQs:0.75,KJs:0.5,QJs:0.25,JTs:0.25,' +
      'T9s:0.25,98s:0.25,AKo,AQo:0.5,A5o:0.5',
    fold:
      '32o,42o,52o,62o,72o,82o,92o,43o,53o,63o,73o,83o,93o,54o,64o,74o,84o,94o,' +
      'T2o,T3o,T4o,T5o,T6o,95o,85o,75o,65o,96o,86o,76o,87o:0.5,97o:0.5,' +
      'J2o,J3o,J4o,J5o,J6o,J7o:0.5,T7o:0.5,Q2o,Q3o,Q4o,Q5o,Q6o:0.5,K2o:0.5,K3o:0.5,' +
      '32s,42s,52s:0.5,62s:0.5,63s:0.5,72s,73s:0.5,82s:0.5,83s:0.5,92s:0.5',
  },
  BB_vs_HJ_open: {
    '3bet_8.75':
      'JJ+,TT:0.75,AQs+,AJs:0.75,ATs:0.25,A5s:0.5,A4s:0.5,KQs:0.75,KJs:0.25,QJs:0.25,AKo,AQo:0.5',
    fold:
      '32o,42o,52o,62o,72o,82o,92o,43o,53o,63o,73o,83o,93o,54o,64o,74o,84o,94o,' +
      'T2o,T3o,T4o,T5o,T6o,T7o,95o,85o,75o,65o,96o,86o,76o,87o:0.5,97o:0.5,98o:0.25,' +
      'J2o,J3o,J4o,J5o,J6o,J7o,J8o:0.5,Q2o,Q3o,Q4o,Q5o,Q6o,Q7o:0.5,Q8o:0.5,K2o,K3o,K4o:0.5,K5o:0.5,' +
      'A2o:0.25,32s,42s,52s,62s,63s:0.5,72s,73s,82s,83s:0.5,92s:0.5,93s:0.5,J2s:0.5,' +
      '84s:0.5,94s:0.5,74s:0.25,53s:0.25',
  },
  BB_vs_UTG_open: {
    '3bet_8.75': 'JJ+,TT:0.5,AQs+,AJs:0.5,A5s:0.75,A4s:0.25,KQs:0.5,AKo,AQo:0.25',
    fold:
      '32o,42o,52o,62o,72o,82o,92o,43o,53o,63o,73o,83o,93o,54o,64o,74o,84o,94o,' +
      'T2o,T3o,T4o,T5o,T6o,T7o,95o,85o,75o,65o,96o,86o,76o,87o:0.5,97o:0.5,98o:0.5,T8o:0.5,' +
      'J2o,J3o,J4o,J5o,J6o,J7o,J8o,J9o:0.5,Q2o,Q3o,Q4o,Q5o,Q6o,Q7o,Q8o,Q9o:0.5,' +
      'K2o,K3o,K4o,K5o,K6o:0.5,K7o:0.5,K9o:0.5,A2o:0.5,A3o:0.5,A4o:0.5,' +
      '32s,42s,52s,62s,63s,72s,73s,82s,83s,92s,93s:0.5,J2s:0.5,J3s:0.5,' +
      '84s:0.5,94s:0.5,74s:0.5,53s:0.5,43s:0.5,K2s:0.5',
  },
};

// ---- SB facing opens: 3bet-or-fold (standard public-chart simplification) ----
const SB_VS_OPEN = {
  SB_vs_BTN_open: {
    '3bet_8.75':
      '88+,77:0.5,66:0.5,ATs+,A9s:0.5,A5s:0.5,A4s:0.5,KTs+,K9s:0.5,QTs+,JTs:0.5,' +
      'T9s:0.5,98s:0.5,76s:0.5,65s:0.5,AJo+,ATo:0.5,KQo,KJo:0.5,A5o:0.5',
  },
  SB_vs_CO_open: {
    '3bet_8.75':
      '99+,88:0.5,AJs+,ATs:0.5,A5s:0.5,A4s:0.5,KQs,KJs:0.5,QJs:0.5,JTs:0.5,' +
      'AQo+,AJo:0.5,KQo:0.5,A5o:0.25',
  },
  SB_vs_HJ_open: {
    '3bet_8.75':
      'TT+,99:0.5,AJs+,ATs:0.5,A5s:0.5,KQs,KJs:0.25,AQo+,AJo:0.25',
  },
  SB_vs_UTG_open: {
    '3bet_8.75': 'TT+,AQs+,AJs:0.5,A5s:0.5,KQs:0.5,AKo,AQo:0.5',
  },
};

// ---- HJ/CO facing opens: 3bet-or-fold ----
const MP_VS_OPEN = {
  HJ_vs_UTG_open: {
    '3bet_7.5': 'TT+,99:0.5,AQs+,AJs:0.5,ATs:0.25,A5s:0.5,KQs:0.75,KJs:0.25,AKo,AQo:0.5',
  },
  CO_vs_UTG_open: {
    '3bet_7.5': 'TT+,99:0.5,AQs+,AJs:0.5,ATs:0.25,A5s:0.5,KQs:0.5,AKo,AQo:0.5',
  },
  CO_vs_HJ_open: {
    '3bet_7.5': 'TT+,99:0.5,88:0.25,AJs+,ATs:0.5,A5s:0.5,A4s:0.25,KQs,KJs:0.25,JTs:0.25,AKo,AQo:0.5,AJo:0.25',
  },
};

// ---- BTN facing opens: fold / call / 3bet ----
const BTN_VS_OPEN = {
  BTN_vs_UTG_open: {
    '3bet_7.5': 'QQ+:0.5,AKs:0.5,AKo:0.5,A5s:0.5,JJ:0.25',
    call:
      'QQ+:0.5,AKs:0.5,AKo:0.5,JJ:0.75,TT,99,88,77:0.5,66:0.5,55:0.5,' +
      'AQs,AJs,ATs:0.5,KQs,KJs:0.5,QJs:0.5,JTs,T9s:0.5,98s:0.5,87s:0.5,76s:0.5,AQo:0.5',
  },
  BTN_vs_HJ_open: {
    '3bet_7.5': 'QQ+:0.5,JJ:0.5,AKs,AKo:0.75,AQs:0.5,A5s:0.5,A4s:0.5,KQs:0.25',
    call:
      'QQ+:0.5,JJ:0.5,TT,99,88,77:0.5,66:0.5,55:0.5,44:0.25,33:0.25,22:0.25,' +
      'AQs:0.5,AJs,ATs,A9s:0.5,KQs:0.75,KJs:0.5,KTs:0.5,QJs:0.5,QTs:0.5,JTs,' +
      'T9s,98s:0.5,87s:0.5,76s:0.5,65s:0.5,AKo:0.25,AQo:0.75,AJo:0.5,KQo:0.5',
  },
  BTN_vs_CO_open: {
    '3bet_7.5':
      'JJ+:0.5,TT:0.25,AKs,AQs:0.5,AKo,AQo:0.25,A5s:0.5,A4s:0.5,KQs:0.5,76s:0.25,65s:0.25',
    call:
      'JJ+:0.5,TT:0.75,99,88,77,66:0.5,55:0.5,44:0.25,33:0.25,22:0.25,' +
      'AQs:0.5,AJs,ATs,A9s:0.5,A8s:0.5,KQs:0.5,KJs,KTs:0.5,QJs,QTs:0.5,JTs,J9s:0.5,' +
      'T9s,98s,87s:0.5,76s:0.5,65s:0.5,54s:0.5,AQo:0.75,AJo:0.5,ATo:0.25,KQo:0.5,KJo:0.25',
  },
};

// ---- Facing 3-bet (hero = opener; arrival = hero RFI range) ----
// Templates by (hero open width, 3bettor position type).
const VS_3BET_TIGHT_VS_BLIND = {
  fourBet: 'AA:0.6,KK:0.6,QQ:0.25,AKs:0.35,AKo:0.35,A5s:0.4',
  call:
    'AA:0.4,KK:0.4,QQ:0.75,JJ,TT,99:0.75,88:0.6,77:0.5,66:0.35,55:0.25,AKs:0.65,AKo:0.65,' +
    'AQs,AJs:0.9,ATs:0.6,A9s:0.3,A5s:0.35,A4s:0.3,KQs,KJs:0.7,KTs:0.5,QJs:0.6,QTs:0.4,' +
    'JTs:0.8,T9s:0.6,98s:0.5,87s:0.4,76s:0.35,65s:0.3,54s:0.25,AQo:0.4,AJo:0.15,KQo:0.2',
};
const VS_3BET_WIDE_VS_BLIND = {
  fourBet: 'AA:0.6,KK:0.6,QQ:0.4,JJ:0.25,AKs:0.5,AKo:0.5,A5s:0.55,A4s:0.45',
  call:
    'AA:0.4,KK:0.4,QQ:0.6,JJ:0.75,TT:0.9,99:0.85,88:0.8,77:0.7,66:0.6,55:0.5,44:0.4,33:0.35,22:0.35,' +
    'AKs:0.5,AKo:0.5,AQs,AJs:0.95,ATs:0.9,A9s:0.65,A8s:0.6,A7s:0.5,A6s:0.45,A5s:0.45,A4s:0.55,A3s:0.5,A2s:0.4,' +
    'KQs,KJs:0.9,KTs:0.75,K9s:0.6,QJs:0.8,QTs:0.65,Q9s:0.5,JTs:0.9,J9s:0.55,T9s:0.8,T8s:0.5,' +
    '98s:0.7,97s:0.4,87s:0.6,86s:0.35,76s:0.55,75s:0.3,65s:0.5,64s:0.25,54s:0.45,' +
    'AQo:0.65,AJo:0.5,ATo:0.3,KQo:0.6,KJo:0.35,KTo:0.15,QJo:0.3,QTo:0.15,JTo:0.2',
};
const VS_3BET_TIGHT_VS_IP = {
  fourBet: 'AA:0.65,KK:0.6,QQ:0.2,AKs:0.3,AKo:0.3,A5s:0.35',
  call:
    'AA:0.35,KK:0.4,QQ:0.8,JJ:0.9,TT:0.8,99:0.6,88:0.5,77:0.4,66:0.25,AKs:0.7,AKo:0.6,' +
    'AQs:0.9,AJs:0.6,ATs:0.45,A5s:0.25,KQs:0.85,KJs:0.5,KTs:0.3,QJs:0.45,QTs:0.25,JTs:0.7,' +
    'T9s:0.5,98s:0.4,87s:0.3,76s:0.25,65s:0.2,AQo:0.25,KQo:0.1',
};
const VS_3BET_MID_VS_IP = {
  fourBet: 'AA:0.65,KK:0.6,QQ:0.3,AKs:0.35,AKo:0.35,A5s:0.4,A4s:0.3',
  call:
    'AA:0.35,KK:0.4,QQ:0.7,JJ:0.9,TT:0.85,99:0.65,88:0.55,77:0.45,66:0.35,55:0.25,AKs:0.65,AKo:0.6,' +
    'AQs:0.95,AJs:0.75,ATs:0.6,A9s:0.3,A5s:0.3,A4s:0.25,KQs:0.9,KJs:0.65,KTs:0.45,QJs:0.55,QTs:0.35,' +
    'JTs:0.75,J9s:0.25,T9s:0.6,T8s:0.25,98s:0.5,87s:0.4,76s:0.35,65s:0.3,54s:0.2,AQo:0.35,AJo:0.15,KQo:0.2',
};
// SB opened ~50% and faces a BB 3-bet — blind battle, defends widest.
const VS_3BET_SB_VS_BB = {
  fourBet:
    'AA:0.6,KK:0.6,QQ:0.5,JJ:0.4,TT:0.2,AKs:0.5,AKo:0.55,A5s:0.6,A4s:0.5,A3s:0.3,A5o:0.25,A4o:0.15',
  call:
    'AA:0.4,KK:0.4,QQ:0.5,JJ:0.6,TT:0.75,99:0.85,88:0.8,77:0.75,66:0.65,55:0.55,44:0.45,33:0.4,22:0.4,' +
    'AKs:0.5,AKo:0.45,AQs,AJs,ATs:0.95,A9s:0.7,A8s:0.65,A7s:0.6,A6s:0.55,A5s:0.4,A4s:0.5,A3s:0.55,A2s:0.5,' +
    'KQs,KJs:0.95,KTs:0.85,K9s:0.65,K8s:0.45,K7s:0.4,K6s:0.35,K5s:0.25,K4s:0.2,QJs:0.9,QTs:0.75,Q9s:0.55,Q8s:0.35,' +
    'JTs:0.9,J9s:0.6,J8s:0.35,T9s:0.8,T8s:0.55,T7s:0.25,97s:0.35,98s:0.7,87s:0.6,86s:0.35,76s:0.55,75s:0.3,' +
    '65s:0.5,64s:0.25,54s:0.45,53s:0.25,AQo:0.7,AJo:0.55,ATo:0.4,A9o:0.2,KQo:0.6,KJo:0.4,KTo:0.25,QJo:0.35,QTo:0.2,JTo:0.25',
};

const FACING_3BET = {
  UTG_vs_BB_3bet: VS_3BET_TIGHT_VS_BLIND,
  UTG_vs_SB_3bet: VS_3BET_TIGHT_VS_BLIND,
  HJ_vs_BB_3bet: VS_3BET_TIGHT_VS_BLIND,
  HJ_vs_SB_3bet: VS_3BET_TIGHT_VS_BLIND,
  CO_vs_BB_3bet: VS_3BET_WIDE_VS_BLIND,
  CO_vs_SB_3bet: VS_3BET_WIDE_VS_BLIND,
  BTN_vs_BB_3bet: VS_3BET_WIDE_VS_BLIND,
  BTN_vs_SB_3bet: VS_3BET_WIDE_VS_BLIND,
  SB_vs_BB_3bet: VS_3BET_SB_VS_BB,
  UTG_vs_HJ_3bet: VS_3BET_TIGHT_VS_IP,
  UTG_vs_CO_3bet: VS_3BET_TIGHT_VS_IP,
  UTG_vs_BTN_3bet: VS_3BET_TIGHT_VS_IP,
  HJ_vs_CO_3bet: VS_3BET_TIGHT_VS_IP,
  HJ_vs_BTN_3bet: VS_3BET_TIGHT_VS_IP,
  CO_vs_BTN_3bet: VS_3BET_MID_VS_IP,
};

// ---- Facing 4-bet (hero = 3-bettor; arrival = hero 3-bet range) ----
const VS_4BET_STD = {
  allin: 'AA:0.5,KK:0.55,QQ:0.2,JJ:0.1,AKs:0.4,AKo:0.45,A5s:0.35,A4s:0.3',
  call:
    'AA:0.5,KK:0.45,QQ:0.65,JJ:0.55,TT:0.45,99:0.3,88:0.2,AKs:0.6,AKo:0.5,' +
    'AQs:0.7,AJs:0.45,ATs:0.35,A9s:0.15,KQs:0.45,KJs:0.3,KTs:0.15,QJs:0.25,JTs:0.3,' +
    'T9s:0.25,98s:0.2,AQo:0.3,AJo:0.1',
};
const VS_4BET_BLIND_BATTLE = {
  allin: 'AA:0.5,KK:0.55,QQ:0.3,JJ:0.2,TT:0.1,AKs:0.4,AKo:0.45,A5s:0.35,A4s:0.3,A5o:0.2',
  call:
    'AA:0.5,KK:0.45,QQ:0.65,JJ:0.6,TT:0.6,99:0.55,88:0.3,AKs:0.6,AKo:0.5,' +
    'AQs:0.75,AJs:0.55,ATs:0.5,A9s:0.35,A8s:0.2,A7s:0.2,A6s:0.15,A5s:0.3,A4s:0.25,A3s:0.2,A2s:0.15,' +
    'KQs:0.55,KJs:0.4,KTs:0.3,K9s:0.2,K8s:0.1,QJs:0.4,QTs:0.2,JTs:0.35,T9s:0.3,T8s:0.15,' +
    '98s:0.25,87s:0.2,76s:0.2,65s:0.15,54s:0.15,AQo:0.4,AJo:0.15,KQo:0.15,KTo:0.1,QJo:0.1',
};

const FACING_4BET = {
  BB_vs_SB_4bet: VS_4BET_BLIND_BATTLE,
  BB_vs_BTN_4bet: VS_4BET_STD,
  BB_vs_CO_4bet: VS_4BET_STD,
  BB_vs_HJ_4bet: VS_4BET_STD,
  BB_vs_UTG_4bet: VS_4BET_STD,
  SB_vs_BTN_4bet: VS_4BET_STD,
  SB_vs_CO_4bet: VS_4BET_STD,
  SB_vs_HJ_4bet: VS_4BET_STD,
  SB_vs_UTG_4bet: VS_4BET_STD,
  BTN_vs_UTG_4bet: VS_4BET_STD,
  BTN_vs_HJ_4bet: VS_4BET_STD,
  BTN_vs_CO_4bet: VS_4BET_STD,
  CO_vs_UTG_4bet: VS_4BET_STD,
  CO_vs_HJ_4bet: VS_4BET_STD,
  HJ_vs_UTG_4bet: VS_4BET_STD,
};

// ── Build grids ─────────────────────────────────────────────────────────────

// Returns { grid, arrival } — grid freqs are conditional on arrival.
function buildRfiGrid(def) {
  const openAction = Object.keys(def)[0];
  const open = R(def[openAction]);
  const grid = {};
  for (const hc of ALL_HANDS) {
    const f = open.get(hc) ?? 0;
    grid[hc] = { fold: round3(1 - f), [openAction]: round3(f) };
  }
  const arrival = new Map(ALL_HANDS.map((h) => [h, 1]));
  return { grid, arrival };
}

function buildFacingOpenGrid(def) {
  const actions = Object.keys(def).filter((a) => a !== 'fold');
  const ranges = Object.fromEntries(actions.map((a) => [a, R(def[a])]));
  const foldRange = def.fold ? R(def.fold) : null;
  const grid = {};
  for (const hc of ALL_HANDS) {
    const entry = {};
    let cont = 0;
    for (const a of actions) {
      const f = ranges[a].get(hc) ?? 0;
      entry[a] = round3(f);
      cont += f;
    }
    if (cont > 1) throw new Error(`Continue freq > 1 for ${hc}`);
    if (foldRange) {
      // Explicit fold range: residual goes to call.
      const foldF = Math.min(1 - cont, foldRange.get(hc) ?? 0);
      entry.fold = round3(foldF);
      entry.call = round3(Math.max(0, 1 - cont - foldF) + (entry.call ?? 0));
    } else {
      entry.fold = round3(1 - cont);
    }
    grid[hc] = entry;
  }
  const arrival = new Map(ALL_HANDS.map((h) => [h, 1]));
  return { grid, arrival };
}

// Facing 3bet/4bet: grid only over arrival hands; strategy clipped to arrival.
function buildFacingRaiseGrid(def, arrival, actionNames) {
  const raiseRange = R(def.fourBet ?? def.allin);
  const callRange = R(def.call);
  const raiseAction = actionNames.raise;
  const grid = {};
  for (const [hc, w] of arrival) {
    if (w <= 0.001) continue;
    const raise = Math.min(1, raiseRange.get(hc) ?? 0);
    const call = Math.min(1 - raise, callRange.get(hc) ?? 0);
    grid[hc] = {
      fold: round3(Math.max(0, 1 - raise - call)),
      call: round3(call),
      [raiseAction]: round3(raise),
    };
  }
  return { grid, arrival };
}

function round3(x) {
  return Math.round(x * 1000) / 1000;
}

// ── Assemble spots ──────────────────────────────────────────────────────────

function aggregate(grid, arrival, actions) {
  const agg = Object.fromEntries(actions.map((a) => [a, 0]));
  let tot = 0;
  for (const [hc, freqs] of Object.entries(grid)) {
    const w = combos(hc) * (arrival.get(hc) ?? 0);
    if (w <= 0) continue;
    tot += w;
    for (const a of actions) agg[a] += (freqs[a] ?? 0) * w;
  }
  for (const a of actions) agg[a] = Math.round((agg[a] / tot) * 1000) / 1000;
  return agg;
}

function main() {
  const oldDir = OUT_DIR;
  const index = JSON.parse(fs.readFileSync(path.join(oldDir, 'index.json'), 'utf8'));

  // Pass 1: RFI grids (needed as arrival ranges for facing_3bet).
  const built = {}; // spot -> { grid, arrival, actions }
  const openRanges = {}; // pos -> Map(hand -> open freq)
  for (const [spot, def] of Object.entries(RFI)) {
    const { grid, arrival } = buildRfiGrid(def);
    const actions = ['fold', Object.keys(def)[0]];
    built[spot] = { grid, arrival, actions };
    const pos = spot.split('_')[0];
    openRanges[pos] = new Map(
      Object.entries(grid).map(([hc, f]) => [hc, f[Object.keys(def)[0]]]),
    );
  }

  // Pass 2: facing_open grids (3bet ranges become arrivals for facing_4bet).
  const threeBetRanges = {}; // 'H_vs_V' -> Map(hand -> 3bet freq)
  const facingOpenDefs = { ...BB_VS_OPEN, ...SB_VS_OPEN, ...MP_VS_OPEN, ...BTN_VS_OPEN };
  for (const [spot, def] of Object.entries(facingOpenDefs)) {
    const { grid, arrival } = buildFacingOpenGrid(def);
    const threeBetAction = Object.keys(def).find((a) => a.startsWith('3bet'));
    const hasCall = spot.startsWith('BB_') || spot.startsWith('BTN_');
    const actions = hasCall ? ['fold', 'call', threeBetAction] : ['fold', threeBetAction];
    built[spot] = { grid, arrival, actions };
    const key = spot.replace('_open', '');
    threeBetRanges[key] = new Map(
      Object.entries(grid).map(([hc, f]) => [hc, f[threeBetAction] ?? 0]),
    );
  }

  // Pass 3: facing_3bet (arrival = hero RFI open range).
  for (const [spot, def] of Object.entries(FACING_3BET)) {
    const hero = spot.split('_')[0];
    let arrival;
    if (hero === 'SB' && spot === 'SB_vs_BB_3bet') {
      arrival = openRanges['SB'];
    } else {
      arrival = openRanges[hero];
    }
    const old = JSON.parse(fs.readFileSync(path.join(oldDir, `${spot}.json`), 'utf8'));
    const raiseAction = old.actions.find((a) => a.startsWith('4bet'));
    const { grid } = buildFacingRaiseGrid(def, arrival, { raise: raiseAction });
    built[spot] = { grid, arrival, actions: ['fold', 'call', raiseAction] };
  }

  // Pass 4: facing_4bet (arrival = hero 3bet range from the matching facing_open spot).
  for (const [spot, def] of Object.entries(FACING_4BET)) {
    const m = spot.match(/^(\w+?)_vs_(\w+?)_4bet$/);
    const key = `${m[1]}_vs_${m[2]}`;
    const arrival = threeBetRanges[key];
    if (!arrival) throw new Error(`No 3bet range for ${key}`);
    const { grid } = buildFacingRaiseGrid(def, arrival, { raise: 'allin' });
    built[spot] = { grid, arrival, actions: ['fold', 'call', 'allin'] };
  }

  // Validation table + write.
  console.log('spot'.padEnd(24), 'aggregate frequencies (combo+arrival weighted)');
  for (const entry of index.spots) {
    const spot = entry.spot;
    const b = built[spot];
    if (!b) {
      console.log(spot.padEnd(24), 'MISSING DEFINITION');
      continue;
    }
    const agg = aggregate(b.grid, b.arrival, b.actions);
    const line = Object.entries(agg)
      .map(([a, v]) => `${a}=${(v * 100).toFixed(1)}%`)
      .join('  ');
    console.log(spot.padEnd(24), line);

    if (WRITE) {
      const old = JSON.parse(fs.readFileSync(path.join(oldDir, `${spot}.json`), 'utf8'));
      const rangeSize = Object.values(b.grid).filter(
        (f) => 1 - (f.fold ?? 0) > 0.02,
      ).length;
      const out = {
        spot: old.spot,
        format: old.format,
        heroPosition: old.heroPosition,
        ...(old.villainPosition ? { villainPosition: old.villainPosition } : {}),
        scenario: old.scenario,
        potSize: old.potSize,
        actions: b.actions,
        grid: b.grid,
        summary: {
          totalCombos: 169,
          rangeSize,
          actionFrequencies: agg,
        },
        metadata: {
          iterations: 0,
          exploitability: 0,
          solveDate: SOLVE_DATE,
          solver: SOLVER_TAG,
        },
      };
      fs.writeFileSync(path.join(oldDir, `${spot}.json`), JSON.stringify(out, null, 1));
    }
  }

  if (WRITE) {
    index.solveDate = SOLVE_DATE;
    fs.writeFileSync(path.join(oldDir, 'index.json'), JSON.stringify(index, null, 1));
    console.log(`\nWrote ${index.spots.length} spots + index.json to ${oldDir}`);
  } else {
    console.log('\nDry run. Re-run with --write to emit files.');
  }
}

main();
