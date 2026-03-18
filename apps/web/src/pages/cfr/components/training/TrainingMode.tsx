import { memo, useState, useCallback, useMemo } from 'react';
import type { HandMapData } from '../../lib/cfr-api';
import { getActionLabels, type Street } from '../../lib/cfr-labels';
import { findSampleEntry, getAggregatedProbs } from '../../lib/cfr-computations';
import { PokerCardDisplay } from '../shared/PokerCardDisplay';
import { ActionColorBar } from '../shared/ActionColorBar';

interface QuizQuestion {
  boardId: number;
  flopCards: number[];
  handClass: string;
  player: number;
  street: Street;
  historyKey: string;
  bucket: number;
  gtoProbs: number[];
  actionLabels: string[];
}

interface QuizResult {
  question: QuizQuestion;
  chosenAction: number;
  isOptimal: boolean;
  score: number;
}

interface TrainingModeProps {
  indexed: Map<string, number[]>;
  prefixIndex: Map<string, string[]>;
  handMap: HandMapData | null;
  meta: { boardId: number; flopCards: number[]; bucketCount: number } | null;
  isV2: boolean;
  onBack: () => void;
}

export const TrainingMode = memo(function TrainingMode({
  indexed,
  prefixIndex,
  handMap,
  meta,
  isV2,
  onBack,
}: TrainingModeProps) {
  const [quizHistory, setQuizHistory] = useState<QuizResult[]>([]);
  const [currentQuiz, setCurrentQuiz] = useState<QuizQuestion | null>(null);
  const [chosenAction, setChosenAction] = useState<number | null>(null);
  const [showFeedback, setShowFeedback] = useState(false);

  const bucketCount = meta?.bucketCount || 50;

  // Generate a random quiz question
  const generateQuiz = useCallback(() => {
    if (!meta || !handMap || indexed.size === 0) return;

    const player = Math.random() < 0.5 ? 0 : 1;
    const street: Street = 'F';
    const historyKey = '';
    const boardId = meta.boardId;

    const prefix = `${street}|${boardId}|${player}|${historyKey}|`;
    const sample = findSampleEntry(indexed, prefix, bucketCount, isV2, prefixIndex);
    if (!sample) return;

    const numActions = sample.probs.length;
    const labels = getActionLabels(historyKey, numActions, street);
    const playerMap = player === 0 ? handMap.oop : handMap.ip;

    // Pick a random hand with non-trivial strategy
    const handClasses = Object.entries(playerMap);
    if (handClasses.length === 0) return;

    let bestHand: string | null = null;
    let bestBucket = 0;
    let bestProbs: number[] | null = null;

    // Try up to 20 random hands to find one with a mixed strategy
    for (let attempt = 0; attempt < 20; attempt++) {
      const [hc, bucket] = handClasses[Math.floor(Math.random() * handClasses.length)];
      const probs = getAggregatedProbs(indexed, prefix, bucket, isV2, prefixIndex);
      if (!probs) continue;

      // Check if strategy is interesting (not >90% one action)
      const maxProb = Math.max(...probs);
      if (maxProb < 0.9 || attempt >= 15) {
        bestHand = hc;
        bestBucket = bucket;
        bestProbs = probs;
        break;
      }
    }

    if (!bestHand || !bestProbs) return;

    setCurrentQuiz({
      boardId,
      flopCards: meta.flopCards,
      handClass: bestHand,
      player,
      street,
      historyKey,
      bucket: bestBucket,
      gtoProbs: bestProbs,
      actionLabels: labels,
    });
    setChosenAction(null);
    setShowFeedback(false);
  }, [meta, handMap, indexed, prefixIndex, bucketCount, isV2]);

  const handleAnswer = useCallback(
    (actionIdx: number) => {
      if (!currentQuiz || showFeedback) return;
      setChosenAction(actionIdx);
      setShowFeedback(true);

      const gtoFreq = currentQuiz.gtoProbs[actionIdx];
      const maxFreq = Math.max(...currentQuiz.gtoProbs);
      const isOptimal = gtoFreq === maxFreq;
      const score = Math.round(gtoFreq * 100);

      setQuizHistory((prev) => {
        const next = [
          ...prev,
          { question: currentQuiz, chosenAction: actionIdx, isOptimal, score },
        ];
        return next.length > 100 ? next.slice(-100) : next;
      });
    },
    [currentQuiz, showFeedback],
  );

  // Stats
  const stats = useMemo(() => {
    const total = quizHistory.length;
    const correct = quizHistory.filter((r) => r.isOptimal).length;
    const avgScore =
      total > 0 ? Math.round(quizHistory.reduce((s, r) => s + r.score, 0) / total) : 0;
    return {
      total,
      correct,
      accuracy: total > 0 ? Math.round((correct / total) * 100) : 0,
      avgScore,
    };
  }, [quizHistory]);

  if (!meta || !handMap) {
    return (
      <div className="text-center py-12">
        <p className="text-slate-400">Select a board first to start training.</p>
        <button
          onClick={onBack}
          className="mt-3 px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-slate-300 hover:text-white transition-colors"
        >
          Back to Viewer
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto space-y-5">
      {/* Board display */}
      <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-5 text-center">
        <div className="flex gap-2 justify-center mb-3">
          {meta.flopCards.map((c, i) => (
            <PokerCardDisplay key={i} cardIndex={c} size="lg" />
          ))}
        </div>

        {!currentQuiz ? (
          <button
            onClick={generateQuiz}
            className="px-6 py-3 bg-blue-500 rounded-lg text-white font-semibold hover:bg-blue-600 transition-colors"
          >
            Start Training
          </button>
        ) : (
          <>
            {/* Situation */}
            <div className="text-sm text-slate-400 mb-1">
              {currentQuiz.player === 0 ? 'OOP (Big Blind)' : 'IP (Button)'} · Flop
            </div>
            <div className="text-lg font-bold text-white mb-4">
              You hold: <span className="text-amber-400">{currentQuiz.handClass}</span>
            </div>

            {/* Action buttons */}
            <div className="text-sm text-slate-400 mb-3">What's the GTO play?</div>
            <div className="flex gap-2 justify-center flex-wrap">
              {currentQuiz.actionLabels.map((label, i) => {
                const isChosen = chosenAction === i;
                const gtoFreq = currentQuiz.gtoProbs[i];
                const maxFreq = Math.max(...currentQuiz.gtoProbs);
                const isGtoBest = gtoFreq === maxFreq && showFeedback;

                return (
                  <button
                    key={label}
                    onClick={() => handleAnswer(i)}
                    disabled={showFeedback}
                    className={`px-5 py-2.5 rounded-lg text-sm font-semibold transition-all border-2 ${
                      showFeedback
                        ? isGtoBest
                          ? 'border-emerald-500 bg-emerald-500/20 text-emerald-400'
                          : isChosen
                            ? 'border-red-500 bg-red-500/20 text-red-400'
                            : 'border-white/10 text-slate-500'
                        : 'border-white/15 text-white hover:border-blue-500 hover:bg-blue-500/10'
                    }`}
                  >
                    {label}
                    {showFeedback && (
                      <span className="block text-xs mt-0.5 opacity-75">
                        {(gtoFreq * 100).toFixed(0)}%
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {/* Feedback */}
            {showFeedback && chosenAction !== null && (
              <div className="mt-4">
                <div
                  className={`text-lg font-bold mb-2 ${
                    currentQuiz.gtoProbs[chosenAction] === Math.max(...currentQuiz.gtoProbs)
                      ? 'text-emerald-400'
                      : 'text-amber-400'
                  }`}
                >
                  {currentQuiz.gtoProbs[chosenAction] === Math.max(...currentQuiz.gtoProbs)
                    ? 'Correct!'
                    : `GTO frequency: ${(currentQuiz.gtoProbs[chosenAction] * 100).toFixed(0)}%`}
                </div>
                <ActionColorBar
                  labels={currentQuiz.actionLabels}
                  probs={currentQuiz.gtoProbs}
                  height={24}
                />
                <button
                  onClick={generateQuiz}
                  className="mt-4 px-6 py-2.5 bg-blue-500 rounded-lg text-white font-semibold hover:bg-blue-600 transition-colors"
                >
                  Next Question →
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {/* Stats */}
      {stats.total > 0 && (
        <div className="bg-[var(--cp-bg-surface)] border border-white/10 rounded-xl p-4">
          <div className="flex justify-around text-center">
            <div>
              <div className="text-xl font-bold text-white">
                {stats.correct}/{stats.total}
              </div>
              <div className="text-[11px] text-slate-500">Correct</div>
            </div>
            <div>
              <div className="text-xl font-bold text-emerald-400">{stats.accuracy}%</div>
              <div className="text-[11px] text-slate-500">Accuracy</div>
            </div>
            <div>
              <div className="text-xl font-bold text-amber-400">{stats.avgScore}</div>
              <div className="text-[11px] text-slate-500">Avg Score</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});
