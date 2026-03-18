import { memo } from 'react';

interface SegmentedControlProps<T extends string> {
  label?: string;
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
}

function SegmentedControlInner<T extends string>({
  label,
  options,
  value,
  onChange,
  size = 'md',
}: SegmentedControlProps<T>) {
  const btnPad = size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-4 py-1.5 text-[13px]';
  return (
    <div>
      {label && (
        <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
          {label}
        </div>
      )}
      <div className="inline-flex gap-0.5 bg-white/5 rounded-lg p-0.5">
        {options.map((opt) => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`${btnPad} rounded-md font-medium transition-all ${
              value === opt.value
                ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export const SegmentedControl = memo(SegmentedControlInner) as typeof SegmentedControlInner;
