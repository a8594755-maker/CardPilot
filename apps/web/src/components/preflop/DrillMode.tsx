// Drill Mode — interactive quiz for preflop GTO training.
// Random spot + hand → user picks action → instant feedback.

import { memo, useState, useCallback, useEffect, useRef } from 'react';
import type { SolutionIndex, SpotSolution } from '../../data/preflop-loader';
import {
  loadSpot,
  RANKS,
  handClassAt,
  blendActionColors,
  getActionColor,
  getActionLabel,
  dominantAction,
  type Position,
  type ScenarioType,
} from '../../data/preflop-loader';

// ── Types ──

interface DrillQuestion {
  spot: SpotSolution;
  handClass: string;
  correctAction: string;
  correctFreq: number;
  isMixed: boolean;
}

interface DrillResult {
  question: DrillQuestion;
  userAction: string;
  isCorrect: boolean;
  isMixedCorrect: boolean; // user picked an action that's part of the mix
}

export interface DrillSettings {
  scenarios: ScenarioType[];
  positions: Position[];
  difficulty: 'easy' | 'medium' | 'hard' | 'all';
}

const DEFAULT_SETTINGS: DrillSettings = {
  scenarios: [],
  positions: [],
  difficulty: 'all',
};

// ── DrillStats persistence ──

interface DrillSessionStats {
  total: number;
  correct: number;
  mixedCorrect: number;
  streak: number;
  bestStreak: number;
  byScenario: Record<string, { total: number; correct: number }>;
}

function loadStats(): DrillSessionStats {
  try {
    const raw = localStorage.getItem('cardpilot_drill_stats');
    if (raw) return JSON.parse(raw);
  } catch {}
  return { total: 0, correct: 0, mixedCorrect: 0, streak: 0, bestStreak: 0, byScenario: {} };
}

function saveStats(stats: DrillSessionStats): void {
  try {
    localStorage.setItem('cardpilot_drill_stats', JSON.stringify(stats));
  } catch {}
}

// ── Component ──

interface DrillModeProps {
  index: SolutionIndex;
  config: string;
}

export const DrillMode = memo(function DrillMode({ index, config }: DrillModeProps) {
  const [question, setQuestion] = useState<DrillQuestion | null>(null);
  const [result, setResult] = useState<DrillResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<DrillSessionStats>(loadStats);
  const [settings, setSettings] = useState<DrillSettings>(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = useState(false);

  const spotCacheRef = useRef<Map<string, SpotSolution>>(new Map());

  const generateQuestion = useCallback(async () => {
    setLoading(true);
    setResult(null);

    // Filter spots by settings
    let candidates = index.spots;
    if (settings.scenarios.length > 0) {
      candidates = candidates.filter((s) =>
        settings.scenarios.includes(s.scenario as ScenarioType),
      );
    }
    if (settings.positions.length > 0) {
      candidates = candidates.filter((s) =>
        settings.positions.includes(s.heroPosition as Position),
      );
    }
    if (candidates.length === 0) candidates = index.spots;

    // Pick random spot
    const spotEntry = candidates[Math.floor(Math.random() * candidates.length)];

    // Load spot data
    let spotData = spotCacheRef.current.get(spotEntry.spot);
    if (!spotData) {
      spotData = await loadSpot(config, spotEntry.spot);
      spotCacheRef.current.set(spotEntry.spot, spotData);
    }

    // Pick random hand class, optionally filtered by difficulty
    const handClasses = Object.keys(spotData.grid);
    let validHands = handClasses;

    if (settings.difficulty !== 'all') {
      validHands = handClasses.filter((hc) => {
        const { freq } = dominantAction(spotData!.grid[hc]);
        if (settings.difficulty === 'easy') return freq >= 0.9;
        if (settings.difficulty === 'medium') return freq >= 0.6 && freq < 0.9;
        if (settings.difficulty === 'hard') return freq < 0.6;
        return true;
      });
      if (validHands.length === 0) validHands = handClasses;
    }

    const hc = validHands[Math.floor(Math.random() * validHands.length)];
    const freqs = spotData.grid[hc];
    const { action, freq } = dominantAction(freqs);

    setQuestion({
      spot: spotData,
      handClass: hc,
      correctAction: action,
      correctFreq: freq,
      isMixed: freq < 0.9,
    });
    setLoading(false);
  }, [index, config, settings]);

  // Auto-generate first question
  useEffect(() => {
    if (!question && !loading) {
      generateQuestion();
    }
  }, [question, loading, generateQuestion]);

  const handleAnswer = useCallback(
    (userAction: string) => {
      if (!question || result) return;

      const freqs = question.spot.grid[question.handClass];
      const userFreq = freqs[userAction] ?? 0;
      const isCorrect = userAction === question.correctAction;
      const isMixedCorrect = userFreq > 0.1; // part of the mix (>10%)

      const drillResult: DrillResult = {
        question,
        userAction,
        isCorrect,
        isMixedCorrect,
      };
      setResult(drillResult);

      // Update stats
      setStats((prev) => {
        const next = { ...prev };
        next.total++;
        if (isCorrect) next.correct++;
        if (isMixedCorrect) next.mixedCorrect++;
        next.streak = isCorrect || isMixedCorrect ? prev.streak + 1 : 0;
        next.bestStreak = Math.max(next.bestStreak, next.streak);

        const scenario = question.spot.scenario;
        if (!next.byScenario[scenario]) {
          next.byScenario[scenario] = { total: 0, correct: 0 };
        }
        next.byScenario[scenario].total++;
        if (isCorrect || isMixedCorrect) next.byScenario[scenario].correct++;

        saveStats(next);
        return next;
      });
    },
    [question, result],
  );

  const handleNext = useCallback(() => {
    setQuestion(null);
    setResult(null);
    generateQuestion();
  }, [generateQuestion]);

  const handleResetStats = useCallback(() => {
    const fresh: DrillSessionStats = {
      total: 0,
      correct: 0,
      mixedCorrect: 0,
      streak: 0,
      bestStreak: 0,
      byScenario: {},
    };
    setStats(fresh);
    saveStats(fresh);
  }, []);

  // Keyboard shortcuts: 1-5 for actions, Enter/Space for next
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Ignore if typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (result) {
        // After answering: Enter or Space → next hand
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleNext();
        }
      } else if (question && !loading) {
        // During question: number keys → pick action
        const num = parseInt(e.key, 10);
        if (num >= 1 && num <= question.spot.actions.length) {
          e.preventDefault();
          handleAnswer(question.spot.actions[num - 1]);
        }
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [question, result, loading, handleAnswer, handleNext]);

  const accuracy = stats.total > 0 ? Math.round((stats.mixedCorrect / stats.total) * 100) : 0;

  return (
    <div className="space-y-4">
      {/* Stats bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <StatPill label="Accuracy" value={`${accuracy}%`} />
          <StatPill label="Streak" value={`${stats.streak}`} />
          <StatPill label="Hands" value={`${stats.total}`} />
        </div>
        <div className="flex items-center gap-2">
          {stats.total > 0 && (
            <button
              className="text-[11px] text-red-400/60 hover:text-red-400 transition-colors"
              onClick={handleResetStats}
              title="Reset all drill statistics"
            >
              Reset
            </button>
          )}
          <button
            className="text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
            onClick={() => setShowSettings(!showSettings)}
          >
            {showSettings ? 'Hide Filters' : 'Filters'}
          </button>
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && <DrillSettingsPanel settings={settings} onChange={setSettings} />}

      {/* Question */}
      {loading && (
        <div className="glass-card p-8 text-center">
          <div className="text-slate-400 text-sm">Loading...</div>
        </div>
      )}

      {question && !loading && (
        <div className="space-y-3">
          {/* Scenario context */}
          <div className="bg-slate-800/60 rounded-lg px-3 py-2">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Spot</div>
            <div className="text-sm font-semibold text-white">
              {question.spot.heroPosition} — {formatScenarioLabel(question.spot)}
            </div>
            <div className="text-xs text-slate-400 mt-0.5">Pot: {question.spot.potSize} bb</div>
          </div>

          {/* Hand display */}
          <div className="text-center py-4">
            <div className="text-3xl font-bold text-white tracking-wide">{question.handClass}</div>
            <div className="text-xs text-slate-500 mt-1">
              {handClassDescription(question.handClass)}
            </div>
          </div>

          {/* Action buttons */}
          {!result && (
            <div>
              <div className="flex gap-2">
                {question.spot.actions.map((action, i) => (
                  <button
                    key={action}
                    className="flex-1 py-3 rounded-lg font-semibold text-sm text-white transition-all hover:brightness-110 active:scale-95"
                    style={{ backgroundColor: getActionColor(action) }}
                    onClick={() => handleAnswer(action)}
                  >
                    <span className="opacity-40 text-[10px] mr-1">{i + 1}</span>
                    {getActionLabel(action)}
                  </button>
                ))}
              </div>
              <div className="text-center text-[10px] text-slate-600 mt-1">
                Press 1-{question.spot.actions.length} to answer
              </div>
            </div>
          )}

          {/* Result feedback */}
          {result && (
            <div className="space-y-3">
              {/* Feedback banner */}
              <div
                className={`rounded-lg px-4 py-3 text-center ${
                  result.isCorrect
                    ? 'bg-green-500/20 border border-green-500/40'
                    : result.isMixedCorrect
                      ? 'bg-amber-500/20 border border-amber-500/40'
                      : 'bg-red-500/20 border border-red-500/40'
                }`}
              >
                <div
                  className={`text-sm font-bold ${
                    result.isCorrect
                      ? 'text-green-400'
                      : result.isMixedCorrect
                        ? 'text-amber-400'
                        : 'text-red-400'
                  }`}
                >
                  {result.isCorrect
                    ? 'Correct!'
                    : result.isMixedCorrect
                      ? 'Acceptable (Mixed Spot)'
                      : 'Incorrect'}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  GTO: {getActionLabel(question.correctAction)}{' '}
                  {(question.correctFreq * 100).toFixed(0)}%{question.isMixed && ' (mixed spot)'}
                </div>
              </div>

              {/* Full frequency breakdown */}
              <div className="space-y-1">
                {question.spot.actions.map((action) => {
                  const freq = question.spot.grid[question.handClass][action] ?? 0;
                  const isUserPick = action === result.userAction;
                  return (
                    <div key={action} className="flex items-center gap-2">
                      <span
                        className={`w-14 text-[11px] font-medium text-right truncate ${
                          isUserPick ? 'text-white' : 'text-slate-500'
                        }`}
                      >
                        {getActionLabel(action)}
                        {isUserPick && ' ←'}
                      </span>
                      <div className="flex-1 h-4 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.max(freq * 100, 0.5)}%`,
                            backgroundColor: getActionColor(action),
                            opacity: freq > 0.01 ? 1 : 0.2,
                          }}
                        />
                      </div>
                      <span className="w-10 text-right text-[11px] font-semibold tabular-nums text-slate-300">
                        {(freq * 100).toFixed(0)}%
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* Mini hand grid */}
              <MiniHandGrid spot={question.spot} highlightHand={question.handClass} />

              {/* Next button */}
              <button
                className="w-full py-2.5 rounded-lg bg-cyan-500/20 text-cyan-400 font-semibold text-sm hover:bg-cyan-500/30 transition-all"
                onClick={handleNext}
              >
                Next Hand → <span className="text-[10px] opacity-50 ml-1">Enter</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ── Sub-components ──

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-slate-500 uppercase">{label}</span>
      <span className="text-xs font-bold text-white tabular-nums">{value}</span>
    </div>
  );
}

const DrillSettingsPanel = memo(function DrillSettingsPanel({
  settings,
  onChange,
}: {
  settings: DrillSettings;
  onChange: (s: DrillSettings) => void;
}) {
  const difficulties: Array<{ id: DrillSettings['difficulty']; label: string }> = [
    { id: 'all', label: 'All' },
    { id: 'easy', label: 'Easy (Pure)' },
    { id: 'medium', label: 'Medium' },
    { id: 'hard', label: 'Hard (Mixed)' },
  ];

  const scenarios: Array<{ id: ScenarioType; label: string }> = [
    { id: 'RFI', label: 'RFI' },
    { id: 'facing_open', label: 'vs Open' },
    { id: 'facing_3bet', label: 'vs 3bet' },
    { id: 'facing_4bet', label: 'vs 4bet' },
  ];

  const positions: Position[] = ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'];

  return (
    <div className="bg-slate-800/40 rounded-lg p-3 space-y-3">
      {/* Difficulty */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Difficulty</div>
        <div className="flex flex-wrap gap-1">
          {difficulties.map((d) => (
            <button
              key={d.id}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                settings.difficulty === d.id
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                  : 'bg-slate-700/50 text-slate-400 border border-transparent hover:bg-slate-700'
              }`}
              onClick={() => onChange({ ...settings, difficulty: d.id })}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* Scenarios */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
          Scenarios (empty = all)
        </div>
        <div className="flex flex-wrap gap-1">
          {scenarios.map((s) => {
            const active = settings.scenarios.includes(s.id);
            return (
              <button
                key={s.id}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                  active
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-slate-700/50 text-slate-400 border border-transparent hover:bg-slate-700'
                }`}
                onClick={() => {
                  const next = active
                    ? settings.scenarios.filter((x) => x !== s.id)
                    : [...settings.scenarios, s.id];
                  onChange({ ...settings, scenarios: next });
                }}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Positions */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
          Positions (empty = all)
        </div>
        <div className="flex flex-wrap gap-1">
          {positions.map((p) => {
            const active = settings.positions.includes(p);
            return (
              <button
                key={p}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                  active
                    ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                    : 'bg-slate-700/50 text-slate-400 border border-transparent hover:bg-slate-700'
                }`}
                onClick={() => {
                  const next = active
                    ? settings.positions.filter((x) => x !== p)
                    : [...settings.positions, p];
                  onChange({ ...settings, positions: next });
                }}
              >
                {p}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
});

const MiniHandGrid = memo(function MiniHandGrid({
  spot,
  highlightHand,
}: {
  spot: SpotSolution;
  highlightHand: string;
}) {
  return (
    <div>
      <div className="text-[10px] text-slate-500 mb-1">Full Range</div>
      <div className="grid gap-[1px]" style={{ gridTemplateColumns: 'repeat(13, 1fr)' }}>
        {RANKS.map((_, row) =>
          RANKS.map((_, col) => {
            const hc = handClassAt(row, col);
            const freqs = spot.grid[hc];
            if (!freqs)
              return <div key={hc} className="aspect-square bg-slate-800/30 rounded-[1px]" />;
            const bg = blendActionColors(freqs);
            const foldFreq = freqs['fold'] ?? 0;
            const isHighlight = hc === highlightHand;
            return (
              <div
                key={hc}
                className={`aspect-square rounded-[1px] ${isHighlight ? 'ring-1 ring-white z-10' : ''}`}
                style={{
                  backgroundColor: bg,
                  opacity: foldFreq >= 0.99 ? 0.1 : foldFreq > 0.5 ? 0.25 : 0.55,
                }}
                title={hc}
              />
            );
          }),
        )}
      </div>
    </div>
  );
});

function formatScenarioLabel(spot: SpotSolution): string {
  if (spot.scenario === 'RFI') return 'Raise First In (Unopened)';
  if (spot.scenario === 'facing_open') return `Facing ${spot.villainPosition} Open`;
  if (spot.scenario === 'facing_3bet') return `Facing ${spot.villainPosition} 3-Bet`;
  if (spot.scenario === 'facing_4bet') return `Facing ${spot.villainPosition} 4-Bet`;
  return spot.scenario;
}

function handClassDescription(hc: string): string {
  if (hc.length === 2) return `Pocket ${hc[0]}s`;
  const suffix = hc[2] === 's' ? 'suited' : 'offsuit';
  return `${hc[0]}${hc[1]} ${suffix}`;
}
