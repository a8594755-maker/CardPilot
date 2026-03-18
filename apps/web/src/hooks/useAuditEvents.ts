/**
 * useAuditEvents hook
 *
 * Listens for GTO audit pipeline socket events and maintains
 * hand audit summaries + session leak summary in state.
 */

import { useEffect, useState } from 'react';
import type { Socket } from 'socket.io-client';
import type { HandAuditSummary, SessionLeakSummary } from '@cardpilot/shared-types';

export interface AuditState {
  /** Most recent hand audit summaries (newest first), capped at 50 */
  handAudits: HandAuditSummary[];
  /** Latest session leak summary (updated incrementally) */
  sessionLeak: SessionLeakSummary | null;
  /** Whether we've received at least one audit event */
  hasData: boolean;
}

export function useAuditEvents(socket: Socket | null, userId: string | null): AuditState {
  const [handAudits, setHandAudits] = useState<HandAuditSummary[]>([]);
  const [sessionLeak, setSessionLeak] = useState<SessionLeakSummary | null>(null);
  const [hasData, setHasData] = useState(false);

  useEffect(() => {
    if (!socket || !userId) return;

    const onHandAudit = (data: { userId: string; summary: HandAuditSummary }) => {
      if (data.userId !== userId) return;
      setHasData(true);
      setHandAudits((prev) => [data.summary, ...prev].slice(0, 50));
    };

    const onSessionLeak = (data: { userId: string; summary: SessionLeakSummary }) => {
      if (data.userId !== userId) return;
      setSessionLeak(data.summary);
    };

    socket.on('hand_audit_complete', onHandAudit);
    socket.on('session_leak_update', onSessionLeak);

    return () => {
      socket.off('hand_audit_complete', onHandAudit);
      socket.off('session_leak_update', onSessionLeak);
    };
  }, [socket, userId]);

  return { handAudits, sessionLeak, hasData };
}
