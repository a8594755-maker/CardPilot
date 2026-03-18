/**
 * Range sampler: deals hands from a range with card removal.
 * Used by play-against-solution mode to deal realistic hands.
 */

const RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A'];
const SUITS = ['h', 'd', 'c', 's'];

/** Generate all 52 cards */
function allCards(): string[] {
  const cards: string[] = [];
  for (const r of RANKS) {
    for (const s of SUITS) {
      cards.push(r + s);
    }
  }
  return cards;
}

/** Get hand class from two specific cards (e.g. "Ah","Kh" -> "AKs") */
export function comboToHandClass(c1: string, c2: string): string {
  const r1 = RANKS.indexOf(c1[0]);
  const r2 = RANKS.indexOf(c2[0]);
  const s1 = c1[1];
  const s2 = c2[1];

  const high = r1 >= r2 ? c1[0] : c2[0];
  const low = r1 >= r2 ? c2[0] : c1[0];

  if (r1 === r2) return `${high}${low}`;
  return s1 === s2 ? `${high}${low}s` : `${high}${low}o`;
}

/** Expand a hand class to all specific combos (e.g. "AKs" -> ["AhKh","AdKd","AcKc","AsKs"]) */
function expandHandClass(hc: string): Array<[string, string]> {
  const combos: Array<[string, string]> = [];

  if (hc.length === 2) {
    // Pair: e.g. "AA"
    const r = hc[0];
    for (let i = 0; i < SUITS.length; i++) {
      for (let j = i + 1; j < SUITS.length; j++) {
        combos.push([r + SUITS[i], r + SUITS[j]]);
      }
    }
  } else if (hc[2] === 's') {
    // Suited: e.g. "AKs"
    for (const s of SUITS) {
      combos.push([hc[0] + s, hc[1] + s]);
    }
  } else {
    // Offsuit: e.g. "AKo"
    for (let i = 0; i < SUITS.length; i++) {
      for (let j = 0; j < SUITS.length; j++) {
        if (i !== j) {
          combos.push([hc[0] + SUITS[i], hc[1] + SUITS[j]]);
        }
      }
    }
  }

  return combos;
}

/**
 * Sample a hand from a strategy grid with card removal.
 *
 * @param grid - Hand class -> action -> frequency map
 * @param deadCards - Cards that can't be dealt (board cards, hero hand, etc.)
 * @returns A randomly sampled specific hand [card1, card2] or null if no valid hands
 */
export function sampleHandFromGrid(
  grid: Record<string, Record<string, number>>,
  deadCards: Set<string>,
): [string, string] | null {
  const deadSet = new Set([...deadCards].map((c) => c.toLowerCase()));
  const candidates: Array<{ combo: [string, string]; weight: number }> = [];

  for (const [hc, actions] of Object.entries(grid)) {
    // Total frequency for this hand class (sum of all action freqs)
    const totalFreq = Object.values(actions).reduce((s, v) => s + v, 0);
    if (totalFreq < 0.001) continue;

    const combos = expandHandClass(hc);
    for (const [c1, c2] of combos) {
      if (deadSet.has(c1.toLowerCase()) || deadSet.has(c2.toLowerCase())) continue;
      candidates.push({ combo: [c1, c2], weight: totalFreq });
    }
  }

  if (candidates.length === 0) return null;

  // Weighted random sampling
  const totalWeight = candidates.reduce((s, c) => s + c.weight, 0);
  let roll = Math.random() * totalWeight;

  for (const c of candidates) {
    roll -= c.weight;
    if (roll <= 0) return c.combo;
  }

  return candidates[candidates.length - 1].combo;
}

/**
 * Sample a GTO action from the strategy grid for a given hand.
 *
 * @param grid - Hand class -> action -> frequency map
 * @param hand - The specific hand [card1, card2]
 * @param actions - Available action names
 * @returns The sampled action name
 */
export function sampleGtoAction(
  grid: Record<string, Record<string, number>>,
  hand: [string, string],
  actions: string[],
): string {
  const hc = comboToHandClass(hand[0], hand[1]);
  const freqs = grid[hc];

  if (!freqs) {
    // Default to the first action (usually fold or check)
    return actions[0] || 'fold';
  }

  const totalFreq = Object.values(freqs).reduce((s, v) => s + v, 0);
  if (totalFreq < 0.001) return actions[0] || 'fold';

  let roll = Math.random() * totalFreq;
  for (const action of actions) {
    const f = freqs[action] || 0;
    roll -= f;
    if (roll <= 0) return action;
  }

  return actions[actions.length - 1] || 'fold';
}

/**
 * Create a shuffled deck, excluding dead cards.
 */
export function createDeck(deadCards: string[] = []): string[] {
  const dead = new Set(deadCards.map((c) => c.toLowerCase()));
  const deck = allCards().filter((c) => !dead.has(c.toLowerCase()));

  // Fisher-Yates shuffle
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [deck[i], deck[j]] = [deck[j], deck[i]];
  }

  return deck;
}

/**
 * Deal N cards from a shuffled deck.
 */
export function dealCards(deck: string[], n: number): string[] {
  return deck.splice(0, n);
}
