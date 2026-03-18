// ===== Smooth mood/state drift system =====
// Session-level mood coefficient that drifts slowly over time

import type { BotPersona } from './persona.js';

export interface MoodState {
  value: number; // [-0.5, 0.5], 0 = neutral
  target: number; // slowly drifts toward this
  lastUpdateHand: number; // hand number of last mood update
  recentResults: number[]; // last 10 hand net results
}

export interface MoodMultipliers {
  raise: number;
  call: number;
  fold: number;
}

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

export function createMoodState(): MoodState {
  return {
    value: 0,
    target: 0,
    lastUpdateHand: 0,
    recentResults: [],
  };
}

export function updateMood(
  mood: MoodState,
  handResult: {
    net: number;
    wasShowdown: boolean;
    wasBadBeat: boolean; // lost at showdown with strong hand
  },
  currentHandNumber: number,
  bigBlind: number,
  persona: BotPersona | null,
): MoodState {
  const updated = { ...mood };

  // Track recent results
  updated.recentResults = [...mood.recentResults, handResult.net];
  if (updated.recentResults.length > 10) {
    updated.recentResults = updated.recentResults.slice(-10);
  }

  // Bad beat reaction: immediate spike
  if (handResult.wasBadBeat) {
    // Aggressive persona tilts aggressive, passive persona shuts down
    const tiltDirection = persona && persona.passiveAggressiveBias > 0 ? 0.15 : -0.15;
    updated.value = clamp(updated.value + tiltDirection, -0.5, 0.5);
  }

  // Only update drift every 5 hands
  if (currentHandNumber - mood.lastUpdateHand < 5) {
    return updated;
  }

  updated.lastUpdateHand = currentHandNumber;

  // Compute average recent results
  if (updated.recentResults.length >= 3) {
    const avg = updated.recentResults.reduce((a, b) => a + b, 0) / updated.recentResults.length;
    const bb = bigBlind || 1;

    if (avg > 2 * bb) {
      // Winning → drift slightly aggressive
      updated.target = clamp(updated.target + 0.05, -0.5, 0.5);
    } else if (avg < -2 * bb) {
      // Losing → drift slightly tight (self-protection)
      updated.target = clamp(updated.target - 0.05, -0.5, 0.5);
    }
  }

  // Exponential moving average toward target
  updated.value = updated.value * 0.85 + updated.target * 0.15;

  // Mean reversion: target slowly drifts back toward 0
  updated.target *= 0.95;

  // Clamp final value
  updated.value = clamp(updated.value, -0.5, 0.5);

  return updated;
}

export function getMoodMultipliers(mood: MoodState): MoodMultipliers {
  return {
    raise: 1.0 + mood.value * 0.15,
    call: 1.0 - Math.abs(mood.value) * 0.05,
    fold: 1.0 - mood.value * 0.15,
  };
}
