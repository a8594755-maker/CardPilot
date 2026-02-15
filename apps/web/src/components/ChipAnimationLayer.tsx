import { useEffect, useRef, useState, useCallback, memo } from "react";
import type { ChipTransfer, AnimationSpeed } from "../lib/chip-animation.js";

interface ChipAnimationLayerProps {
  transfers: ChipTransfer[];
  onTransferDone: (id: string) => void;
  speed: AnimationSpeed;
}

/**
 * Absolute overlay rendered on top of the table surface.
 * Renders animated chip tokens that fly from seat→pot or pot→seat.
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

// ── Individual animated chip token ──

interface AnimatedChipProps {
  transfer: ChipTransfer;
  onDone: (id: string) => void;
}

function AnimatedChip({ transfer, onDone }: AnimatedChipProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<"start" | "flying" | "landed">("start");

  const { id, from, to, amount, kind, duration } = transfer;

  // Kick off the animation on mount
  useEffect(() => {
    // Start at "from" position, then after a microtask switch to "flying"
    const raf = requestAnimationFrame(() => {
      setPhase("flying");
    });
    return () => cancelAnimationFrame(raf);
  }, []);

  // Remove after duration
  useEffect(() => {
    if (phase !== "flying") return;
    const timer = setTimeout(() => {
      setPhase("landed");
      onDone(id);
    }, duration + 50); // small buffer
    return () => clearTimeout(timer);
  }, [phase, duration, id, onDone]);

  if (phase === "landed") return null;

  const x = phase === "start" ? from.x : to.x;
  const y = phase === "start" ? from.y : to.y;

  const isAllIn = kind === "toPot" && amount > 0; // styling handled below
  const isWinner = kind === "toWinner";

  // Format amount for display
  const label = amount >= 1000 ? `${(amount / 1000).toFixed(1)}k` : amount.toLocaleString();

  return (
    <div
      ref={elRef}
      className="absolute flex items-center gap-1"
      style={{
        left: x,
        top: y,
        transform: "translate(-50%, -50%)",
        transition: phase === "flying"
          ? `left ${duration}ms cubic-bezier(0.25, 0.1, 0.25, 1), top ${duration}ms cubic-bezier(0.25, 0.1, 0.25, 1), opacity ${duration * 0.3}ms ease`
          : "none",
        opacity: phase === "flying" ? 1 : 0.85,
        willChange: "left, top, opacity",
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
    </div>
  );
}

export default ChipAnimationLayer;
