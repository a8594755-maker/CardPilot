import { useEffect, useRef, useState, memo } from "react";
import type { ChipTransfer, AnimationSpeed } from "../lib/chip-animation.js";

interface ChipAnimationLayerProps {
  transfers: ChipTransfer[];
  onTransferDone: (id: string) => void;
  speed: AnimationSpeed;
}

/**
 * Absolute overlay rendered on top of the table surface.
 * Renders animated chip tokens that fly from seat→pot or pot→seat.
 * 3-stage animation: flight → arrival hold → merge/fade.
 * pointer-events: none so clicks pass through.
 */
export const ChipAnimationLayer = memo(function ChipAnimationLayer({
  transfers,
  onTransferDone,
  speed,
}: ChipAnimationLayerProps) {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleChange = () => setPrefersReducedMotion(mq.matches);
    handleChange();
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", handleChange);
      return () => mq.removeEventListener("change", handleChange);
    }
    mq.addListener(handleChange);
    return () => mq.removeListener(handleChange);
  }, []);

  if (speed === "off" || transfers.length === 0 || prefersReducedMotion) return null;

  return (
    <div
      className="absolute inset-0 z-30 pointer-events-none overflow-hidden cp-chip-flight-layer"
      aria-hidden="true"
    >
      {transfers.map((t) => (
        <AnimatedChip key={t.id} transfer={t} onDone={onTransferDone} />
      ))}
    </div>
  );
});

// ── 3-stage animated chip token ──

type Phase = "init" | "flight" | "hold" | "merge" | "done";

interface AnimatedChipProps {
  transfer: ChipTransfer;
  onDone: (id: string) => void;
}

function AnimatedChip({ transfer, onDone }: AnimatedChipProps) {
  const [phase, setPhase] = useState<Phase>("init");
  const timerRef = useRef<ReturnType<typeof setTimeout>>();
  const rafRef = useRef<number>();

  const { id, from, to, amount, kind, timing } = transfer;
  const isWinner = kind === "toWinner";

  // Phase state machine: init → flight → hold → merge → done
  useEffect(() => {
    // Kick off flight on next frame (so browser renders at "from" first)
    rafRef.current = requestAnimationFrame(() => {
      setPhase("flight");
    });
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (phase === "flight") {
      timerRef.current = setTimeout(() => setPhase("hold"), timing.flight);
    } else if (phase === "hold") {
      timerRef.current = setTimeout(() => setPhase("merge"), timing.hold);
    } else if (phase === "merge") {
      timerRef.current = setTimeout(() => {
        setPhase("done");
        onDone(id);
      }, timing.merge);
    }
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [phase, timing, id, onDone]);

  if (phase === "done") return null;

  // Move token using transform only (GPU-friendly), anchored at origin coordinates.
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const isAtDestination = phase !== "init";

  // Opacity/scale per phase
  let opacity = 1;
  let scale = 1;
  if (phase === "init") { opacity = 0.7; scale = 0.8; }
  if (phase === "merge") { opacity = 0; scale = 0.4; }

  // Format amount for display
  const label = amount >= 1000 ? `${(amount / 1000).toFixed(1)}k` : amount.toLocaleString();

  // Transition timing depends on phase
  let transition = "none";
  if (phase === "flight") {
    transition = `transform ${timing.flight}ms cubic-bezier(0.22, 1, 0.36, 1), opacity ${timing.flight}ms ease`;
  }
  if (phase === "merge") {
    transition = `transform ${timing.merge}ms ease, opacity ${timing.merge}ms ease`;
  }

  return (
    <div
      className={`absolute cp-chip-flight ${isWinner ? "cp-chip-flight--winner" : "cp-chip-flight--pot"}`}
      style={{
        left: from.x,
        top: from.y,
        transform: `translate3d(${isAtDestination ? dx : 0}px, ${isAtDestination ? dy : 0}px, 0) translate(-50%, -50%) scale(${scale})`,
        opacity,
        transition,
        willChange: "transform, opacity",
      }}
    >
      {/* Chip icon */}
      <div className="cp-chip-token">
        <span className="cp-chip-token-core">$</span>
      </div>
      {/* Amount label */}
      <span className="cp-chip-label">
        {isWinner ? "+" : ""}{label}
      </span>
      {/* Pot pulse ring — shows during hold phase for toPot transfers */}
      {kind === "toPot" && phase === "hold" && (
        <div
          className="cp-chip-ring cp-chip-ring--pot"
          style={{ animationDuration: `${timing.potPulse}ms` }}
        />
      )}
      {/* Winner glow — shows during hold phase for toWinner transfers */}
      {isWinner && phase === "hold" && (
        <div
          className="cp-chip-ring cp-chip-ring--winner"
          style={{ animationDuration: `${timing.winnerGlow}ms` }}
        />
      )}
      {isWinner && phase === "hold" && <div className="cp-chip-winner-spark" />}
    </div>
  );
}

export default ChipAnimationLayer;
