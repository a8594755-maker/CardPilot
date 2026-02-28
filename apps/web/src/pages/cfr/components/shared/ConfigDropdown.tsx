import { memo, useState, useRef, useEffect, useCallback } from 'react';
import type { CfrConfig } from '../../lib/cfr-api';

interface ConfigDropdownProps {
  configs: CfrConfig[];
  selected: string;
  onSelect: (name: string) => void;
}

export const ConfigDropdown = memo(function ConfigDropdown({ configs, selected, onSelect }: ConfigDropdownProps) {
  const [open, setOpen] = useState(false);
  const [focusIdx, setFocusIdx] = useState(-1);
  const ref = useRef<HTMLDivElement>(null);
  const available = configs.filter(c => c.available);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        setOpen(true);
        setFocusIdx(available.findIndex(c => c.name === selected));
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setFocusIdx(i => Math.min(i + 1, available.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setFocusIdx(i => Math.max(i - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (focusIdx >= 0 && focusIdx < available.length) {
          onSelect(available[focusIdx].name);
          setOpen(false);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setOpen(false);
        break;
    }
  }, [open, focusIdx, available, selected, onSelect]);

  const current = available.find(c => c.name === selected);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => { setOpen(!open); setFocusIdx(available.findIndex(c => c.name === selected)); }}
        onKeyDown={handleKeyDown}
        role="combobox"
        aria-expanded={open}
        aria-haspopup="listbox"
        className="mt-2 w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-left hover:border-white/20 focus:outline-none focus:border-blue-500/50 transition-colors flex items-center justify-between gap-2"
      >
        <span className={current ? 'text-white truncate' : 'text-slate-500'}>
          {current ? `${current.positions} ${current.potType} ${current.stack}` : 'Select config...'}
        </span>
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          className={`text-slate-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div
          role="listbox"
          className="absolute top-full left-0 right-0 mt-1 bg-[var(--cp-bg-elevated)] border border-white/10 rounded-lg shadow-xl z-30 max-h-[300px] overflow-y-auto py-1"
        >
          {available.map((c, i) => (
            <button
              key={c.name}
              role="option"
              aria-selected={c.name === selected}
              onClick={() => { onSelect(c.name); setOpen(false); }}
              onMouseEnter={() => setFocusIdx(i)}
              className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                c.name === selected
                  ? 'bg-blue-500/15 text-blue-400'
                  : i === focusIdx
                    ? 'bg-white/5 text-white'
                    : 'text-slate-300 hover:bg-white/5'
              }`}
            >
              <div className="font-medium">{c.positions} {c.potType} {c.stack}</div>
              <div className="text-[10px] text-slate-500 mt-0.5">{c.solvedFlops} boards solved</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});
