import { memo } from "react";

/**
 * Unified poker card component used across the entire app.
 * Renders a crisp HTML card with rank + suit symbol on a dark gradient background.
 * Supports 4-color suits and multiple size variants.
 */

// ── Suit mappings ──

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

// ── Variant size presets ──

export type PokerCardVariant = "mini" | "seat" | "table" | "modal";

interface VariantConfig {
  card: string;
  rank: string;
  suit: string;
  gap: string;
}

const VARIANT_CONFIG: Record<PokerCardVariant, VariantConfig> = {
  mini: {
    card: "w-[22px] h-[30px] text-[9px] rounded-[3px]",
    rank: "text-[9px] leading-none",
    suit: "text-[7px] leading-none -mt-px",
    gap: "",
  },
  seat: {
    card: "w-9 h-[50px] text-sm rounded-md",
    rank: "text-sm leading-none",
    suit: "text-[10px] leading-none -mt-0.5",
    gap: "",
  },
  table: {
    card: "w-11 h-[62px] text-base rounded-md",
    rank: "text-base leading-none",
    suit: "text-xs leading-none -mt-0.5",
    gap: "",
  },
  modal: {
    card: "w-20 h-28 text-2xl rounded-xl",
    rank: "text-2xl leading-none",
    suit: "text-lg leading-none -mt-0.5",
    gap: "",
  },
};

// ── Props ──

export interface PokerCardProps {
  /** Card code, e.g. "Ah", "Ks", "Td", "2c" */
  card?: string;
  /** Whether the card is face-down */
  faceDown?: boolean;
  /** Size variant */
  variant?: PokerCardVariant;
  /** Use 4-color suit mode (default true) */
  fourColor?: boolean;
  /** Click handler (adds hover/active states) */
  onClick?: () => void;
  /** Additional CSS classes */
  className?: string;
  /** If true, show subtle hover effect even without onClick */
  interactive?: boolean;
}

// ── Component ──

export const PokerCard = memo(function PokerCard({
  card,
  faceDown = false,
  variant = "table",
  fourColor = true,
  onClick,
  className = "",
  interactive = false,
}: PokerCardProps) {
  const cfg = VARIANT_CONFIG[variant];

  // Face-down card
  if (faceDown || !card || card.length < 2) {
    return (
      <div
        className={`${cfg.card} bg-gradient-to-br from-sky-800 to-sky-950 border border-sky-600/30 flex items-center justify-center select-none shadow-sm ${
          onClick || interactive
            ? "cursor-pointer hover:border-sky-400/50 active:scale-95 transition-all"
            : ""
        } ${className}`}
        onClick={onClick}
        role={onClick ? "button" : undefined}
        tabIndex={onClick ? 0 : undefined}
      >
        <div
          className={`rounded-sm border border-sky-500/20 ${
            variant === "mini"
              ? "w-3 h-4"
              : variant === "seat"
              ? "w-5 h-7"
              : variant === "table"
              ? "w-6 h-9"
              : "w-12 h-16"
          } bg-gradient-to-br from-sky-700/40 to-sky-900/60`}
        />
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

  const clickable = onClick || interactive;

  return (
    <div
      className={`${cfg.card} bg-gradient-to-b ${bg} border border-white/20 flex flex-col items-center justify-center font-extrabold shadow-sm select-none ${
        clickable
          ? "cursor-pointer hover:border-white/40 hover:shadow-md active:scale-95 transition-all"
          : ""
      } ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <span className={`${suitColor} ${cfg.rank}`}>{rankStr}</span>
      <span className={`${suitColor} ${cfg.suit}`}>{suitStr}</span>
    </div>
  );
});

export default PokerCard;
