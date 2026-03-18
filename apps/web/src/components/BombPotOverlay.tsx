import { memo, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface BombPotOverlayProps {
  anteAmount: number;
  onDismiss: () => void;
}

type Phase = 'enter' | 'hold' | 'exit' | 'idle';

const ENTER_MS = 400;
const HOLD_MS = 1200;
const EXIT_MS = 250;

export const BombPotOverlay = memo(function BombPotOverlay({
  anteAmount,
  onDismiss,
}: BombPotOverlayProps) {
  const [phase, setPhase] = useState<Phase>('enter');
  const timersRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);

  useEffect(() => {
    const t1 = setTimeout(() => setPhase('hold'), ENTER_MS);
    const t2 = setTimeout(() => setPhase('exit'), ENTER_MS + HOLD_MS);
    const t3 = setTimeout(
      () => {
        setPhase('idle');
        onDismiss();
      },
      ENTER_MS + HOLD_MS + EXIT_MS,
    );
    timersRef.current = [t1, t2, t3];
    return () => timersRef.current.forEach(clearTimeout);
  }, [onDismiss]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onDismiss]);

  if (phase === 'idle') return null;

  const overlay = (
    <div className={`cp-bomb-overlay cp-bomb-overlay--${phase}`} role="status" aria-live="polite">
      <div className="cp-bomb-overlay__backdrop" />
      <div className="cp-bomb-overlay__content">
        <div className="cp-bomb-overlay__title">
          <span role="img" aria-label="bomb">
            💣
          </span>{' '}
          BOMB POT
        </div>
        {anteAmount > 0 && (
          <div className="cp-bomb-overlay__subtitle">Ante: {anteAmount.toLocaleString()}</div>
        )}
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
});

export default BombPotOverlay;
