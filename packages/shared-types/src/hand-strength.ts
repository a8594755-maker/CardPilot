type Rank = "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "T" | "J" | "Q" | "K" | "A";

type ParsedCard = {
  rank: Rank;
  suit: string;
  value: number;
};

const RANK_VALUE: Record<Rank, number> = {
  "2": 2,
  "3": 3,
  "4": 4,
  "5": 5,
  "6": 6,
  "7": 7,
  "8": 8,
  "9": 9,
  T: 10,
  J: 11,
  Q: 12,
  K: 13,
  A: 14,
};

function parseCard(card: string): ParsedCard | null {
  if (typeof card !== "string" || card.length < 2) return null;
  const rank = card[0] as Rank;
  const suit = card[1];
  if (!(rank in RANK_VALUE)) return null;
  return { rank, suit, value: RANK_VALUE[rank] };
}

function countByRank(cards: ParsedCard[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const card of cards) {
    counts.set(card.value, (counts.get(card.value) ?? 0) + 1);
  }
  return counts;
}

function hasStraight(values: number[]): boolean {
  const uniq = [...new Set(values)].sort((a, b) => a - b);
  const withWheel = uniq.includes(14) ? [1, ...uniq] : uniq;
  let streak = 1;
  for (let i = 1; i < withWheel.length; i += 1) {
    const diff = withWheel[i] - withWheel[i - 1];
    if (diff === 1) {
      streak += 1;
      if (streak >= 5) return true;
    } else if (diff > 1) {
      streak = 1;
    }
  }
  return false;
}

function hasFlush(cards: ParsedCard[]): boolean {
  const suitCounts = new Map<string, number>();
  for (const card of cards) {
    suitCounts.set(card.suit, (suitCounts.get(card.suit) ?? 0) + 1);
  }
  return [...suitCounts.values()].some((count) => count >= 5);
}

function hasFlushDraw(cards: ParsedCard[]): boolean {
  const suitCounts = new Map<string, number>();
  for (const card of cards) {
    suitCounts.set(card.suit, (suitCounts.get(card.suit) ?? 0) + 1);
  }
  return [...suitCounts.values()].some((count) => count === 4);
}

function straightDrawLabel(values: number[]): "Open-ended straight draw" | "Gutshot straight draw" | null {
  const uniq = [...new Set(values)].sort((a, b) => a - b);
  const allValues = uniq.includes(14) ? [1, ...uniq] : uniq;
  const set = new Set(allValues);

  let hasOpenEnded = false;
  let hasGutshot = false;

  for (let start = 1; start <= 10; start += 1) {
    const seq = [start, start + 1, start + 2, start + 3, start + 4];
    const hits = seq.filter((v) => set.has(v));
    if (hits.length !== 4) continue;

    const missing = seq.find((v) => !set.has(v));
    if (missing == null) continue;
    if (missing === seq[0] || missing === seq[4]) {
      hasOpenEnded = true;
    } else {
      hasGutshot = true;
    }
  }

  if (hasOpenEnded) return "Open-ended straight draw";
  if (hasGutshot) return "Gutshot straight draw";
  return null;
}

export function describeHandStrength(holeCards: string[], boardCards: string[]): string {
  const parsedHole = holeCards.map(parseCard).filter((c): c is ParsedCard => c !== null);
  const parsedBoard = boardCards.map(parseCard).filter((c): c is ParsedCard => c !== null);
  const all = [...parsedHole, ...parsedBoard];

  if (parsedHole.length < 2) return "No hand data";
  if (parsedBoard.length === 0) return "No board yet";

  const values = all.map((c) => c.value);
  const rankCounts = [...countByRank(all).values()].sort((a, b) => b - a);

  const flush = hasFlush(all);
  const straight = hasStraight(values);

  if (flush && straight) return "Straight flush draw complete";
  if (rankCounts[0] === 4) return "Quads";
  if (rankCounts[0] === 3 && rankCounts[1] === 2) return "Full house";
  if (flush) return "Flush";
  if (straight) return "Straight";
  if (rankCounts[0] === 3) return "Trips";
  if (rankCounts[0] === 2 && rankCounts[1] === 2) return "Two pair";

  const boardTop = Math.max(...parsedBoard.map((c) => c.value));
  const holePairsTop = parsedHole.some((card) => card.value === boardTop)
    && rankCounts[0] === 2;
  if (holePairsTop) return "Top pair";
  if (rankCounts[0] === 2) return "Pair";

  if (parsedBoard.length < 5) {
    const drawParts: string[] = [];
    if (hasFlushDraw(all)) drawParts.push("Flush draw");
    const straightDraw = straightDrawLabel(values);
    if (straightDraw) drawParts.push(straightDraw);
    if (drawParts.length > 0) return drawParts.join(" + ");
  }

  return "High card";
}
