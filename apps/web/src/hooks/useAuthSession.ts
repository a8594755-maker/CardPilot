import { useEffect, useState, useCallback, useRef } from 'react';
import {
  getExistingSession,
  signOut,
  supabase,
  normalizeClientUserId,
  resetInvalidRefreshGuard,
  type AuthSession,
} from '../supabase';

export interface UseAuthSessionReturn {
  authSession: AuthSession | null;
  authLoading: boolean;
  userEmail: string | null;
  displayName: string;
  setDisplayName: (name: string) => void;
  handleLogout: () => Promise<void>;
  /** Stable ref to the latest access token (for socket auth) */
  socketAuthTokenRef: React.RefObject<string | undefined>;
  socketAuthUserId: string | undefined;
}

export function useAuthSession(showToast: (text: string) => void): UseAuthSessionReturn {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [userEmail, setUserEmail] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string>('Guest');

  const socketAuthTokenRef = useRef<string | undefined>(authSession?.accessToken);
  useEffect(() => {
    socketAuthTokenRef.current = authSession?.accessToken;
  }, [authSession?.accessToken]);

  // Check existing session on mount
  useEffect(() => {
    let alive = true;
    getExistingSession()
      .then((session) => {
        if (!alive) return;
        if (session) {
          setAuthSession(session);
          setUserEmail(session.email ?? null);
          setDisplayName(session.displayName || session.email?.split('@')[0] || 'Guest');
          showToast('Signed in');
        }
        setAuthLoading(false);
      })
      .catch(() => {
        if (!alive) return;
        setAuthLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []); // intentionally empty deps - run once on mount

  // Listen for Supabase auth changes
  useEffect(() => {
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_ev, session) => {
      if (session) {
        const meta = session.user.user_metadata;
        const dn =
          (typeof meta?.display_name === 'string' && meta.display_name) ||
          (typeof meta?.name === 'string' && meta.name) ||
          null;
        const isGuest = Boolean((session.user as { is_anonymous?: boolean }).is_anonymous);
        const s: AuthSession = {
          accessToken: session.access_token,
          userId: normalizeClientUserId(session.user.id, isGuest),
          email: session.user.email,
          displayName: dn,
          isGuest,
        };
        setAuthSession(s);
        setUserEmail(session.user.email ?? null);
        if (dn) setDisplayName(dn);
        resetInvalidRefreshGuard();
      } else {
        setAuthSession(null);
        setUserEmail(null);
      }
    });
    return () => {
      data.subscription.unsubscribe();
    };
  }, []);

  const handleLogout = useCallback(async () => {
    await signOut();
    setAuthSession(null);
    setUserEmail(null);
    setDisplayName('Guest');
  }, []);

  return {
    authSession,
    authLoading,
    userEmail,
    displayName,
    setDisplayName,
    handleLogout,
    socketAuthTokenRef,
    socketAuthUserId: authSession?.userId,
  };
}
