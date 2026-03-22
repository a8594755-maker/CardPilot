import { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuthSafe } from './AuthContext';
import { debugLog } from '../lib/debug';
import { useToast } from './ToastContext';

// Use VITE_SERVER_URL if explicitly set; in dev mode use relative URL to go through Vite proxy
const SERVER =
  import.meta.env.VITE_SERVER_URL || (import.meta.env.DEV ? '/' : 'http://127.0.0.1:4000');

interface SocketContextType {
  socket: Socket | null;
  connected: boolean;
  reconnecting: boolean;
}

const SocketContext = createContext<SocketContextType | null>(null);

export function useSocket() {
  const context = useContext(SocketContext);
  if (!context) {
    throw new Error('useSocket must be used within a SocketProvider');
  }
  return context;
}

export function SocketProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const auth = useAuthSafe();
  const authSession = auth?.authSession ?? null;

  const [socket, setSocket] = useState<Socket | null>(null);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  const socketAuthTokenRef = useRef(authSession?.accessToken);
  const lastSocketConnectErrorToastRef = useRef(0);

  useEffect(() => {
    socketAuthTokenRef.current = authSession?.accessToken;
  }, [authSession?.accessToken]);

  useEffect(() => {
    if (!authSession?.userId) return;

    debugLog('[SOCKET] Connecting with userId:', authSession.userId);
    // Use same-origin in dev (via Vite proxy) to avoid CORS; explicit URL in prod
    const serverUrl = import.meta.env.DEV ? window.location.origin : SERVER;

    const s = io(serverUrl, {
      auth: {
        accessToken: socketAuthTokenRef.current,
        displayName: authSession.displayName || 'Guest',
        userId: authSession.userId,
      },
    });

    setSocket(s);

    // Expose socket for e2e testing
    if (import.meta.env.DEV) (window as unknown as Record<string, unknown>).__testSocket = s;

    s.on('connect', () => {
      setConnected(true);
      setReconnecting(false);
      showToast('Connected');
      debugLog('[SOCKET] Connected');
    });

    s.on('connected', (payload) => {
      setConnected(true);
      setReconnecting(false);
      debugLog('[SOCKET] Handshake acknowledged', payload);
    });

    s.on('disconnect', () => {
      setConnected(false);
      setReconnecting(true);
      debugLog('[SOCKET] Disconnected');
    });

    s.on('reconnect_attempt', () => {
      setReconnecting(true);
    });

    s.on('connect_error', (err) => {
      setConnected(false);
      setReconnecting(true);

      const now = Date.now();
      if (now - lastSocketConnectErrorToastRef.current < 10_000) return;
      lastSocketConnectErrorToastRef.current = now;

      const message = err?.message ?? 'unknown connection error';
      if (import.meta.env.DEV) {
        showToast('Server unavailable. Start game-server.');
        console.warn('[socket] connect_error', { message });
      } else {
        showToast(`Connection failed: ${message}`);
      }
    });

    return () => {
      s.disconnect();
    };
  }, [authSession?.userId, showToast]);

  return (
    <SocketContext.Provider value={{ socket, connected, reconnecting }}>
      {children}
    </SocketContext.Provider>
  );
}
