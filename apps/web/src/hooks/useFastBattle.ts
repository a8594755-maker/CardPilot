/**
 * useFastBattle hook
 *
 * Manages the client-side state for the "Infinite Fast Battle" training mode.
 * Listens for server socket events and exposes session state + controls.
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import type { Socket } from 'socket.io-client';
import type {
  FastBattleReport,
  FastBattleTableAssignedPayload,
  FastBattleHandResultPayload,
  FastBattleProgressPayload,
  FastBattleSessionStartedPayload,
  FastBattleSessionEndedPayload,
  FastBattleErrorPayload,
} from '@cardpilot/shared-types';

export type FastBattlePhase = 'setup' | 'playing' | 'switching' | 'report';

export interface FastBattleHandResultEntry {
  handId: string;
  handNumber: number;
  result: number;
  heroPosition: string;
  holeCards: [string, string];
  wentToShowdown: boolean;
  cumulativeResult: number;
  timestamp: number;
}

export interface FastBattleState {
  // Session
  sessionId: string | null;
  phase: FastBattlePhase;
  // Progress
  handsPlayed: number;
  targetHandCount: number;
  cumulativeResult: number;
  decisionsPerHour: number;
  // Current table
  currentTableId: string | null;
  currentRoomCode: string | null;
  currentHandNumber: number;
  // Hand results feed (for toast)
  lastHandResult: FastBattleHandResultEntry | null;
  handResults: FastBattleHandResultEntry[];
  // Report (populated when session ends)
  report: FastBattleReport | null;
  // Error
  error: string | null;
  // Actions
  startSession: (config: { targetHandCount: number; bigBlind?: number }) => void;
  endSession: () => void;
  warmup: () => void;
  resetToSetup: () => void;
}

export function useFastBattle(socket: Socket | null, _userId: string | null): FastBattleState {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [phase, setPhase] = useState<FastBattlePhase>('setup');
  const [handsPlayed, setHandsPlayed] = useState(0);
  const [targetHandCount, setTargetHandCount] = useState(0);
  const [cumulativeResult, setCumulativeResult] = useState(0);
  const [decisionsPerHour, setDecisionsPerHour] = useState(0);
  const [currentTableId, setCurrentTableId] = useState<string | null>(null);
  const [currentRoomCode, setCurrentRoomCode] = useState<string | null>(null);
  const [currentHandNumber, setCurrentHandNumber] = useState(0);
  const [lastHandResult, setLastHandResult] = useState<FastBattleHandResultEntry | null>(null);
  const [handResults, setHandResults] = useState<FastBattleHandResultEntry[]>([]);
  const [report, setReport] = useState<FastBattleReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Keep a ref to clear the toast timeout
  const toastTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const startSession = useCallback(
    (config: { targetHandCount: number; bigBlind?: number }) => {
      if (!socket) {
        console.warn('[fast-battle] startSession: no socket!');
        return;
      }
      console.log('[fast-battle] startSession', config, 'socketId=', socket.id);
      setError(null);
      setReport(null);
      setHandResults([]);
      setLastHandResult(null);
      setPhase('setup');
      socket.emit('fast_battle_start', {
        targetHandCount: config.targetHandCount,
        bigBlind: config.bigBlind ?? 3,
      });
    },
    [socket],
  );

  const endSession = useCallback(() => {
    if (!socket) return;
    socket.emit('fast_battle_end');
  }, [socket]);

  const warmup = useCallback(() => {
    if (!socket) return;
    socket.emit('fast_battle_warmup');
  }, [socket]);

  const resetToSetup = useCallback(() => {
    setPhase('setup');
    setSessionId(null);
    setCurrentTableId(null);
    setCurrentRoomCode(null);
    setError(null);
  }, []);

  useEffect(() => {
    if (!socket) return;

    const onSessionStarted = (data: FastBattleSessionStartedPayload) => {
      console.log('[fast-battle] session_started', data);
      setSessionId(data.sessionId);
      setTargetHandCount(data.targetHandCount);
      setHandsPlayed(0);
      setCumulativeResult(0);
      setPhase('switching');
    };

    const onTableAssigned = (data: FastBattleTableAssignedPayload) => {
      console.log('[fast-battle] table_assigned', data);
      setCurrentTableId(data.tableId);
      setCurrentRoomCode(data.roomCode);
      setCurrentHandNumber(data.handNumber);
      // Server already seated us and scheduled the deal — just switch UI
      setPhase('playing');
      // Belt-and-suspenders: request snapshot in case we missed the initial broadcast
      setTimeout(() => {
        socket.emit('request_table_snapshot', { tableId: data.tableId });
      }, 300);
    };

    const onHandResult = (data: FastBattleHandResultPayload) => {
      const entry: FastBattleHandResultEntry = {
        handId: data.handId,
        handNumber: data.handNumber,
        result: data.result,
        heroPosition: data.heroPosition,
        holeCards: data.holeCards,
        wentToShowdown: data.wentToShowdown,
        cumulativeResult: data.cumulativeResult,
        timestamp: Date.now(),
      };
      setLastHandResult(entry);
      setHandResults((prev) => [...prev, entry]);

      // Auto-clear toast after 3s
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
      toastTimeoutRef.current = setTimeout(() => setLastHandResult(null), 3000);
    };

    const onProgress = (data: FastBattleProgressPayload) => {
      setHandsPlayed(data.handsPlayed);
      setCumulativeResult(data.cumulativeResult);
      setDecisionsPerHour(data.decisionsPerHour);
    };

    const onSessionEnded = (data: FastBattleSessionEndedPayload) => {
      setReport(data.report);
      setPhase('report');
      setSessionId(null);
      setCurrentTableId(null);
      setCurrentRoomCode(null);
      // Persist session to localStorage
      try {
        const key = 'cardpilot_fb_sessions';
        const existing = JSON.parse(localStorage.getItem(key) ?? '[]');
        existing.push({ ...data.report, endedAt: Date.now() });
        // Keep last 50 sessions
        if (existing.length > 50) existing.splice(0, existing.length - 50);
        localStorage.setItem(key, JSON.stringify(existing));
      } catch {
        /* ignore storage failures */
      }
    };

    const onError = (data: FastBattleErrorPayload) => {
      console.warn('[fast-battle] error:', data);
      setError(data.message);
    };

    socket.on('fast_battle_session_started', onSessionStarted);
    socket.on('fast_battle_table_assigned', onTableAssigned);
    socket.on('fast_battle_hand_result', onHandResult);
    socket.on('fast_battle_progress', onProgress);
    socket.on('fast_battle_session_ended', onSessionEnded);
    socket.on('fast_battle_error', onError);

    return () => {
      socket.off('fast_battle_session_started', onSessionStarted);
      socket.off('fast_battle_table_assigned', onTableAssigned);
      socket.off('fast_battle_hand_result', onHandResult);
      socket.off('fast_battle_progress', onProgress);
      socket.off('fast_battle_session_ended', onSessionEnded);
      socket.off('fast_battle_error', onError);
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    };
  }, [socket]);

  return {
    sessionId,
    phase,
    handsPlayed,
    targetHandCount,
    cumulativeResult,
    decisionsPerHour,
    currentTableId,
    currentRoomCode,
    currentHandNumber,
    lastHandResult,
    handResults,
    report,
    error,
    startSession,
    endSession,
    warmup,
    resetToSetup,
  };
}
