import { memo } from 'react';

interface FilterChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

export const FilterChip = memo(function FilterChip({ label, active, onClick }: FilterChipProps) {
  return (
    <button
      onClick={onClick}
      className={`px-2.5 py-1 rounded-md border text-xs transition-all whitespace-nowrap ${
        active
          ? 'bg-blue-500/15 border-blue-500 text-blue-400 font-semibold'
          : 'border-white/10 text-slate-400 hover:border-blue-500/50 hover:text-slate-300'
      }`}
    >
      {label}
    </button>
  );
});
