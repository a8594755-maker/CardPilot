import { memo, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { PokerCard } from "./PokerCard";

interface SevenTwoRevealOverlayProps {
  winnerName: string;
  winnerCards: [string, string];
  totalBounty: number;
  onDismiss: () => void;
}

export const SevenTwoRevealOverlay = memo(function SevenTwoRevealOverlay({
  winnerName,
  winnerCards,
  totalBounty,
  onDismiss,
}: SevenTwoRevealOverlayProps) {
  const [visible, setVisible] = useState(false);

  // Trigger entrance animation on mount
  useEffect(() => {
    requestAnimationFrame(() => setVisible(true));
  }, []);

  // Auto-dismiss after 3.5s
  useEffect(() => {
    const t = setTimeout(onDismiss, 3500);
    return () => clearTimeout(t);
  }, [onDismiss]);

  // ESC to dismiss
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDismiss();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onDismiss]);

  const overlay = (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center cursor-pointer"
      onClick={onDismiss}
      style={{
        opacity: visible ? 1 : 0,
        transition: "opacity 300ms ease",
      }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-[3px]" />

      {/* Content */}
      <div className="relative flex flex-col items-center gap-4">
        {/* Title */}
        <div
          className="text-amber-400 text-lg font-extrabold uppercase tracking-widest cp-72-title"
          style={{ animationDelay: "0ms" }}
        >
          7-2 Bounty!
        </div>

        {/* Winner name */}
        <div
          className="text-white text-base font-bold cp-72-title"
          style={{ animationDelay: "100ms" }}
        >
          {winnerName}
        </div>

        {/* Cards */}
        <div className="flex items-center gap-4">
          <div className="cp-72-card-reveal" style={{ animationDelay: "200ms" }}>
            <div className="cp-72-glow rounded-xl">
              <PokerCard card={winnerCards[0]} variant="modal" />
            </div>
          </div>
          <div className="cp-72-card-reveal" style={{ animationDelay: "400ms" }}>
            <div className="cp-72-glow rounded-xl">
              <PokerCard card={winnerCards[1]} variant="modal" />
            </div>
          </div>
        </div>

        {/* Bounty amount */}
        <div className="cp-72-bounty-badge">
          <span className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-amber-500/20 border-2 border-amber-400/60 text-amber-300 text-lg font-extrabold shadow-lg shadow-amber-500/20">
            +{totalBounty.toLocaleString()}
          </span>
        </div>
      </div>
    </div>
  );

  return createPortal(overlay, document.body);
});

export default SevenTwoRevealOverlay;
