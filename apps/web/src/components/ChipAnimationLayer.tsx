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
  if (speed === "off" || transfers.length === 0) return null;

  return (
    <div
      className="absolute inset-0 z-30 pointer-events-none overflow-hidden"
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

  // Position: start at "from", move to "to" during flight, stay at "to" for hold+merge
  const atOrigin = phase === "init";
  const x = atOrigin ? from.x : to.x;
  const y = atOrigin ? from.y : to.y;

  // Opacity/scale per phase
  let opacity = 1;
  let scale = 1;
  if (phase === "init") { opacity = 0.7; scale = 0.8; }
  if (phase === "merge") { opacity = 0; scale = 0.4; }

  // Format amount for display
  const label = amount >= 1000 ? `${(amount / 1000).toFixed(1)}k` : amount.toLocaleString();

  // Transition timing depends on phase
  let transitionDuration = "0ms";
  if (phase === "flight") transitionDuration = `${timing.flight}ms`;
  if (phase === "merge") transitionDuration = `${timing.merge}ms`;

  return (
    <div
      className="absolute flex items-center gap-1"
      style={{
        left: x,
        top: y,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        transition: phase === "init"
          ? "none"
          : `left ${transitionDuration} cubic-bezier(0.25, 0.1, 0.25, 1), top ${transitionDuration} cubic-bezier(0.25, 0.1, 0.25, 1), opacity ${transitionDuration} ease, transform ${transitionDuration} ease`,
        willChange: "transform, opacity",
      }}
    >
      {/* Chip icon */}
      <div
        className={`
          w-5 h-5 rounded-full flex items-center justify-center text-[8px] font-black shadow-lg
          ${isWinner
            ? "bg-gradient-to-br from-amber-400 to-yellow-500 text-amber-900 ring-2 ring-amber-300/60"
            : "bg-gradient-to-br from-sky-400 to-blue-600 text-white ring-1 ring-sky-300/40"
          }
        `}
      >
        $
      </div>
      {/* Amount label */}
      <span
        className={`
          text-[10px] font-bold whitespace-nowrap px-1 py-0.5 rounded-md shadow-md
          ${isWinner
            ? "bg-amber-500/90 text-white"
            : "bg-sky-600/90 text-white"
          }
        `}
      >
        {isWinner ? "+" : ""}{label}
      </span>
      {/* Pot pulse ring — shows during hold phase for toPot transfers */}
      {kind === "toPot" && phase === "hold" && (
        <div
          className="absolute inset-0 -m-2 rounded-full border-2 border-sky-400/60 animate-ping"
          style={{ animationDuration: `${timing.potPulse}ms`, animationIterationCount: 1 }}
        />
      )}
      {/* Winner glow — shows during hold phase for toWinner transfers */}
      {isWinner && phase === "hold" && (
        <div
          className="absolute inset-0 -m-3 rounded-full bg-amber-400/20 animate-pulse"
          style={{ animationDuration: `${timing.winnerGlow}ms` }}
        />
      )}
    </div>
  );
}

export default ChipAnimationLayer;
