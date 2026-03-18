// ===== Structured decision trace logging (JSONL) =====

import type { Mix } from './types.js';

export interface BoardTextureSummary {
  category: string;
  wetness: number;
  isPaired: boolean;
  hasFlushDraw: boolean;
  highCard: string;
}

export interface RaiseContextSummary {
  facingType: string;
  raiserPosition: string | null;
  raiseSizeBB: number;
  raiseSizeCategory: string;
  numCallers: number;
  isMultiway: boolean;
  spr: number;
}

export interface DecisionTrace {
  timestamp: string;
  handId: string;
  street: string;

  // Input context
  source: string; // 'advice' | 'fallback' | 'fallback+hand'
  holeCards: [string, string] | null;
  board: string[];
  handStrength: number | null;
  boardTexture: BoardTextureSummary | null;
  potOdds: number;
  pot: number;
  toCall: number;
  position: string;

  // Raise context
  raiseContext: RaiseContextSummary | null;

  // Active modifiers
  personaSeed: string;
  personaMultipliers: { raise: number; call: number; fold: number };
  moodValue: number;
  adaptiveAdj: { raise: number; call: number; fold: number };
  opponentAdj: { raise: number; call: number; fold: number } | null;

  // Mix pipeline snapshots
  baseMix: Mix;
  afterWeights: Mix;
  afterPersona: Mix;
  afterBoardTexture: Mix;
  afterAdaptive: Mix;
  afterOpponent: Mix;
  afterMood: Mix;
  isDonkSpot: boolean;
  donkGuardrailApplied: boolean;
  afterDonkGuardrail: Mix;
  afterLimp: Mix;
  afterMistake: Mix;

  // Output
  sampledAction: string;
  resolvedAction: string;
  raiseAmount: number | null;
  raiseSizeCategory: string | null;

  // Mistake
  mistakeApplied: boolean;
  mistakeDescription: string | null;
}

export function createEmptyTrace(): DecisionTrace {
  const emptyMix = { raise: 0, call: 0, fold: 0 };
  return {
    timestamp: new Date().toISOString(),
    handId: '',
    street: '',
    source: '',
    holeCards: null,
    board: [],
    handStrength: null,
    boardTexture: null,
    potOdds: 0,
    pot: 0,
    toCall: 0,
    position: '',
    raiseContext: null,
    personaSeed: '',
    personaMultipliers: { raise: 1, call: 1, fold: 1 },
    moodValue: 0,
    adaptiveAdj: { raise: 1, call: 1, fold: 1 },
    opponentAdj: null,
    baseMix: { ...emptyMix },
    afterWeights: { ...emptyMix },
    afterPersona: { ...emptyMix },
    afterBoardTexture: { ...emptyMix },
    afterAdaptive: { ...emptyMix },
    afterOpponent: { ...emptyMix },
    afterMood: { ...emptyMix },
    isDonkSpot: false,
    donkGuardrailApplied: false,
    afterDonkGuardrail: { ...emptyMix },
    afterLimp: { ...emptyMix },
    afterMistake: { ...emptyMix },
    sampledAction: '',
    resolvedAction: '',
    raiseAmount: null,
    raiseSizeCategory: null,
    mistakeApplied: false,
    mistakeDescription: null,
  };
}

export class TraceLogger {
  private buffer: DecisionTrace[] = [];
  private maxBuffer: number;
  private traceFile: string | null;
  private stdoutEnabled: boolean;

  constructor(maxBuffer = 100) {
    this.maxBuffer = maxBuffer;
    this.traceFile = process.env['BOT_TRACE_FILE'] ?? null;
    this.stdoutEnabled = process.env['BOT_TRACE_STDOUT'] === '1';
  }

  log(trace: DecisionTrace): void {
    this.buffer.push(trace);
    if (this.buffer.length > this.maxBuffer) {
      this.buffer.shift();
    }

    const line = JSON.stringify(trace);
    if (this.traceFile) {
      // Lazy file append
      import('fs')
        .then((fs) => {
          fs.appendFileSync(this.traceFile!, line + '\n');
        })
        .catch(() => {});
    } else if (this.stdoutEnabled) {
      console.log(`[TRACE] ${line}`);
    }
  }

  getRecentTraces(n: number): DecisionTrace[] {
    return this.buffer.slice(-n);
  }

  getSummary(): {
    totalDecisions: number;
    raiseCount: number;
    callCount: number;
    foldCount: number;
    checkCount: number;
    adviceUsed: number;
    fallbackUsed: number;
    mistakeCount: number;
    donkGuardrailCount: number;
  } {
    let raiseCount = 0,
      callCount = 0,
      foldCount = 0,
      checkCount = 0;
    let adviceUsed = 0,
      fallbackUsed = 0,
      mistakeCount = 0,
      donkGuardrailCount = 0;

    for (const t of this.buffer) {
      if (t.resolvedAction === 'raise') raiseCount++;
      else if (t.resolvedAction === 'call') callCount++;
      else if (t.resolvedAction === 'fold') foldCount++;
      else if (t.resolvedAction === 'check') checkCount++;

      if (t.source === 'advice') adviceUsed++;
      else fallbackUsed++;

      if (t.mistakeApplied) mistakeCount++;
      if (t.donkGuardrailApplied) donkGuardrailCount++;
    }

    return {
      totalDecisions: this.buffer.length,
      raiseCount,
      callCount,
      foldCount,
      checkCount,
      adviceUsed,
      fallbackUsed,
      mistakeCount,
      donkGuardrailCount,
    };
  }

  formatReasoning(trace: DecisionTrace): string {
    const str = trace.handStrength != null ? ` str=${trace.handStrength.toFixed(2)}` : '';
    const bt = trace.boardTexture
      ? ` board=${trace.boardTexture.category}(w=${trace.boardTexture.wetness})`
      : '';
    const rc = trace.raiseContext ? ` facing=${trace.raiseContext.facingType}` : '';
    const mood = trace.moodValue !== 0 ? ` mood=${trace.moodValue.toFixed(2)}` : '';
    const mistake = trace.mistakeApplied ? ` MISTAKE:${trace.mistakeDescription}` : '';
    const donk = trace.donkGuardrailApplied ? ' DONK_GUARD' : '';

    const fmtMix = (m: Mix) =>
      `R:${m.raise.toFixed(2)} C:${m.call.toFixed(2)} F:${m.fold.toFixed(2)}`;

    return (
      `src=${trace.source}${str}${bt}${rc}${mood}${mistake}${donk} ` +
      `base=(${fmtMix(trace.baseMix)}) final=(${fmtMix(trace.afterMistake)}) ` +
      `raw=${trace.sampledAction} → ${trace.resolvedAction}` +
      `${trace.raiseAmount != null ? ` amt=${trace.raiseAmount}` : ''}` +
      `${trace.raiseSizeCategory ? ` size=${trace.raiseSizeCategory}` : ''}`
    );
  }
}
