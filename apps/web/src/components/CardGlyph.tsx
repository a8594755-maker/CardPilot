import { memo } from "react";

/**
 * Text/emoji-based card renderer for maximum readability at small sizes.
 * Renders a crisp HTML card with big rank + suit symbol.
 * Supports 2-color (red/black) and 4-color suit styles.
 */

const SUIT_SYMBOL: Record<string, string> = {
  s: "♠",
  h: "♥",
  d: "♦",
  c: "♣",
};

const SUIT_COLOR_2: Record<string, string> = {
  s: "text-slate-100",
  h: "text-red-500",
  d: "text-red-500",
  c: "text-slate-100",
};

const SUIT_COLOR_4: Record<string, string> = {
  s: "text-slate-100",
  h: "text-red-500",
  d: "text-blue-400",
  c: "text-emerald-400",
};

const SUIT_BG: Record<string, string> = {
  s: "from-slate-800 to-slate-900",
  h: "from-slate-800 to-red-950/40",
  d: "from-slate-800 to-blue-950/40",
  c: "from-slate-800 to-emerald-950/40",
};

const RANK_DISPLAY: Record<string, string> = {
  A: "A",
  "2": "2",
  "3": "3",
  "4": "4",
  "5": "5",
  "6": "6",
  "7": "7",
  "8": "8",
  "9": "9",
  T: "10",
  J: "J",
  Q: "Q",
  K: "K",
};

interface CardGlyphProps {
  card: string;
  /** Size preset */
  size?: "sm" | "md" | "lg";
  /** Use 4-color suit mode */
  fourColor?: boolean;
  className?: string;
  onClick?: () => void;
}

const SIZE_CLASSES = {
  sm: "w-8 h-11 text-[11px] rounded",
  md: "w-11 h-[62px] text-sm rounded-md",
  lg: "w-20 h-28 text-2xl rounded-xl",
};

const SUIT_SIZE_CLASSES = {
  sm: "text-[9px]",
  md: "text-xs",
  lg: "text-lg",
};

export const CardGlyph = memo(function CardGlyph({
  card,
  size = "md",
  fourColor = false,
  className = "",
  onClick,
}: CardGlyphProps) {
  if (!card || card.length < 2) {
    return (
      <div
        className={`${SIZE_CLASSES[size]} bg-gradient-to-b from-slate-700 to-slate-800 border border-white/10 flex items-center justify-center text-slate-500 shadow-md ${className}`}
      >
        ?
      </div>
    );
  }

  const rank = card[0];
  const suit = card[1];
  const rankStr = RANK_DISPLAY[rank] ?? rank;
  const suitStr = SUIT_SYMBOL[suit] ?? suit;
  const colorMap = fourColor ? SUIT_COLOR_4 : SUIT_COLOR_2;
  const suitColor = colorMap[suit] ?? "text-white";
  const bg = SUIT_BG[suit] ?? "from-slate-800 to-slate-900";

  return (
    <div
      className={`${SIZE_CLASSES[size]} bg-gradient-to-b ${bg} border border-white/20 flex flex-col items-center justify-center font-extrabold shadow-md select-none ${onClick ? "cursor-pointer hover:border-white/40 active:scale-95 transition-all" : ""} ${className}`}
      onClick={onClick}
    >
      <span className={suitColor}>{rankStr}</span>
      <span className={`${suitColor} ${SUIT_SIZE_CLASSES[size]} -mt-0.5`}>
        {suitStr}
      </span>
    </div>
  );
});

export default CardGlyph;
