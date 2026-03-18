import { useSolverConfig } from '../../stores/solver-config';
import type { AdvancedPlayerConfig } from '../../stores/solver-config';

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, accentColor: '#2980b9' }}
      />
      <span className="gto-label" style={{ fontSize: 12 }}>
        {label}
      </span>
    </div>
  );
}

function PlayerSection({
  title,
  config,
  onChange,
}: {
  title: string;
  config: AdvancedPlayerConfig;
  onChange: (c: Partial<AdvancedPlayerConfig>) => void;
}) {
  return (
    <div style={{ flex: 1 }}>
      <div className="gto-label" style={{ fontWeight: 700, marginBottom: 8, fontSize: 13 }}>
        {title}
      </div>

      <div
        style={{ border: '1px solid #bbb', borderRadius: 4, padding: 12, background: '#f8f8f8' }}
      >
        <div className="gto-label-muted" style={{ marginBottom: 8 }}>
          Default Settings:
        </div>

        {/* Default bet % pot */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
          <span className="gto-label" style={{ fontSize: 12 }}>
            Default bet:
          </span>
          <input
            type="number"
            value={config.defaultBetPct}
            onChange={(e) => onChange({ defaultBetPct: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 60, textAlign: 'center', fontSize: 12 }}
            min={0}
            max={500}
          />
          <span className="gto-label" style={{ fontSize: 12 }}>
            % pot
          </span>
        </div>

        {/* Auto-allocate last two */}
        <ToggleRow
          label="Only 2 bet opportunities, auto-allocate"
          checked={config.autoAllocateLastTwo}
          onChange={(v) => onChange({ autoAllocateLastTwo: v })}
        />

        {/* No donk bet */}
        <ToggleRow
          label="Don't donk bet (unless aggressive)"
          checked={config.noDonkBet}
          onChange={(v) => onChange({ noDonkBet: v })}
        />

        {/* All-in threshold */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <input
            type="checkbox"
            checked={config.allInThresholdEnabled}
            onChange={(e) => onChange({ allInThresholdEnabled: e.target.checked })}
            style={{ width: 16, height: 16, accentColor: '#2980b9' }}
          />
          <span className="gto-label" style={{ fontSize: 12 }}>
            If eff. stack &lt;
          </span>
          <input
            type="number"
            value={config.allInThresholdPct}
            onChange={(e) => onChange({ allInThresholdPct: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 50, textAlign: 'center', fontSize: 12 }}
            disabled={!config.allInThresholdEnabled}
          />
          <span className="gto-label" style={{ fontSize: 12 }}>
            % pot, all-in
          </span>
        </div>

        {/* Remaining bet threshold */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <input
            type="checkbox"
            checked={config.remainingBetAllIn}
            onChange={(e) => onChange({ remainingBetAllIn: e.target.checked })}
            style={{ width: 16, height: 16, accentColor: '#2980b9' }}
          />
          <span className="gto-label" style={{ fontSize: 12 }}>
            If remaining bet &lt;
          </span>
          <input
            type="number"
            value={config.remainingBetPct}
            onChange={(e) => onChange({ remainingBetPct: Number(e.target.value) })}
            className="gto-input"
            style={{ width: 50, textAlign: 'center', fontSize: 12 }}
            disabled={!config.remainingBetAllIn}
          />
          <span className="gto-label" style={{ fontSize: 12 }}>
            % pot, all-in
          </span>
        </div>

        <hr style={{ border: 'none', borderTop: '1px solid #ccc', margin: '10px 0' }} />

        {/* Custom street settings */}
        <ToggleRow
          label="Use custom flop settings"
          checked={config.useCustomFlop}
          onChange={(v) => onChange({ useCustomFlop: v })}
        />
        <ToggleRow
          label="Use custom turn settings"
          checked={config.useCustomTurn}
          onChange={(v) => onChange({ useCustomTurn: v })}
        />
        <ToggleRow
          label="Use custom river settings"
          checked={config.useCustomRiver}
          onChange={(v) => onChange({ useCustomRiver: v })}
        />
      </div>
    </div>
  );
}

export function AdvancedBetTab() {
  const { advancedConfig, setAdvancedConfig } = useSolverConfig();

  return (
    <div style={{ padding: '16px 12px', display: 'flex', gap: 16 }}>
      <PlayerSection
        title="OOP Settings"
        config={advancedConfig.oop}
        onChange={(c) => setAdvancedConfig('oop', c)}
      />
      <PlayerSection
        title="IP Settings"
        config={advancedConfig.ip}
        onChange={(c) => setAdvancedConfig('ip', c)}
      />
    </div>
  );
}
