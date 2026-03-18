import type { CashConfig } from '../../stores/solver-config';
import { NumericInput } from '../ui/NumericInput';

interface CashTabProps {
  config: CashConfig;
  onChange: (changes: Partial<CashConfig>) => void;
}

export function CashTab({ config, onChange }: CashTabProps) {
  return (
    <div style={{ padding: '24px 32px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <FieldRow
          label="Starting Pot"
          value={config.startingPot}
          onChange={(v) => onChange({ startingPot: v })}
          min={0.5}
          step={0.5}
        />
        <FieldRow
          label="Effective Stacks"
          value={config.effectiveStack}
          onChange={(v) => onChange({ effectiveStack: v })}
          min={1}
          step={1}
        />
        <FieldRow
          label="Rake (%)"
          value={config.rakePercent}
          onChange={(v) => onChange({ rakePercent: v })}
          min={0}
          max={100}
          step={0.5}
          suffix="%"
        />
        <FieldRow
          label="Rake Cap"
          value={config.rakeCap}
          onChange={(v) => onChange({ rakeCap: v })}
          min={0}
          step={0.5}
        />
      </div>
    </div>
  );
}

function FieldRow({
  label,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <label className="gto-label" style={{ width: 120, textAlign: 'right', flexShrink: 0 }}>
        {label}
      </label>
      <div style={{ position: 'relative', width: 120 }}>
        <NumericInput
          value={value}
          onChange={onChange}
          min={min}
          max={max}
          step={step}
          className="gto-input"
          style={{ textAlign: 'center' }}
        />
        {suffix && (
          <span
            style={{
              position: 'absolute',
              right: 8,
              top: '50%',
              transform: 'translateY(-50%)',
              fontSize: 11,
              color: '#888',
            }}
          >
            {suffix}
          </span>
        )}
      </div>
    </div>
  );
}
