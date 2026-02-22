import { memo, useEffect, useRef, useState } from "react";
import type { AnimationSpeed, ChipTransfer } from "../lib/chip-animation.js";

interface ChipAnimationLayerProps {
  transfers: ChipTransfer[];
  onTransferDone: (id: string) => void;
  speed: AnimationSpeed;
}

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

  if (speed === "off" || prefersReducedMotion || transfers.length === 0) return null;

  return (
    <div className="absolute inset-0 z-30 pointer-events-none overflow-hidden cp-chip-flight-layer" aria-hidden="true">
      {transfers.map((transfer) => (
        <AnimatedChip key={transfer.id} transfer={transfer} onDone={onTransferDone} />
      ))}
    </div>
  );
});

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
  const isBombPot = kind === "bombPotAnte";
  const isBounty = kind === "bountyToWinner";
  const isWinner = kind === "toWinner" || isBounty;

  useEffect(() => {
    rafRef.current = requestAnimationFrame(() => setPhase("flight"));
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
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [phase, timing, id, onDone]);

  if (phase === "done") return null;

  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const isAtDestination = phase !== "init";
  const arcHeight = Math.max(12, Math.min(64, (Math.abs(dx) * 0.05) + (Math.abs(dy) * 0.2)));

  let opacity = 1;
  let scale = 1;
  if (phase === "init") {
    opacity = 0.7;
    scale = 0.8;
  }
  if (phase === "merge") {
    opacity = 0;
    scale = 0.4;
  }

  const label = amount >= 1000 ? `${(amount / 1000).toFixed(1)}k` : amount.toLocaleString();

  let transition = "none";
  if (phase === "flight") {
    transition = `transform ${timing.flight}ms cubic-bezier(0.22, 1, 0.36, 1), opacity ${timing.flight}ms ease`;
  }
  if (phase === "merge") {
    transition = `transform ${timing.merge}ms ease, opacity ${timing.merge}ms ease`;
  }

  return (
    <div
      className={`absolute cp-chip-flight ${isBombPot ? "cp-chip-flight--bomb-pot" : isBounty ? "cp-chip-flight--bounty" : isWinner ? "cp-chip-flight--winner" : "cp-chip-flight--pot"}`}
      style={{
        left: from.x,
        top: from.y,
        transform: `translate3d(${isAtDestination ? dx : 0}px, ${isAtDestination ? dy : 0}px, 0) translate(-50%, -50%) scale(${scale})`,
        opacity,
        transition,
        willChange: "transform, opacity",
      }}
    >
      <div
        className={`cp-chip-flight-body ${phase === "flight" ? "cp-chip-flight-body--arc" : ""}`}
        style={phase === "flight"
          ? {
              ["--cp-chip-arc" as string]: `${arcHeight}px`,
              ["--cp-chip-flight-ms" as string]: `${timing.flight}ms`,
            }
          : undefined}
      >
        <div className={`cp-chip-token ${isBombPot ? "cp-chip-token--bomb-pot" : isBounty ? "cp-chip-token--bounty" : ""}`}>
          <span className="cp-chip-token-core">{isBombPot ? "B" : isBounty ? "7" : "$"}</span>
        </div>
        <span className="cp-chip-label">
          {isWinner ? "+" : ""}{label}
        </span>
        {kind === "toPot" && phase === "hold" && (
          <div className="cp-chip-ring cp-chip-ring--pot" style={{ animationDuration: `${timing.potPulse}ms` }} />
        )}
        {kind === "bombPotAnte" && phase === "hold" && (
          <div className="cp-chip-ring cp-chip-ring--bomb-pot" style={{ animationDuration: `${timing.potPulse}ms` }} />
        )}
        {isWinner && phase === "hold" && (
          <div className="cp-chip-ring cp-chip-ring--winner" style={{ animationDuration: `${timing.winnerGlow}ms` }} />
        )}
        {isWinner && phase === "hold" && <div className="cp-chip-winner-spark" />}
      </div>
    </div>
  );
}

export default ChipAnimationLayer;
