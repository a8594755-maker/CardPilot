// ===== Bot Persona: session-fixed personality generation =====

import type { Mix } from './types.js';

export interface PersonaAnchors {
  looseTightCenter: number;          // [-1, 1]
  passiveAggressiveCenter: number;   // [-1, 1]
  bluffCenter: number;               // [0, 0.3]
  heroCallCenter: number;            // [0, 0.3]
  variance: number;                  // standard deviation for randomization
}

export interface BotPersona {
  looseTightBias: number;            // [-1, 1] positive = tight
  passiveAggressiveBias: number;     // [-1, 1] positive = aggressive
  bluffFrequency: number;            // [0, 0.3]
  heroCallTendency: number;          // [0, 0.3]
  raiseMultiplier: number;           // derived, [0.7, 1.4]
  callMultiplier: number;
  foldMultiplier: number;
  seed: string;
}

// ===== Default persona anchors per profile =====
export const PERSONA_ANCHORS: Record<string, PersonaAnchors> = {
  gto_balanced: {
    looseTightCenter: 0,
    passiveAggressiveCenter: 0,
    bluffCenter: 0.10,
    heroCallCenter: 0.10,
    variance: 0.10,
  },
  limp_fish: {
    looseTightCenter: -0.3,
    passiveAggressiveCenter: -0.4,
    bluffCenter: 0.03,
    heroCallCenter: 0.20,
    variance: 0.15,
  },
  tag: {
    looseTightCenter: 0.3,
    passiveAggressiveCenter: 0.3,
    bluffCenter: 0.08,
    heroCallCenter: 0.05,
    variance: 0.12,
  },
  lag: {
    looseTightCenter: -0.3,
    passiveAggressiveCenter: 0.4,
    bluffCenter: 0.20,
    heroCallCenter: 0.15,
    variance: 0.15,
  },
  nit: {
    looseTightCenter: 0.6,
    passiveAggressiveCenter: -0.2,
    bluffCenter: 0.02,
    heroCallCenter: 0.02,
    variance: 0.08,
  },
};

// ===== Simple seeded PRNG (Mulberry32) =====
function mulberry32(seed: number): () => number {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return h;
}

// Box-Muller transform for normal distribution
function normalRandom(rng: () => number, mean: number, sd: number): number {
  const u1 = rng();
  const u2 = rng();
  const z = Math.sqrt(-2 * Math.log(Math.max(u1, 1e-10))) * Math.cos(2 * Math.PI * u2);
  return mean + z * sd;
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

// ===== Generate a persona for a bot session =====
export function generatePersona(profileId: string, seed?: string): BotPersona {
  const actualSeed = seed ?? `${profileId}-${Date.now()}-${Math.random()}`;
  const rng = mulberry32(hashString(actualSeed));

  const anchors = PERSONA_ANCHORS[profileId] ?? PERSONA_ANCHORS['gto_balanced'];

  const looseTightBias = clamp(
    normalRandom(rng, anchors.looseTightCenter, anchors.variance),
    -1, 1,
  );
  const passiveAggressiveBias = clamp(
    normalRandom(rng, anchors.passiveAggressiveCenter, anchors.variance),
    -1, 1,
  );
  const bluffFrequency = clamp(
    normalRandom(rng, anchors.bluffCenter, anchors.variance * 0.5),
    0, 0.3,
  );
  const heroCallTendency = clamp(
    normalRandom(rng, anchors.heroCallCenter, anchors.variance * 0.5),
    0, 0.3,
  );

  // Derive multipliers from biases
  const raiseMultiplier = clamp(
    1.0 + passiveAggressiveBias * 0.3 - looseTightBias * 0.1,
    0.7, 1.4,
  );
  const foldMultiplier = clamp(
    1.0 + looseTightBias * 0.3 - passiveAggressiveBias * 0.1,
    0.7, 1.4,
  );
  const callMultiplier = clamp(
    1.0 - looseTightBias * 0.15 - passiveAggressiveBias * 0.15,
    0.7, 1.4,
  );

  return {
    looseTightBias,
    passiveAggressiveBias,
    bluffFrequency,
    heroCallTendency,
    raiseMultiplier,
    callMultiplier,
    foldMultiplier,
    seed: actualSeed,
  };
}

// ===== Apply persona to a mix =====
export function applyPersona(
  mix: Mix,
  persona: BotPersona,
  street: string,
  handStrength?: number,
  facingLargeBet?: boolean,
): Mix {
  let r = mix.raise * persona.raiseMultiplier;
  let c = mix.call * persona.callMultiplier;
  let f = mix.fold * persona.foldMultiplier;

  // Postflop bluff injection: low strength → add bluff raise frequency
  if (street !== 'PREFLOP' && handStrength != null && handStrength < 0.30) {
    r += persona.bluffFrequency * 0.15;
  }

  // Hero-call tendency: facing large bets → reduce fold, increase call
  if (facingLargeBet && persona.heroCallTendency > 0) {
    const shift = f * persona.heroCallTendency * 0.3;
    f -= shift;
    c += shift;
  }

  // Normalize
  const sum = r + c + f;
  if (sum <= 0) return { raise: 0, call: 0, fold: 1 };
  return { raise: r / sum, call: c / sum, fold: f / sum };
}
