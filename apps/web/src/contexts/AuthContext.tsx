import { createContext, useContext, ReactNode } from 'react';
import { useAuthSession, UseAuthSessionReturn } from '../hooks/useAuthSession';
import { useToast } from './ToastContext';

const AuthContext = createContext<UseAuthSessionReturn | null>(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/** Non-throwing variant — returns null when AuthProvider is missing (e.g. during Vite HMR). */
export function useAuthSafe(): UseAuthSessionReturn | null {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { showToast } = useToast();
  const auth = useAuthSession(showToast);

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}
