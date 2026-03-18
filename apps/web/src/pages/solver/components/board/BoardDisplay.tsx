import { CardComponent } from './CardComponent';

interface BoardDisplayProps {
  cards: string[];
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function BoardDisplay({ cards, label, size = 'md' }: BoardDisplayProps) {
  return (
    <div className="space-y-1">
      {label && <div className="text-xs text-muted-foreground font-medium">{label}</div>}
      <div className="flex gap-1.5">
        {cards.map((card, i) => (
          <CardComponent key={i} card={card} size={size} />
        ))}
      </div>
    </div>
  );
}
