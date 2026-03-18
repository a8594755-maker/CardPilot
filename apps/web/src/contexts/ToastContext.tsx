import { createContext, useContext, useState, useCallback, useRef, ReactNode } from 'react';

interface Toast {
  text: string;
  isError: boolean;
  id: number;
}

interface ToastContextType {
  showToast: (text: string) => void;
  toast: Toast | null;
  toastExiting: boolean;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const [toastExiting, setToastExiting] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((text: string) => {
    if (!text) return;
    const isError = /^error:/i.test(text) || /fail|denied|kicked|banned/i.test(text);

    // Clear previous dismiss timer
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);

    setToastExiting(false);
    setToast({ text, isError, id: Date.now() });

    // Auto-dismiss non-error toasts after 5s
    if (!isError) {
      toastTimerRef.current = setTimeout(() => {
        setToastExiting(true);
        setTimeout(() => setToast(null), 250);
      }, 5000);
    }
  }, []);

  return (
    <ToastContext.Provider value={{ showToast, toast, toastExiting }}>
      {children}
    </ToastContext.Provider>
  );
}
