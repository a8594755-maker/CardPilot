import { memo } from "react";

const SUIT_SYMBOL: Record<string, string> = {
  s: "\u2660",
  h: "\u2665",
  d: "\u2666",
  c: "\u2663",
};

const SUIT_COLOR_2: Record<string, string> = {
  s: "text-slate-900",
  h: "text-red-600",
  d: "text-red-600",
  c: "text-slate-900",
};

const SUIT_COLOR_4: Record<string, string> = {
  s: "text-slate-900",
  h: "text-red-600",
  d: "text-blue-600",
  c: "text-emerald-700",
};

const SUIT_BACK_TINT: Record<string, string> = {
  s: "from-slate-700 to-slate-900",
  h: "from-slate-700 to-rose-900",
  d: "from-slate-700 to-blue-900",
  c: "from-slate-700 to-emerald-900",
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

export type PokerCardVariant = "mini" | "seat" | "table" | "modal";

interface VariantConfig {
  card: string;
  rank: string;
  cornerSuit: string;
  centerSuit: string;
  cornerGap: string;
  backInner: string;
}

const VARIANT_CONFIG: Record<PokerCardVariant, VariantConfig> = {
  mini: {
    card: "w-[38px] h-[54px] rounded-[5px]",
    rank: "text-[13px]",
    cornerSuit: "text-[11px]",
    centerSuit: "text-[14px]",
    cornerGap: "gap-0",
    backInner: "w-5 h-8",
  },
  seat: {
    card: "w-12 h-[68px] rounded-[7px]",
    rank: "text-[15px]",
    cornerSuit: "text-[13px]",
    centerSuit: "text-lg",
    cornerGap: "gap-0.5",
    backInner: "w-7 h-10",
  },
  table: {
    card: "w-14 h-[84px] rounded-[8px]",
    rank: "text-[18px]",
    cornerSuit: "text-sm",
    centerSuit: "text-xl",
    cornerGap: "gap-0.5",
    backInner: "w-8 h-12",
  },
  modal: {
    card: "w-24 h-36 rounded-2xl",
    rank: "text-2xl",
    cornerSuit: "text-xl",
    centerSuit: "text-4xl",
    cornerGap: "gap-1",
    backInner: "w-14 h-20",
  },
};

export interface PokerCardProps {
  card?: string;
  faceDown?: boolean;
  variant?: PokerCardVariant;
  fourColor?: boolean;
  onClick?: () => void;
  className?: string;
  interactive?: boolean;
  showCenterPip?: boolean;
  showCornerPips?: boolean;
}

export const PokerCard = memo(function PokerCard({
  card,
  faceDown = false,
  variant = "table",
  fourColor = true,
  onClick,
  className = "",
  interactive = false,
  showCenterPip = false,
  showCornerPips = true,
}: PokerCardProps) {
  const cfg = VARIANT_CONFIG[variant];

  if (faceDown || !card || card.length < 2) {
    return (
      <div
        className={`cp-poker-card cp-poker-card--back ${cfg.card} relative overflow-hidden border border-sky-500/35 bg-gradient-to-br from-slate-800 via-sky-900 to-slate-900 shadow-md select-none ${
          onClick || interactive
            ? "cursor-pointer hover:border-sky-300/60 hover:shadow-lg active:scale-[0.98] transition-all"
            : ""
        } ${className}`}
        onClick={onClick}
        role={onClick ? "button" : undefined}
        tabIndex={onClick ? 0 : undefined}
      >
        <div className="absolute inset-[6%] rounded-[inherit] border border-sky-200/20 bg-[radial-gradient(circle_at_20%_20%,rgba(148,163,184,0.22),rgba(15,23,42,0.2)_50%,rgba(15,23,42,0.7)_100%)]" />
        <div
          className={`relative ${cfg.backInner} rounded-md border border-sky-200/30 bg-[repeating-linear-gradient(45deg,rgba(56,189,248,0.16)_0px,rgba(56,189,248,0.16)_3px,rgba(2,6,23,0.16)_3px,rgba(2,6,23,0.16)_6px)]`}
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
  const backTint = SUIT_BACK_TINT[suit] ?? "from-slate-700 to-slate-900";

  const clickable = onClick || interactive;

  return (
    <div
      className={`cp-poker-card ${cfg.card} relative overflow-hidden border border-slate-300/80 bg-gradient-to-b from-white via-slate-50 to-slate-100 shadow-[0_2px_8px_rgba(2,6,23,0.24)] select-none ${
        clickable
          ? "cursor-pointer hover:shadow-[0_8px_18px_rgba(2,6,23,0.28)] hover:-translate-y-px active:scale-[0.98] transition-all"
          : ""
      } ${className}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      <div className={`absolute inset-[1px] rounded-[inherit] bg-gradient-to-b ${backTint} opacity-[0.06]`} />
      {showCornerPips && (
        <>
          <div className={`absolute top-[8%] left-[10%] flex flex-col items-center leading-none ${cfg.cornerGap}`}>
            <span className={`${suitColor} ${cfg.rank} font-black tracking-tight`}>{rankStr}</span>
            <span className={`${suitColor} ${cfg.cornerSuit} leading-none`}>{suitStr}</span>
          </div>
          <div className={`absolute bottom-[8%] right-[10%] rotate-180 flex flex-col items-center leading-none ${cfg.cornerGap}`}>
            <span className={`${suitColor} ${cfg.rank} font-black tracking-tight`}>{rankStr}</span>
            <span className={`${suitColor} ${cfg.cornerSuit} leading-none`}>{suitStr}</span>
          </div>
        </>
      )}
      {showCenterPip && (
        <span className={`absolute inset-0 flex items-center justify-center ${suitColor} ${cfg.centerSuit} opacity-80`}>
          {suitStr}
        </span>
      )}
    </div>
  );
});

export default PokerCard;
