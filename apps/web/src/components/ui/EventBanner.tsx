import { memo, useEffect, useRef, useState } from 'react';

export type EventBannerVariant = 'success' | 'warning';

export interface EventBannerProps {
  open: boolean;
  label: string;
  variant?: EventBannerVariant;
  icon?: string;
  eventKey?: number;
  className?: string;
}

const IN_MS = 180;
const HOLD_MS = 1200;
const OUT_MS = 180;

type EventBannerPhase = 'idle' | 'enter' | 'hold' | 'exit';

export const EventBanner = memo(function EventBanner({
  open,
  label,
  variant = 'warning',
  icon,
  eventKey = 0,
  className = '',
}: EventBannerProps) {
  const [mounted, setMounted] = useState(false);
  const [phase, setPhase] = useState<EventBannerPhase>('idle');
  const timersRef = useRef<Array<ReturnType<typeof setTimeout>>>([]);
  const seqRef = useRef(0);

  const clearTimers = () => {
    for (const timer of timersRef.current) clearTimeout(timer);
    timersRef.current = [];
  };

  useEffect(() => {
    return () => clearTimers();
  }, []);

  useEffect(() => {
    if (open) {
      seqRef.current += 1;
      const seq = seqRef.current;
      clearTimers();
      setMounted(true);
      setPhase('enter');

      timersRef.current.push(
        setTimeout(() => {
          if (seq !== seqRef.current) return;
          setPhase('hold');
        }, IN_MS),
      );

      timersRef.current.push(
        setTimeout(() => {
          if (seq !== seqRef.current) return;
          setPhase('exit');
        }, IN_MS + HOLD_MS),
      );

      timersRef.current.push(
        setTimeout(
          () => {
            if (seq !== seqRef.current) return;
            setMounted(false);
            setPhase('idle');
          },
          IN_MS + HOLD_MS + OUT_MS,
        ),
      );
      return;
    }

    if (!mounted) return;
    seqRef.current += 1;
    clearTimers();
    setPhase('exit');
    timersRef.current.push(
      setTimeout(() => {
        setMounted(false);
        setPhase('idle');
      }, OUT_MS),
    );
  }, [open, eventKey, mounted]);

  if (!mounted) return null;

  return (
    <div
      className={`cp-event-banner cp-event-banner--${variant} cp-event-banner--${phase} ${className}`.trim()}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="cp-event-banner__spark" aria-hidden="true" />
      <span className="cp-event-banner__icon-wrap" aria-hidden="true">
        {icon ? (
          <img src={icon} alt="" className="cp-event-banner__icon" />
        ) : (
          <span className="cp-event-banner__icon-fallback">72</span>
        )}
      </span>
      <span className="cp-event-banner__label cp-num">{label}</span>
    </div>
  );
});

export default EventBanner;
