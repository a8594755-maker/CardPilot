import { Router, type Request, type Response } from 'express';

interface RangeVsRangeBody {
  range1: string[]; // hand classes for player 1
  range2: string[]; // hand classes for player 2
  board?: string[]; // optional board cards
  simulations?: number;
}

interface CategoryBreakdown {
  category: string;
  count: number;
  percentage: number;
}

export function createRangeVsRangeRouter(): Router {
  const router = Router();

  // Compute range vs range equity
  router.post('/range-vs-range', async (req: Request, res: Response) => {
    try {
      const { range1, range2, board = [], simulations = 10000 } = req.body as RangeVsRangeBody;

      // Basic equity estimation using combo counting
      const combos1 = expandToCombos(range1);
      const combos2 = expandToCombos(range2);

      // Remove blocked combos (card overlap with board)
      const liveCombos1 = combos1.filter((c) => !hasOverlap(c, board));
      const liveCombos2 = combos2.filter((c) => !hasOverlap(c, board));

      // Monte Carlo equity estimation
      let p1Wins = 0;
      let p2Wins = 0;
      let ties = 0;
      const totalSims = Math.min(simulations, liveCombos1.length * liveCombos2.length);

      // Simple preflop equity approximation based on hand rankings
      for (let i = 0; i < totalSims; i++) {
        const c1 = liveCombos1[Math.floor(Math.random() * liveCombos1.length)];
        const c2 = liveCombos2[Math.floor(Math.random() * liveCombos2.length)];

        // Skip if cards overlap
        if (c1.some((card) => c2.includes(card))) continue;

        const strength1 = getHandStrength(c1);
        const strength2 = getHandStrength(c2);

        if (strength1 > strength2) p1Wins++;
        else if (strength2 > strength1) p2Wins++;
        else ties++;
      }

      const total = p1Wins + p2Wins + ties;
      const equity1 = total > 0 ? (p1Wins + ties / 2) / total : 0.5;
      const equity2 = 1 - equity1;

      // Category breakdowns
      const categories1 = categorizeRange(range1);
      const categories2 = categorizeRange(range2);

      // Overlap analysis
      const overlap = range1.filter((h) => range2.includes(h));

      res.json({
        range1Equity: equity1,
        range2Equity: equity2,
        range1Combos: liveCombos1.length,
        range2Combos: liveCombos2.length,
        simulations: total,
        categories1,
        categories2,
        overlap: overlap.length,
        overlapHands: overlap,
      });
    } catch (e) {
      res.status(500).json({ error: String(e) });
    }
  });

  return router;
}

const SUITS = ['h', 'd', 'c', 's'];

function expandToCombos(handClasses: string[]): string[][] {
  const combos: string[][] = [];
  for (const hc of handClasses) {
    if (hc.length === 2) {
      // Pair
      for (let i = 0; i < 4; i++) {
        for (let j = i + 1; j < 4; j++) {
          combos.push([hc[0] + SUITS[i], hc[1] + SUITS[j]]);
        }
      }
    } else if (hc[2] === 's') {
      for (const s of SUITS) {
        combos.push([hc[0] + s, hc[1] + s]);
      }
    } else {
      for (let i = 0; i < 4; i++) {
        for (let j = 0; j < 4; j++) {
          if (i !== j) combos.push([hc[0] + SUITS[i], hc[1] + SUITS[j]]);
        }
      }
    }
  }
  return combos;
}

function hasOverlap(combo: string[], board: string[]): boolean {
  return combo.some((c) => board.includes(c));
}

const RANK_VALUES: Record<string, number> = {
  A: 14,
  K: 13,
  Q: 12,
  J: 11,
  T: 10,
  '9': 9,
  '8': 8,
  '7': 7,
  '6': 6,
  '5': 5,
  '4': 4,
  '3': 3,
  '2': 2,
};

function getHandStrength(combo: string[]): number {
  const v1 = RANK_VALUES[combo[0][0]] || 0;
  const v2 = RANK_VALUES[combo[1][0]] || 0;
  const suited = combo[0][1] === combo[1][1];
  const isPair = v1 === v2;

  if (isPair) return v1 * 20 + 200;
  const high = Math.max(v1, v2);
  const low = Math.min(v1, v2);
  return high * 10 + low + (suited ? 5 : 0);
}

function categorizeRange(hands: string[]): CategoryBreakdown[] {
  const categories: Record<string, number> = {
    Pairs: 0,
    Broadway: 0,
    'Suited connectors': 0,
    Suited: 0,
    Offsuit: 0,
  };

  const broadways = new Set(['A', 'K', 'Q', 'J', 'T']);

  for (const h of hands) {
    if (h.length === 2) {
      categories['Pairs']++;
    } else if (broadways.has(h[0]) && broadways.has(h[1])) {
      categories['Broadway']++;
    } else if (h[2] === 's' && Math.abs(RANK_VALUES[h[0]] - RANK_VALUES[h[1]]) === 1) {
      categories['Suited connectors']++;
    } else if (h[2] === 's') {
      categories['Suited']++;
    } else {
      categories['Offsuit']++;
    }
  }

  const total = hands.length;
  return Object.entries(categories)
    .filter(([, count]) => count > 0)
    .map(([category, count]) => ({
      category,
      count,
      percentage: total > 0 ? (count / total) * 100 : 0,
    }));
}
