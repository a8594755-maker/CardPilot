import type { GeometricBetConfig } from '../../stores/solver-config';
import { NumericInput } from '../ui/NumericInput';

interface GeometricBetTabProps {
  config: GeometricBetConfig;
  startingPot: number;
  effectiveStack: number;
  onAllInBetIndexChange: (index: number) => void;
  onBetAmountChange: (index: number, amount: number) => void;
}

const BET_LABELS = ['1st bet', '2nd bet', '3rd bet', '4th bet', '5th bet'];

export function GeometricBetTab({
  config,
  startingPot,
  effectiveStack,
  onAllInBetIndexChange,
  onBetAmountChange,
}: GeometricBetTabProps) {
  return (
    <div style={{ padding: '20px 16px' }}>
      {/* Bet rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {BET_LABELS.map((label, i) => {
          const isSelected = i === config.allInBetIndex;
          const isActive = i <= config.allInBetIndex;

          return (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                opacity: isActive ? 1 : 0.35,
              }}
            >
              {/* Radio button */}
              <div
                className={`gto-radio ${isSelected ? 'active' : ''}`}
                onClick={() => onAllInBetIndexChange(i)}
              />

              {/* Label */}
              <span className="gto-label" style={{ width: 56, flexShrink: 0 }}>
                {label}
              </span>

              {/* Bet amount input */}
              <NumericInput
                value={isActive ? config.betAmounts[i] : 0}
                onChange={(v) => onBetAmountChange(i, v)}
                disabled={!isActive}
                step={0.01}
                min={0}
                className="gto-input"
                style={{
                  width: 100,
                  textAlign: 'right',
                  opacity: isActive ? 1 : 0.3,
                }}
              />

              {/* Pot percentage display */}
              <span className="gto-label-muted" style={{ width: 100, textAlign: 'right' }}>
                {isActive && config.betPotPcts[i] > 0
                  ? `${config.betPotPcts[i].toFixed(2)}% pot`
                  : ''}
              </span>
            </div>
          );
        })}
      </div>

      {/* Summary */}
      <div style={{ marginTop: 20, paddingTop: 12, borderTop: '1px solid #ccc' }}>
        <div className="gto-summary">Starting Pot: {startingPot.toFixed(3)}</div>
        <div className="gto-summary">Effective Stacks: {effectiveStack.toFixed(1)}</div>
      </div>
    </div>
  );
}
