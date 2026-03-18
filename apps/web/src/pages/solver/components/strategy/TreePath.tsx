interface TreePathProps {
  path: string[];
  onNavigate: (index: number) => void;
  onRoot: () => void;
}

export function TreePath({ path, onNavigate, onRoot }: TreePathProps) {
  return (
    <div className="flex items-center gap-1 text-sm flex-wrap">
      <button
        onClick={onRoot}
        className="px-2 py-0.5 rounded text-primary hover:bg-primary/10 font-medium transition-colors"
      >
        Root
      </button>
      {path.map((action, i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="text-muted-foreground">/</span>
          <button
            onClick={() => onNavigate(i)}
            className={`px-2 py-0.5 rounded transition-colors ${
              i === path.length - 1
                ? 'bg-primary/10 text-primary font-medium'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            {action}
          </button>
        </span>
      ))}
    </div>
  );
}
