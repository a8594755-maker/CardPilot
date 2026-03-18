interface MatrixCellProps {
  hand: string;
  frequencies: Record<string, number>;
  actions: string[];
  isPair: boolean;
  isSuited: boolean;
  isSelected: boolean;
  isHovered: boolean;
  isDimmed?: boolean;
  compact?: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export function MatrixCell({
  hand,
  frequencies,
  actions: _actions,
  isPair,
  isSuited,
  isSelected,
  isDimmed,
  compact,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: MatrixCellProps) {
  const bgColor = computeCellColor(frequencies);
  const foldFreq = frequencies.fold ?? 0;
  const isEmpty = Object.keys(frequencies).length === 0;
  const baseOpacity = isEmpty ? 0.25 : foldFreq > 0.99 ? 0.15 : 1;
  const opacity = isDimmed ? baseOpacity * 0.25 : baseOpacity;

  const sizeClass = compact ? 'w-[26px] h-[26px] text-[8px]' : 'w-[38px] h-[38px] text-[10px]';

  return (
    <button
      className={`matrix-cell relative flex items-center justify-center ${sizeClass} font-mono font-medium rounded-[2px] cursor-pointer select-none transition-shadow ${
        isSelected ? 'ring-2 ring-yellow-400 z-20' : ''
      } ${isPair ? 'font-bold' : ''}`}
      style={{
        backgroundColor: bgColor,
        opacity,
        color: getContrastColor(bgColor),
      }}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      title={hand}
    >
      {hand}
      {/* Suited/Offsuit indicator */}
      {!isPair && !compact && (
        <span className="absolute bottom-0 right-0.5 text-[6px] opacity-60">
          {isSuited ? 's' : 'o'}
        </span>
      )}
    </button>
  );
}

// GTO+ color palette (more vibrant and professional)
const ACTION_COLORS: Record<string, [number, number, number]> = {
  fold: [220, 53, 53], // vibrant red
  call: [34, 197, 94], // vibrant green
  check: [100, 116, 139], // slate gray
  raise: [59, 130, 246], // vibrant blue
  bet: [245, 158, 11], // amber
  allin: [139, 92, 246], // purple
};

function getActionRGB(action: string): [number, number, number] {
  const lower = action.toLowerCase();
  if (lower === 'fold') return ACTION_COLORS.fold;
  if (lower === 'call') return ACTION_COLORS.call;
  if (lower === 'check') return ACTION_COLORS.check;
  if (lower === 'allin' || lower === 'jam') return ACTION_COLORS.allin;
  if (lower.startsWith('raise') || lower.startsWith('3bet') || lower.startsWith('4bet'))
    return ACTION_COLORS.raise;
  if (lower.startsWith('bet')) return ACTION_COLORS.bet;
  return ACTION_COLORS.raise;
}

function computeCellColor(frequencies: Record<string, number>): string {
  const keys = Object.keys(frequencies);
  if (keys.length === 0) return '#1e293b';

  // Sum all frequencies
  let totalFreq = 0;
  for (const v of Object.values(frequencies)) {
    totalFreq += v;
  }
  if (totalFreq <= 0) return '#1e293b';

  // Weighted blend of action RGB values
  let r = 0,
    g = 0,
    b = 0;
  for (const [action, freq] of Object.entries(frequencies)) {
    if (freq <= 0) continue;
    const weight = freq / totalFreq;
    const [ar, ag, ab] = getActionRGB(action);
    r += ar * weight;
    g += ag * weight;
    b += ab * weight;
  }

  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
}

function getContrastColor(bgColor: string): string {
  const match = bgColor.match(/\d+/g);
  if (!match) return 'white';
  const [r, g, b] = match.map(Number);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? '#000' : '#fff';
}
