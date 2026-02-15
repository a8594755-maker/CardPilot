import { useEffect, memo } from "react";
import { CardGlyph } from "./CardGlyph";

interface CardZoomModalProps {
  cards: string[];
  label?: string;
  sublabel?: string;
  onClose: () => void;
}

export const CardZoomModal = memo(function CardZoomModal({
  cards,
  label,
  sublabel,
  onClose,
}: CardZoomModalProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[110] bg-black/70 backdrop-blur-sm flex items-end md:items-center justify-center"
      onClick={onClose}
    >
      <div
        className="w-full md:w-auto md:min-w-[340px] rounded-t-2xl md:rounded-2xl border border-white/15 bg-slate-900/95 p-4 md:p-6"
        style={{ paddingBottom: "max(16px, env(safe-area-inset-bottom))" }}
        onClick={(e) => e.stopPropagation()}
      >
        {(label || sublabel) && (
          <div className="flex items-center justify-between mb-4">
            <div>
              {label && (
                <div className="text-sm font-semibold text-white">{label}</div>
              )}
              {sublabel && (
                <div className="text-xs text-slate-400">{sublabel}</div>
              )}
            </div>
            <button
              className="text-slate-400 hover:text-white transition-colors"
              onClick={onClose}
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex items-center justify-center gap-3">
          {cards.map((c, i) => (
            <CardGlyph key={i} card={c} size="lg" fourColor />
          ))}
        </div>
      </div>
    </div>
  );
});

export default CardZoomModal;
