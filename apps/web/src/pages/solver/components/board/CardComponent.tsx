const SUIT_SYMBOLS: Record<string, string> = {
  s: '\u2660',
  h: '\u2665',
  d: '\u2666',
  c: '\u2663',
};

const SUIT_COLORS: Record<string, string> = {
  s: '#1a1a2e',
  h: '#e74c3c',
  d: '#3498db',
  c: '#27ae60',
};

const SUIT_BG: Record<string, string> = {
  s: '#e2e8f0',
  h: '#fce4ec',
  d: '#e3f2fd',
  c: '#e8f5e9',
};

interface CardComponentProps {
  card: string;
  size?: 'sm' | 'md' | 'lg';
}

const SIZE_CLASSES = {
  sm: 'w-8 h-11 text-sm',
  md: 'w-10 h-14 text-base',
  lg: 'w-14 h-20 text-xl',
};

export function CardComponent({ card, size = 'md' }: CardComponentProps) {
  const rank = card[0]?.toUpperCase() ?? '?';
  const suit = card[1]?.toLowerCase() ?? '?';
  const symbol = SUIT_SYMBOLS[suit] || '?';
  const color = SUIT_COLORS[suit] || '#666';
  const bg = SUIT_BG[suit] || '#f0f0f0';

  return (
    <div
      className={`${SIZE_CLASSES[size]} flex flex-col items-center justify-center rounded-md border border-border/50 font-mono font-bold shadow-sm`}
      style={{ backgroundColor: bg, color }}
    >
      <span className="leading-none">{rank}</span>
      <span className="leading-none text-[0.7em]">{symbol}</span>
    </div>
  );
}
