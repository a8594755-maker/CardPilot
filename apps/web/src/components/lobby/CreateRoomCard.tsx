import { memo, useState, useCallback } from 'react';

/** Common blind presets */
const BLIND_PRESETS = [
  { label: '1/2', sb: 1, bb: 2 },
  { label: '1/3', sb: 1, bb: 3 },
  { label: '2/5', sb: 2, bb: 5 },
  { label: '5/10', sb: 5, bb: 10 },
  { label: '10/20', sb: 10, bb: 20 },
  { label: '25/50', sb: 25, bb: 50 },
] as const;

export interface CreateRoomSettings {
  sb: number;
  bb: number;
  buyInMin: number;
  buyInMax: number;
  maxPlayers: number;
  visibility: 'public' | 'private';
}

export interface CreateRoomCardProps {
  disabled: boolean;
  settings: CreateRoomSettings;
  onSettingsChange: (next: CreateRoomSettings) => void;
  onCreate: (settings: CreateRoomSettings) => void;
  /** If true, start with the card expanded (e.g. from Quick Play → Customize) */
  initialExpanded?: boolean;
}

/* Small chevron SVG for the advanced toggle */
function ChevronRight() {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 4l4 4-4 4" />
    </svg>
  );
}

/* Stepper control for numeric values */
function Stepper({
  value,
  min,
  max,
  step = 1,
  unit,
  onChange,
}: {
  value: number;
  min: number;
  max?: number;
  step?: number;
  unit?: string;
  onChange: (v: number) => void;
}) {
  return (
    <div className="cp-stepper w-full">
      <button
        className="cp-stepper-btn"
        disabled={value <= min}
        onClick={() => onChange(Math.max(min, value - step))}
        aria-label="Decrease"
      >
        −
      </button>
      <span className="cp-stepper-value flex-1">
        {value.toLocaleString()}
        {unit && <span className="text-xs text-slate-400 ml-0.5">{unit}</span>}
      </span>
      <button
        className="cp-stepper-btn"
        disabled={max != null && value >= max}
        onClick={() => onChange(max != null ? Math.min(max, value + step) : value + step)}
        aria-label="Increase"
      >
        +
      </button>
    </div>
  );
}

export const CreateRoomCard = memo(function CreateRoomCard({
  disabled,
  settings,
  onSettingsChange,
  onCreate,
  initialExpanded = false,
}: CreateRoomCardProps) {
  const [showAdvanced, setShowAdvanced] = useState(initialExpanded);
  const [customBlinds, setCustomBlinds] = useState(false);

  const { sb, bb, buyInMin, buyInMax, maxPlayers, visibility } = settings;

  const update = useCallback(
    (partial: Partial<CreateRoomSettings>) => {
      onSettingsChange({ ...settings, ...partial });
    },
    [settings, onSettingsChange],
  );

  const selectPreset = useCallback(
    (preset: (typeof BLIND_PRESETS)[number]) => {
      setCustomBlinds(false);
      const newBuyInMin = preset.bb * 20;
      const newBuyInMax = preset.bb * 100;
      update({
        sb: preset.sb,
        bb: preset.bb,
        buyInMin: newBuyInMin,
        buyInMax: newBuyInMax,
      });
    },
    [update],
  );

  const validationError =
    bb <= sb
      ? 'Big blind must be greater than small blind'
      : buyInMax < buyInMin
        ? 'Max buy-in must be ≥ min buy-in'
        : null;

  const handleCreate = useCallback(() => {
    if (!validationError) onCreate(settings);
  }, [validationError, onCreate, settings]);

  return (
    <div className="cp-lobby-card">
      <h2 className="cp-lobby-title">Create a Room</h2>
      <p className="cp-lobby-subtitle mt-1">Set up your own table with custom stakes.</p>

      <div className="mt-5 space-y-4">
        {/* ── Blinds ── */}
        <div>
          <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
            Blinds
          </label>
          <div className="flex flex-wrap gap-1.5">
            {BLIND_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => selectPreset(p)}
                className={`cp-btn text-[11px] px-2.5 py-1 ${
                  !customBlinds && p.sb === sb && p.bb === bb ? 'cp-btn-primary' : 'cp-btn-ghost'
                }`}
                style={{ minHeight: 28 }}
              >
                {p.label}
              </button>
            ))}
            <button
              onClick={() => setCustomBlinds(true)}
              className={`cp-btn text-[11px] px-2.5 py-1 ${
                customBlinds ? 'cp-btn-primary' : 'cp-btn-ghost'
              }`}
              style={{ minHeight: 28 }}
            >
              Custom
            </button>
          </div>

          {customBlinds && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Small Blind</label>
                <Stepper
                  value={sb}
                  min={1}
                  step={1}
                  onChange={(v) => update({ sb: v, bb: Math.max(v + 1, bb) })}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Big Blind</label>
                <Stepper value={bb} min={sb + 1} step={1} onChange={(v) => update({ bb: v })} />
              </div>
            </div>
          )}
        </div>

        {/* ── Buy-in (presets in basic, steppers in advanced) ── */}
        <div>
          <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
            Buy-in Range
            <span className="ml-2 font-normal normal-case text-slate-500">
              ({buyInMin.toLocaleString()} – {buyInMax.toLocaleString()} chips)
            </span>
          </label>
          <div className="flex flex-wrap gap-1.5">
            {[
              { label: '20×BB', min: bb * 20, max: bb * 100 },
              { label: '40×BB', min: bb * 40, max: bb * 200 },
              { label: '100×BB', min: bb * 100, max: bb * 300 },
            ].map((p) => (
              <button
                key={p.label}
                onClick={() => update({ buyInMin: p.min, buyInMax: p.max })}
                className={`cp-btn text-[11px] px-2.5 py-1 ${
                  buyInMin === p.min && buyInMax === p.max ? 'cp-btn-primary' : 'cp-btn-ghost'
                }`}
                style={{ minHeight: 28 }}
              >
                {p.label}
                <span className="ml-1 text-[10px] text-slate-400 font-normal">
                  ({p.min}–{p.max})
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* ── Max Players ── */}
        <div>
          <label className="block text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">
            Table Size
          </label>
          <div className="flex gap-2">
            {(
              [
                { n: 2, label: 'Heads-up' },
                { n: 6, label: '6-max' },
                { n: 9, label: '9-max' },
              ] as const
            ).map(({ n, label }) => (
              <button
                key={n}
                onClick={() => update({ maxPlayers: n })}
                className={`cp-btn text-[11px] px-3 py-1 flex-1 ${
                  maxPlayers === n ? 'cp-btn-primary' : 'cp-btn-ghost'
                }`}
                style={{ minHeight: 28 }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* ── Advanced section (collapsed) ── */}
        <button
          className="cp-advanced-toggle"
          data-open={showAdvanced ? 'true' : 'false'}
          onClick={() => setShowAdvanced(!showAdvanced)}
        >
          <ChevronRight />
          Advanced settings
        </button>

        {showAdvanced && (
          <div className="space-y-4 pl-1 animate-[cpFadeSlideUp_150ms_ease-out]">
            {/* Min/Max buy-in steppers (shown when advanced is open) */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-500 mb-1">Min Buy-in</label>
                <Stepper
                  value={buyInMin}
                  min={1}
                  max={buyInMax}
                  step={Math.max(1, bb * 5)}
                  unit="chips"
                  onChange={(v) => update({ buyInMin: v })}
                />
              </div>
              <div>
                <label className="block text-xs text-slate-500 mb-1">Max Buy-in</label>
                <Stepper
                  value={buyInMax}
                  min={buyInMin}
                  step={Math.max(1, bb * 10)}
                  unit="chips"
                  onChange={(v) => update({ buyInMax: v })}
                />
              </div>
            </div>

            {/* Visibility */}
            <div>
              <label className="block text-xs text-slate-500 mb-1">Room Visibility</label>
              <div className="flex gap-2">
                <button
                  onClick={() => update({ visibility: 'public' })}
                  className={`cp-btn text-[11px] px-3 py-1 flex-1 ${
                    visibility === 'public' ? 'cp-btn-success' : 'cp-btn-ghost'
                  }`}
                  style={{ minHeight: 28 }}
                >
                  Public
                </button>
                <button
                  onClick={() => update({ visibility: 'private' })}
                  className={`cp-btn text-[11px] px-3 py-1 flex-1 ${
                    visibility === 'private' ? 'cp-btn-primary' : 'cp-btn-ghost'
                  }`}
                  style={{ minHeight: 28 }}
                >
                  Private
                </button>
              </div>
            </div>

            {/* Full player count selector */}
            <div>
              <label className="block text-xs text-slate-500 mb-1">Max Players</label>
              <select
                value={maxPlayers}
                onChange={(e) => update({ maxPlayers: Number(e.target.value) })}
                className="cp-lobby-select"
              >
                {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
                  <option key={n} value={n}>
                    {n} players
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* ── Live summary line ── */}
        <div className="cp-summary-line cp-num text-left">
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[13px] leading-tight">
            <span className="text-white whitespace-nowrap">{maxPlayers}-max</span>
            <span className="whitespace-nowrap">
              Blinds{' '}
              <span className="text-white">
                {sb}/{bb}
              </span>
            </span>
            <span className="whitespace-nowrap">
              Buy-in{' '}
              <span className="text-white">
                {buyInMin.toLocaleString()}–{buyInMax.toLocaleString()}
              </span>
            </span>
            <span
              className={`whitespace-nowrap ${visibility === 'private' ? 'text-amber-400' : 'text-emerald-400'}`}
            >
              {visibility === 'private' ? 'Private' : 'Public'}
            </span>
          </div>
        </div>

        {/* Validation error */}
        {validationError && (
          <p className="text-sm text-red-400 text-center font-medium">{validationError}</p>
        )}

        {/* ── CTA ── */}
        <button
          disabled={disabled || !!validationError}
          onClick={handleCreate}
          className="cp-btn cp-btn-primary w-full text-base font-bold py-3"
        >
          Create Room
        </button>
      </div>
    </div>
  );
});
