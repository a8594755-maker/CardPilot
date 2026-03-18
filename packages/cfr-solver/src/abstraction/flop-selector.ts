// Select representative flops using stratified sampling across board textures.
// Dimensions: high card rank × suit pattern × connectivity × paired
//
// From ~1,755 isomorphic flops, we select N (default 200) representative flops.

import { indexToRank } from './card-index.js';
import { enumerateIsomorphicFlops } from './suit-isomorphism.js';

export interface FlopDescriptor {
  cards: [number, number, number];
  canonical: string;
  highRank: number; // 0=2 ... 12=A
  suitPattern: 'rainbow' | 'two_tone' | 'monotone';
  connectivity: 'connected' | 'semi_connected' | 'disconnected';
  paired: boolean;
  textureKey: string; // combined classification key
}

/**
 * Classify a flop by its texture dimensions.
 */
function classifyFlop(
  cards: [number, number, number],
): Omit<FlopDescriptor, 'cards' | 'canonical'> {
  const ranks = cards.map(indexToRank).sort((a, b) => b - a);
  const suits = cards.map((c) => c & 3);

  // High card
  const highRank = ranks[0];

  // Suit pattern
  const uniqueSuits = new Set(suits).size;
  const suitPattern: FlopDescriptor['suitPattern'] =
    uniqueSuits === 1 ? 'monotone' : uniqueSuits === 2 ? 'two_tone' : 'rainbow';

  // Connectivity (gaps between sorted ranks)
  const gap1 = ranks[0] - ranks[1];
  const gap2 = ranks[1] - ranks[2];
  const maxGap = Math.max(gap1, gap2);
  const totalSpread = ranks[0] - ranks[2];

  const connectivity: FlopDescriptor['connectivity'] =
    totalSpread <= 4 && maxGap <= 2
      ? 'connected'
      : totalSpread <= 6
        ? 'semi_connected'
        : 'disconnected';

  // Paired
  const paired = ranks[0] === ranks[1] || ranks[1] === ranks[2];

  // High card tier (group into 5 tiers)
  const highTier =
    highRank >= 12
      ? 'A'
      : highRank >= 11
        ? 'K'
        : highRank >= 10
          ? 'Q'
          : highRank >= 8
            ? 'TJ'
            : highRank >= 6
              ? '89'
              : 'low';

  const textureKey = `${highTier}_${suitPattern}_${connectivity}${paired ? '_paired' : ''}`;

  return { highRank, suitPattern, connectivity, paired, textureKey };
}

/**
 * Select N representative flops using stratified sampling.
 * Distributes selections proportionally across texture classes.
 */
export function selectRepresentativeFlops(count: number = 200): FlopDescriptor[] {
  const allFlops = enumerateIsomorphicFlops();

  // Classify all flops
  const classified: FlopDescriptor[] = allFlops.map((f) => ({
    ...f,
    ...classifyFlop(f.cards),
  }));

  // Group by texture key
  const groups = new Map<string, FlopDescriptor[]>();
  for (const flop of classified) {
    const list = groups.get(flop.textureKey) || [];
    list.push(flop);
    groups.set(flop.textureKey, list);
  }

  // Stratified sampling: proportional allocation
  const totalFlops = classified.length;
  const selected: FlopDescriptor[] = [];

  // Sort groups by size (largest first) for stable ordering
  const sortedGroups = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);

  // First pass: allocate proportionally
  const allocations: Array<{ key: string; flops: FlopDescriptor[]; allocation: number }> = [];

  for (const [key, flops] of sortedGroups) {
    const proportion = flops.length / totalFlops;
    const allocation = Math.max(1, Math.round(proportion * count));
    allocations.push({ key, flops, allocation });
  }

  // Adjust to hit exact count
  const totalAllocated = allocations.reduce((s, a) => s + a.allocation, 0);
  if (totalAllocated > count) {
    // Trim from smallest allocations
    allocations.sort((a, b) => a.allocation - b.allocation);
    let excess = totalAllocated - count;
    for (const a of allocations) {
      if (excess <= 0) break;
      if (a.allocation > 1) {
        a.allocation--;
        excess--;
      }
    }
  }

  // Select from each group
  for (const { flops, allocation } of allocations) {
    // Select evenly spaced flops from sorted list
    const sorted = flops.sort((a, b) => a.highRank - b.highRank);
    const step = Math.max(1, Math.floor(sorted.length / allocation));
    for (let i = 0; i < allocation && i * step < sorted.length; i++) {
      selected.push(sorted[i * step]);
    }
  }

  // If we still need more, fill from remaining
  if (selected.length < count) {
    const selectedSet = new Set(selected.map((s) => s.canonical));
    for (const flop of classified) {
      if (selected.length >= count) break;
      if (!selectedSet.has(flop.canonical)) {
        selected.push(flop);
        selectedSet.add(flop.canonical);
      }
    }
  }

  return selected.slice(0, count);
}

/**
 * Print flop selection statistics.
 */
export function printFlopStats(flops: FlopDescriptor[]): void {
  console.log(`Selected ${flops.length} representative flops:`);

  // Count by suit pattern
  const byPattern: Record<string, number> = {};
  const byConn: Record<string, number> = {};
  let paired = 0;

  for (const f of flops) {
    byPattern[f.suitPattern] = (byPattern[f.suitPattern] || 0) + 1;
    byConn[f.connectivity] = (byConn[f.connectivity] || 0) + 1;
    if (f.paired) paired++;
  }

  console.log(`  Suit pattern: ${JSON.stringify(byPattern)}`);
  console.log(`  Connectivity: ${JSON.stringify(byConn)}`);
  console.log(`  Paired: ${paired}, Unpaired: ${flops.length - paired}`);
}
