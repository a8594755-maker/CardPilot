import { readFileSync } from 'node:fs';

const RANKS = '23456789TJQKA';

interface UnknownRecord {
  [key: string]: unknown;
}

export interface GtoWizardRangeEntry {
  format: string;
  spot: string;
  hand: string;
  mix: Record<string, number>;
  notes?: string[];
}

function ensureObject(value: unknown, label: string): UnknownRecord {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value as UnknownRecord;
}

function ensureString(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function ensureFrequency(value: unknown, label: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${label} must be a finite number`);
  }
  if (value < 0 || value > 1) {
    throw new Error(`${label} must be in [0, 1]`);
  }
  return value;
}

function ensureHandClass(value: unknown, label: string): string {
  const hand = ensureString(value, label).toUpperCase();

  if (hand.length === 2) {
    if (!RANKS.includes(hand[0]) || !RANKS.includes(hand[1])) {
      throw new Error(`${label} has invalid ranks: ${hand}`);
    }
    if (hand[0] !== hand[1]) {
      throw new Error(`${label} must use suited/offsuit suffix for non-pair hands: ${hand}`);
    }
    return hand;
  }

  if (hand.length === 3) {
    if (!RANKS.includes(hand[0]) || !RANKS.includes(hand[1])) {
      throw new Error(`${label} has invalid ranks: ${hand}`);
    }
    if (hand[0] === hand[1]) {
      throw new Error(`${label} pair hands must not include suited/offsuit suffix: ${hand}`);
    }
    if (hand[2] !== 'S' && hand[2] !== 'O') {
      throw new Error(`${label} must end with "s" or "o": ${hand}`);
    }
    return hand[0] + hand[1] + hand[2].toLowerCase();
  }

  throw new Error(`${label} has invalid hand class length: ${hand}`);
}

function parseMix(value: unknown, label: string): Record<string, number> {
  const mixObj = ensureObject(value, label);
  const mix: Record<string, number> = {};

  for (const [action, freq] of Object.entries(mixObj)) {
    mix[action] = ensureFrequency(freq, `${label}.${action}`);
  }

  if (Object.keys(mix).length === 0) {
    throw new Error(`${label} must contain at least one action frequency`);
  }

  return mix;
}

function parseNotes(value: unknown, label: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) {
    throw new Error(`${label} must be an array of strings`);
  }
  const notes: string[] = [];
  for (let i = 0; i < value.length; i++) {
    notes.push(ensureString(value[i], `${label}[${i}]`));
  }
  return notes;
}

export function parseGtoWizardRangeJson(raw: unknown): GtoWizardRangeEntry[] {
  if (!Array.isArray(raw)) {
    throw new Error('GTO Wizard preflop payload must be an array');
  }

  return raw.map((entry, index) => {
    const obj = ensureObject(entry, `entry[${index}]`);
    return {
      format: ensureString(obj.format, `entry[${index}].format`),
      spot: ensureString(obj.spot, `entry[${index}].spot`),
      hand: ensureHandClass(obj.hand, `entry[${index}].hand`),
      mix: parseMix(obj.mix, `entry[${index}].mix`),
      notes: parseNotes(obj.notes, `entry[${index}].notes`),
    };
  });
}

export function loadGtoWizardRangeFile(filePath: string): GtoWizardRangeEntry[] {
  const raw = JSON.parse(readFileSync(filePath, 'utf-8')) as unknown;
  return parseGtoWizardRangeJson(raw);
}

/**
 * Expand a hand class (e.g. "AKs", "AKo", "AA") to card index combos.
 * Every combo is returned as [c1, c2] where c1 < c2.
 */
export function expandHandClassToCombos(handClass: string): Array<[number, number]> {
  const hand = ensureHandClass(handClass, 'handClass');
  const combos: Array<[number, number]> = [];

  if (hand.length === 2) {
    const rank = RANKS.indexOf(hand[0]);
    for (let s1 = 0; s1 < 4; s1++) {
      for (let s2 = s1 + 1; s2 < 4; s2++) {
        const c1 = rank * 4 + s1;
        const c2 = rank * 4 + s2;
        combos.push([c1, c2]);
      }
    }
    return combos;
  }

  const rankA = RANKS.indexOf(hand[0]);
  const rankB = RANKS.indexOf(hand[1]);
  const suited = hand[2] === 's';

  if (suited) {
    for (let suit = 0; suit < 4; suit++) {
      const c1 = rankA * 4 + suit;
      const c2 = rankB * 4 + suit;
      combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
    }
    return combos;
  }

  for (let suitA = 0; suitA < 4; suitA++) {
    for (let suitB = 0; suitB < 4; suitB++) {
      if (suitA === suitB) continue;
      const c1 = rankA * 4 + suitA;
      const c2 = rankB * 4 + suitB;
      combos.push([Math.min(c1, c2), Math.max(c1, c2)]);
    }
  }

  return combos;
}
