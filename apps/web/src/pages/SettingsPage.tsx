import { useState, useCallback, type ChangeEvent } from "react";

/* ─── Timezone options ─── */
const TIMEZONE_OPTIONS = [
  { value: "America/New_York", label: "Eastern (ET)" },
  { value: "America/Chicago", label: "Central (CT)" },
  { value: "America/Denver", label: "Mountain (MT)" },
  { value: "America/Los_Angeles", label: "Pacific (PT)" },
  { value: "Europe/London", label: "London (GMT)" },
  { value: "Europe/Berlin", label: "Berlin (CET)" },
  { value: "Asia/Tokyo", label: "Tokyo (JST)" },
  { value: "Asia/Taipei", label: "Taipei (CST)" },
  { value: "Australia/Sydney", label: "Sydney (AEST)" },
];

const STAKES_OPTIONS = [
  { value: "1/2", label: "1/2" },
  { value: "2/5", label: "2/5" },
  { value: "5/10", label: "5/10" },
  { value: "10/20", label: "10/20" },
  { value: "25/50", label: "25/50" },
  { value: "50/100", label: "50/100" },
];

/* ─── Reusable sub-components ─── */

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="glass-card p-5 space-y-4">
      <div>
        <h3 className="text-base font-bold text-white">{title}</h3>
        {description && (
          <p className="text-xs text-slate-400 mt-1 leading-relaxed">{description}</p>
        )}
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium text-slate-200">{label}</p>
        {description && (
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange(!checked)}
        className={`relative shrink-0 w-11 h-6 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900 ${
          checked ? "bg-emerald-500" : "bg-slate-600"
        }`}
      >
        <span
          className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-transform ${
            checked ? "translate-x-[22px]" : "translate-x-0.5"
          }`}
        />
      </button>
    </div>
  );
}

function SelectRow({
  label,
  description,
  value,
  options,
  onChange,
}: {
  label: string;
  description?: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (next: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0 flex-1">
        <label className="text-sm font-medium text-slate-200">{label}</label>
        {description && (
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
        )}
      </div>
      <select
        value={value}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
        className="input-field w-44 text-sm shrink-0"
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function TextRow({
  label,
  description,
  value,
  onChange,
  placeholder,
  error,
}: {
  label: string;
  description?: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  error?: string;
}) {
  return (
    <div className="py-2">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 flex-1">
          <label className="text-sm font-medium text-slate-200">{label}</label>
          {description && (
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">{description}</p>
          )}
        </div>
        <input
          type="text"
          value={value}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          placeholder={placeholder}
          className={`input-field w-56 text-sm shrink-0 ${
            error ? "!border-red-500/60 focus:!border-red-500" : ""
          }`}
          aria-label={label}
          aria-invalid={!!error}
        />
      </div>
      {error && (
        <p className="text-xs text-red-400 mt-1.5 text-right" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function DangerZone() {
  const [confirming, setConfirming] = useState(false);

  return (
    <SectionCard
      title="Danger Zone"
      description="Irreversible actions. Proceed with caution."
    >
      <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-red-300">Delete Account</p>
            <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
              Permanently remove your account and all associated data. This cannot be undone.
            </p>
          </div>
          {!confirming ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="btn-danger text-sm !py-2 !px-4 shrink-0"
            >
              Delete Account
            </button>
          ) : (
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="btn-ghost text-sm !py-2 !px-3"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  /* In a real app, this would call an API */
                  setConfirming(false);
                }}
                className="btn-danger text-sm !py-2 !px-4 animate-pulse"
              >
                Confirm Delete
              </button>
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
}

/* ─── Inline SVG Icons (minimal) ─── */

function CheckIcon() {
  return (
    <svg
      className="w-4 h-4"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 8.5l3.5 3.5 6.5-7" />
    </svg>
  );
}

function SpinnerIcon() {
  return (
    <svg className="w-4 h-4 animate-spin" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth={2} opacity={0.25} />
      <path
        d="M8 2a6 6 0 0 1 6 6"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
      />
    </svg>
  );
}

/* ═══════════════════ MAIN SETTINGS PAGE ═══════════════════ */

interface SettingsState {
  displayName: string;
  email: string;
  timezone: string;
  autoBuyIn: boolean;
  defaultStakes: string;
  soundEffects: boolean;
  hideFromLeaderboard: boolean;
}

const DEFAULT_STATE: SettingsState = {
  displayName: "HeroPlayer",
  email: "player@cardpilot.app",
  timezone: "America/New_York",
  autoBuyIn: true,
  defaultStakes: "5/10",
  soundEffects: true,
  hideFromLeaderboard: false,
};

export function SettingsPage() {
  const [state, setState] = useState<SettingsState>({ ...DEFAULT_STATE });
  const [savedState, setSavedState] = useState<SettingsState>({ ...DEFAULT_STATE });
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);

  const update = useCallback(
    <K extends keyof SettingsState>(key: K, value: SettingsState[K]) => {
      setState((prev) => ({ ...prev, [key]: value }));
      setJustSaved(false);
    },
    [],
  );

  /* ── Validation ── */
  const nameError =
    state.displayName.trim().length > 0 && state.displayName.trim().length < 3
      ? "Display name must be at least 3 characters"
      : state.displayName.trim().length === 0
        ? "Display name is required"
        : undefined;

  const hasChanges = JSON.stringify(state) !== JSON.stringify(savedState);
  const canSave = !nameError && hasChanges && !saving;

  /* ── Mock save ── */
  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setJustSaved(false);
    await new Promise((r) => setTimeout(r, 800));
    setSavedState({ ...state });
    setSaving(false);
    setJustSaved(true);
    setTimeout(() => setJustSaved(false), 3000);
  }

  function handleReset() {
    setState({ ...savedState });
    setJustSaved(false);
  }

  return (
    <main className="flex-1 flex flex-col overflow-hidden">
      {/* ── Sticky Header ── */}
      <header className="shrink-0 border-b border-white/5 bg-[rgba(10,15,26,0.85)] backdrop-blur-lg z-10">
        <div className="max-w-5xl mx-auto flex items-center justify-between px-4 sm:px-6 py-3">
          <div className="min-w-0">
            <h2 className="text-xl font-bold text-white truncate">Settings</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Manage your profile, gameplay, and privacy preferences
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {justSaved && (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-400 font-medium animate-[fadeSlideUp_0.25s_ease-out]">
                <CheckIcon />
                Saved
              </span>
            )}
            <button
              type="button"
              onClick={handleReset}
              disabled={!hasChanges || saving}
              className="btn-ghost text-sm !py-2 !px-4 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Reset
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              className="btn-primary text-sm !py-2 !px-5 disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {saving && <SpinnerIcon />}
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Content ── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* ─── Left Column ─── */}
            <div className="space-y-5">
              {/* Profile */}
              <SectionCard
                title="Profile"
                description="Your public identity on CardPilot."
              >
                <TextRow
                  label="Display Name"
                  description="Visible to other players at the table"
                  value={state.displayName}
                  onChange={(v) => update("displayName", v)}
                  placeholder="Enter your name"
                  error={nameError}
                />
                <div className="py-2">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-200">Email</p>
                      <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                        Your account email cannot be changed here
                      </p>
                    </div>
                    <p className="text-sm text-slate-400 font-mono bg-white/5 px-3 py-2 rounded-lg border border-white/5 shrink-0 max-w-[220px] truncate">
                      {state.email}
                    </p>
                  </div>
                </div>
                <SelectRow
                  label="Time Zone"
                  description="Used for hand history timestamps"
                  value={state.timezone}
                  options={TIMEZONE_OPTIONS}
                  onChange={(v) => update("timezone", v)}
                />
              </SectionCard>

              {/* Gameplay */}
              <SectionCard
                title="Gameplay"
                description="Customize your table experience."
              >
                <ToggleRow
                  label="Auto Buy-in"
                  description="Automatically buy in when joining a table"
                  checked={state.autoBuyIn}
                  onChange={(v) => update("autoBuyIn", v)}
                />
                <div className="border-t border-white/5" />
                <SelectRow
                  label="Default Table Stakes"
                  description="Pre-selected stakes when creating a room"
                  value={state.defaultStakes}
                  options={STAKES_OPTIONS}
                  onChange={(v) => update("defaultStakes", v)}
                />
                <div className="border-t border-white/5" />
                <ToggleRow
                  label="Sound Effects"
                  description="Play audio feedback for actions and alerts"
                  checked={state.soundEffects}
                  onChange={(v) => update("soundEffects", v)}
                />
              </SectionCard>
            </div>

            {/* ─── Right Column ─── */}
            <div className="space-y-5">
              {/* Privacy */}
              <SectionCard
                title="Privacy"
                description="Control who can see your information."
              >
                <ToggleRow
                  label="Hide Profile from Leaderboard"
                  description="Your stats and ranking will be hidden from public leaderboards"
                  checked={state.hideFromLeaderboard}
                  onChange={(v) => update("hideFromLeaderboard", v)}
                />
              </SectionCard>

              {/* Danger Zone */}
              <DangerZone />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
