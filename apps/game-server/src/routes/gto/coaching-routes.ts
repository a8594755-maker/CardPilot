/**
 * Coaching API Routes
 *
 * ── Pre-computed (frontend sends policy/qValues) ──
 * POST /evaluate      — evaluate a single decision point
 * POST /review        — analyze a complete hand history
 *
 * ── Real-time neural network inference ──
 * POST /realtime      — game state + user action → ΔEV feedback
 * POST /infer         — game state → policy + Q-values (no evaluation)
 * POST /realtime/hand — full hand history → per-street feedback
 *
 * ── Drills & leaks ──
 * POST /drill/generate — generate practice scenarios
 * POST /drill/evaluate — evaluate user's drill answer
 * GET  /leaks         — get leak detection results
 * GET  /model/status  — check if model is loaded
 */

import { Router, type Request, type Response } from 'express';
import { evaluateDecision, reviewHand } from '../../services/gto/coaching-service.js';
import { detectLeaks, type DecisionRecord } from '../../services/gto/leak-detector.js';
import {
  generateDrills,
  evaluateDrill,
  type DrillConfig,
} from '../../services/gto/drill-generator.js';
import { getCoachingOracle, getModelPath } from '../../services/gto/coaching-oracle-manager.js';
import {
  cardToIndex,
  translateBetSize,
  actionToIndex,
  indexToAction,
  actionToHistoryToken,
  type CoachingInput,
} from '@cardpilot/cfr-solver';

// ── Helpers ──

/** Standard bet size fractions for each category. */
const BET_FRACTIONS = [0.25, 0.33, 0.5, 0.75, 1.0, 1.5];
const RAISE_FRACTIONS = [0.25, 0.33, 0.5, 0.75, 1.0, 1.5];

/**
 * Parse card strings ("Ah", "Ks") to 0-51 indices.
 * Accepts both individual cards and space/comma-separated strings.
 */
function parseCards(cards: string | string[]): number[] {
  const arr = Array.isArray(cards) ? cards : cards.split(/[\s,]+/).filter(Boolean);
  return arr.map((c) => cardToIndex(c.trim()));
}

/**
 * Convert user-facing action description to a CoachingInput and action index.
 *
 * Accepts:
 *   - Direct action name: "fold", "check", "call", "bet_2", "raise_3", "allin"
 *   - Human bet size: "bet 42%" or "raise 60%" → interpolated to nearest actions
 *   - Action index: 0-15
 */
function resolveUserAction(action: string | number): {
  actionIndex: number;
  interpolation?: { actions: Array<{ action: string; weight: number }> };
} {
  // Numeric index
  if (typeof action === 'number') {
    return { actionIndex: Math.max(0, Math.min(15, action)) };
  }

  // Direct action name (e.g. "fold", "bet_2")
  const directIdx = actionToIndex(action);
  if (directIdx >= 0) {
    return { actionIndex: directIdx };
  }

  // Human bet description: "bet 42%" or "raise 60%"
  const betMatch = action.match(/^(bet|raise)\s+([\d.]+)%?$/i);
  if (betMatch) {
    const isRaise = betMatch[1].toLowerCase() === 'raise';
    const fraction = parseFloat(betMatch[2]) / 100;
    const fractions = isRaise ? RAISE_FRACTIONS : BET_FRACTIONS;
    const translated = translateBetSize(fraction, fractions, isRaise);

    // Use the highest-weight action as the primary
    const primary = translated.actions.reduce(
      (a: { action: string; weight: number }, b: { action: string; weight: number }) =>
        a.weight > b.weight ? a : b,
    );
    return {
      actionIndex: actionToIndex(primary.action),
      interpolation: translated,
    };
  }

  // Fallback: treat as action name
  return { actionIndex: Math.max(0, actionToIndex(action)) };
}

/**
 * Build a CoachingInput from the API request body.
 */
function buildCoachingInput(body: RealtimeRequestBody): CoachingInput {
  const hole = parseCards(body.holeCards) as [number, number];
  const board = body.boardCards ? parseCards(body.boardCards) : [];
  const pot = body.pot;
  const stack = body.stack;
  const spr = pot > 0 ? stack / pot : 20;
  const facingBet = body.facingBet ?? 0;

  // Determine street from board length
  let street: number;
  if (body.street != null) {
    street =
      typeof body.street === 'number'
        ? body.street
        : ({ flop: 0, turn: 1, river: 2 }[body.street.toLowerCase()] ?? 0);
  } else {
    street = board.length <= 3 ? 0 : board.length === 4 ? 1 : 2;
  }

  // Position: accept number (0-5) or string ("BTN", "BB", etc.)
  let position: number;
  if (typeof body.position === 'number') {
    position = body.position;
  } else {
    const posMap: Record<string, number> = { SB: 0, BB: 1, UTG: 2, MP: 3, HJ: 3, CO: 4, BTN: 5 };
    position = posMap[body.position?.toUpperCase() ?? ''] ?? 0;
  }

  // Action history: accept token IDs or action name strings
  let actionHistory: number[];
  if (body.actionHistory && body.actionHistory.length > 0) {
    if (typeof body.actionHistory[0] === 'number') {
      actionHistory = body.actionHistory as number[];
    } else {
      actionHistory = (body.actionHistory as string[]).map((a) => {
        if (a === '/') return 18; // street separator
        return actionToHistoryToken(a);
      });
    }
  } else {
    actionHistory = [];
  }

  // Legal mask: if not provided, infer from game state
  let legalMask: number[];
  if (body.legalMask) {
    legalMask = body.legalMask;
  } else {
    // Default: fold/check/call always legal, all bets/raises/allin legal
    legalMask = new Array(16).fill(1);
    // If facing a bet, check is not legal; if not facing, fold and call are not legal
    if (facingBet > 0) {
      legalMask[1] = 0; // can't check when facing bet
    } else {
      legalMask[0] = 0; // can't fold when not facing bet
      legalMask[2] = 0; // can't call when not facing bet
    }
  }

  return {
    hole,
    board,
    position,
    street,
    pot,
    stack,
    spr,
    facingBet,
    actionHistory,
    legalMask,
  };
}

/** Shared request body shape for realtime endpoints. */
interface RealtimeRequestBody {
  holeCards: string | string[]; // "Ah Kd" or ["Ah", "Kd"]
  boardCards?: string | string[]; // "Qh Jc Ts" or ["Qh", "Jc", "Ts"]
  pot: number; // in BB
  stack: number; // effective stack in BB
  position: number | string; // 0-5 or "BTN"/"BB"/etc.
  street?: number | string; // 0/1/2 or "flop"/"turn"/"river"
  facingBet?: number; // in BB, default 0
  actionHistory?: (number | string)[]; // token IDs or action names
  legalMask?: number[]; // 16-dim, 1=legal
}

// In-memory storage for reviewed decisions (per-session; production would use a DB)
const reviewedDecisions: DecisionRecord[] = [];

export function createCoachingRouter(): Router {
  const router = Router();

  // ════════════════════════════════════════════════════════════════════
  // REAL-TIME NEURAL NETWORK INFERENCE ROUTES
  // ════════════════════════════════════════════════════════════════════

  // ── GET /model/status ──
  // Check if the coaching model is loaded and ready
  router.get('/model/status', async (_req: Request, res: Response) => {
    try {
      const modelPath = getModelPath();
      if (!modelPath) {
        // Try loading (lazy init)
        try {
          const oracle = await getCoachingOracle();
          return res.json({
            loaded: true,
            provider: oracle.provider,
            modelPath: getModelPath(),
          });
        } catch (err: any) {
          return res.json({
            loaded: false,
            error: err.message,
          });
        }
      }
      const oracle = await getCoachingOracle();
      return res.json({
        loaded: true,
        provider: oracle.provider,
        modelPath,
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /infer ──
  // Raw inference: game state → policy + Q-values + embedding
  // Use this to power the frontend strategy bar without evaluating a user action.
  router.post('/infer', async (req: Request, res: Response) => {
    try {
      const bodies: RealtimeRequestBody[] = Array.isArray(req.body) ? req.body : [req.body];

      if (bodies.length === 0) {
        return res.status(400).json({ error: 'Empty request body' });
      }
      for (const b of bodies) {
        if (!b.holeCards || b.pot == null || b.stack == null) {
          return res.status(400).json({ error: 'Missing required fields: holeCards, pot, stack' });
        }
      }

      const oracle = await getCoachingOracle();
      const inputs = bodies.map(buildCoachingInput);
      const results = await oracle.inferBatch(inputs);

      const response = results.map(
        (
          r: { policy: Float32Array; qValues: Float32Array; embedding: Float32Array },
          i: number,
        ) => {
          // Build human-readable policy map (only legal actions)
          const mask = inputs[i].legalMask;
          const policy: Record<string, number> = {};
          const qValues: Record<string, number> = {};
          let bestIdx = -1;
          let bestEV = -Infinity;

          for (let j = 0; j < 16; j++) {
            if (mask[j] > 0) {
              const name = indexToAction(j);
              policy[name] = r.policy[j];
              qValues[name] = r.qValues[j] * 10; // scale to BB (model uses /10 normalization)
              if (r.qValues[j] > bestEV) {
                bestEV = r.qValues[j];
                bestIdx = j;
              }
            }
          }

          return {
            policy,
            qValues,
            bestAction: bestIdx >= 0 ? indexToAction(bestIdx) : 'unknown',
            bestActionEV: bestEV * 10,
            embedding: Array.from(r.embedding),
            raw: {
              policy: Array.from(r.policy),
              qValues: Array.from(r.qValues),
            },
          };
        },
      );

      return res.json(Array.isArray(req.body) ? response : response[0]);
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /realtime ──
  // Full pipeline: game state + user action → ΔEV feedback + GTO policy
  router.post('/realtime', async (req: Request, res: Response) => {
    try {
      const { userAction, ...gameState } = req.body;

      if (
        !gameState.holeCards ||
        gameState.pot == null ||
        gameState.stack == null ||
        userAction == null
      ) {
        return res.status(400).json({
          error: 'Missing required fields: holeCards, pot, stack, userAction',
        });
      }

      const oracle = await getCoachingOracle();
      const input = buildCoachingInput(gameState);
      const { actionIndex, interpolation } = resolveUserAction(userAction);

      // Run inference
      const inference = await oracle.infer(input);
      const feedback = evaluateDecision(inference, actionIndex, input.legalMask, input.pot);

      // If the user action was interpolated (off-tree bet size), compute blended ΔEV
      let interpolatedDeltaEV: number | undefined;
      if (interpolation && interpolation.actions.length > 1) {
        interpolatedDeltaEV = 0;
        for (const { action, weight } of interpolation.actions) {
          const idx = actionToIndex(action);
          if (idx >= 0 && input.legalMask[idx] > 0) {
            const ev = inference.qValues[idx] * 10;
            interpolatedDeltaEV += weight * (ev - feedback.bestActionEV);
          }
        }
      }

      // Store for leak detection
      reviewedDecisions.push({
        embedding: inference.embedding,
        deltaEV: interpolatedDeltaEV ?? feedback.deltaEV,
        userAction: typeof userAction === 'string' ? userAction : indexToAction(actionIndex),
        bestAction: feedback.bestAction,
        potSize: input.pot,
        street: ['flop', 'turn', 'river'][input.street] ?? 'flop',
        position: input.position,
        spr: input.spr,
        facingBet: input.facingBet,
        holeCards:
          typeof gameState.holeCards === 'string'
            ? gameState.holeCards
            : (gameState.holeCards as string[]).join(' '),
        boardCards: gameState.boardCards
          ? typeof gameState.boardCards === 'string'
            ? gameState.boardCards
            : (gameState.boardCards as string[]).join(' ')
          : undefined,
      });

      return res.json({
        ...feedback,
        ...(interpolation ? { interpolation, interpolatedDeltaEV } : {}),
        embedding: Array.from(inference.embedding),
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /realtime/hand ──
  // Review a complete hand using the neural network
  router.post('/realtime/hand', async (req: Request, res: Response) => {
    try {
      const { decisions } = req.body;

      if (!decisions || !Array.isArray(decisions) || decisions.length === 0) {
        return res.status(400).json({ error: 'Missing or empty decisions array' });
      }

      const oracle = await getCoachingOracle();

      const inputs = decisions.map((d: any) => {
        const { userAction, ...gameState } = d;
        return {
          input: buildCoachingInput(gameState),
          userActionIndex: resolveUserAction(userAction).actionIndex,
          street: ['flop', 'turn', 'river'][buildCoachingInput(gameState).street] ?? 'flop',
          history: '', // could be derived from actionHistory
          userAction:
            typeof userAction === 'string'
              ? userAction
              : indexToAction(resolveUserAction(userAction).actionIndex),
        };
      });

      const review = await reviewHand(oracle, inputs);

      return res.json(review);
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ════════════════════════════════════════════════════════════════════
  // LEGACY PRE-COMPUTED ROUTES (frontend sends policy/qValues directly)
  // ════════════════════════════════════════════════════════════════════

  // ── POST /evaluate ──
  // Evaluate a single decision point (without full model — uses pre-computed data)
  router.post('/evaluate', async (req: Request, res: Response) => {
    try {
      const { policy, qValues, legalMask, userActionIndex, potSize, embedding, metadata } =
        req.body;

      if (!policy || !qValues || !legalMask || userActionIndex == null || !potSize) {
        return res.status(400).json({ error: 'Missing required fields' });
      }

      const inference = {
        policy: new Float32Array(policy),
        qValues: new Float32Array(qValues),
        embedding: new Float32Array(embedding ?? new Array(64).fill(0)),
      };

      const feedback = evaluateDecision(inference, userActionIndex, legalMask, potSize);

      // Store for leak detection if embedding is provided
      if (embedding && metadata) {
        reviewedDecisions.push({
          embedding: new Float32Array(embedding),
          deltaEV: feedback.deltaEV,
          userAction: metadata.userAction ?? 'unknown',
          bestAction: feedback.bestAction,
          potSize,
          street: metadata.street ?? 'flop',
          position: metadata.position ?? 0,
          spr: metadata.spr ?? 10,
          facingBet: metadata.facingBet ?? 0,
          holeCards: metadata.holeCards,
          boardCards: metadata.boardCards,
        });
      }

      return res.json(feedback);
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /review ──
  // Analyze a complete hand history (batch of decisions)
  router.post('/review', async (req: Request, res: Response) => {
    try {
      const { decisions } = req.body;

      if (!decisions || !Array.isArray(decisions) || decisions.length === 0) {
        return res.status(400).json({ error: 'Missing or empty decisions array' });
      }

      const feedbacks = decisions.map((d: any) => {
        const inference = {
          policy: new Float32Array(d.policy),
          qValues: new Float32Array(d.qValues),
          embedding: new Float32Array(d.embedding ?? new Array(64).fill(0)),
        };
        return {
          street: d.street,
          history: d.history,
          userAction: d.userAction,
          feedback: evaluateDecision(inference, d.userActionIndex, d.legalMask, d.potSize),
        };
      });

      const totalEVLost = feedbacks.reduce(
        (sum: number, f: any) => sum + Math.abs(Math.min(0, f.feedback.deltaEV)),
        0,
      );
      const avgPctPot =
        feedbacks.length > 0
          ? feedbacks.reduce(
              (sum: number, f: any) =>
                sum + Math.abs(f.feedback.deltaEV) / Math.max(f.feedback.potSize, 0.01),
              0,
            ) / feedbacks.length
          : 0;
      const handScore = Math.max(0, Math.min(100, 100 * (1 - avgPctPot)));

      return res.json({
        decisions: feedbacks,
        handScore,
        totalEVLost,
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── GET /leaks ──
  // Get leak detection results from accumulated reviewed decisions
  router.get('/leaks', async (req: Request, res: Response) => {
    try {
      const k = parseInt((req.query.k as string) ?? '15', 10);
      const minCluster = parseInt((req.query.minCluster as string) ?? '5', 10);

      const report = detectLeaks(reviewedDecisions, k, minCluster);
      report.handsReviewed = reviewedDecisions.length;

      // Serialize centroids to arrays for JSON
      return res.json({
        ...report,
        leaks: report.leaks.map((l) => ({
          ...l,
          centroid: Array.from(l.centroid),
        })),
      });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /drill/generate ──
  // Generate practice scenarios targeting identified leaks
  router.post('/drill/generate', async (req: Request, res: Response) => {
    try {
      const difficulty = req.body.difficulty ?? 'medium';
      const stackDepth = (req.body.stackDepth ?? 100) as 30 | 60 | 100 | 200;
      const count = req.body.count ?? 10;

      // Get current leak clusters (if any)
      const report = detectLeaks(reviewedDecisions);
      const focusLeaks = report.leaks.slice(0, 5); // top 5 leaks

      const config: DrillConfig = {
        focusLeaks,
        difficulty,
        stackDepth,
        count,
      };

      const scenarios = generateDrills(config);
      return res.json({ scenarios, leaksUsed: focusLeaks.length });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── POST /drill/evaluate ──
  // Evaluate user's answer to a drill scenario
  router.post('/drill/evaluate', async (req: Request, res: Response) => {
    try {
      const { scenario, userAction } = req.body;

      if (!scenario || !userAction) {
        return res.status(400).json({ error: 'Missing scenario or userAction' });
      }

      return res.json(evaluateDrill(scenario, userAction));
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  // ── DELETE /leaks ──
  // Reset accumulated decision records
  router.delete('/leaks', async (_req: Request, res: Response) => {
    try {
      const count = reviewedDecisions.length;
      reviewedDecisions.length = 0;
      return res.json({ cleared: count });
    } catch (err) {
      return res.status(500).json({ error: String(err) });
    }
  });

  return router;
}

export default createCoachingRouter();
