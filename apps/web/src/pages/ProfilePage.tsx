import { useState } from 'react';
import { supabase, type AuthSession } from '../supabase';

const AVATAR_COLORS = [
  'from-cyan-500 to-blue-600',
  'from-amber-400 to-orange-500',
  'from-emerald-400 to-green-600',
  'from-purple-400 to-violet-600',
  'from-rose-400 to-pink-600',
  'from-teal-400 to-cyan-600',
];

const PROFILE_STORAGE_KEY = 'cardpilot_profile';

export type UserPreferences = {
  gameType: 'NLH' | 'PLO';
  blindLevel: string;
  tableType: '6-max' | '9-max';
  currency: string;
  avatarColor: number;
  betPresets: {
    flop: [number, number, number];
    turn: [number, number, number];
    river: [number, number, number];
  };
  raiseMultipliers: [number, number];
  potPercentages: [number, number, number];
  dataRetention: boolean;
};

const DEFAULT_PREFS: UserPreferences = {
  gameType: 'NLH',
  blindLevel: '50/100',
  tableType: '6-max',
  currency: 'Chips',
  avatarColor: 0,
  betPresets: {
    flop: [33, 66, 100],
    turn: [50, 75, 125],
    river: [50, 100, 200],
  },
  raiseMultipliers: [2, 3],
  potPercentages: [33, 50, 100],
  dataRetention: true,
};

export function loadPrefs(): UserPreferences {
  try {
    const raw = localStorage.getItem(PROFILE_STORAGE_KEY);
    if (raw) return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_PREFS };
}

export function savePrefs(prefs: UserPreferences): void {
  try {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

export function ProfilePage({
  displayName,
  setDisplayName,
  email,
  authSession,
}: {
  displayName: string;
  setDisplayName: (n: string) => void;
  email: string | null;
  authSession: AuthSession | null;
}) {
  const [prefs, setPrefs] = useState<UserPreferences>(loadPrefs);
  const [editName, setEditName] = useState(displayName);
  const [saved, setSaved] = useState(false);

  function updatePref<K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    savePrefs(next);
  }

  function handleSaveName() {
    const trimmed = editName.trim();
    if (!trimmed) return;
    setDisplayName(trimmed);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    // Persist to Supabase in background
    if (supabase && authSession && !authSession.isGuest) {
      supabase.auth.updateUser({ data: { display_name: trimmed } }).catch(() => {});
    }
  }

  const mults = prefs.raiseMultipliers ?? DEFAULT_PREFS.raiseMultipliers;
  const pcts = prefs.potPercentages ?? DEFAULT_PREFS.potPercentages;

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-xl mx-auto space-y-5">
        {/* ── Profile Card ── */}
        <div className="cp-lobby-card p-5 space-y-4">
          <div className="flex items-center gap-4">
            <div
              className={`w-14 h-14 rounded-full bg-gradient-to-br ${AVATAR_COLORS[prefs.avatarColor]} flex items-center justify-center text-2xl font-extrabold text-white uppercase shadow-lg shrink-0`}
            >
              {displayName[0]}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveName();
                  }}
                  className="cp-input flex-1 min-w-0 text-base font-bold"
                  maxLength={32}
                  placeholder="Display Name"
                />
                <button
                  onClick={handleSaveName}
                  className={`cp-btn text-xs px-4 py-2 shrink-0 ${saved ? 'cp-btn-success' : 'cp-btn-primary'}`}
                >
                  {saved ? 'Saved' : 'Save'}
                </button>
              </div>
              <p className="text-xs text-slate-500 mt-1.5 truncate">{email || 'Guest account'}</p>
            </div>
          </div>
        </div>

        {/* ── Action Presets ── */}
        <div className="cp-lobby-card p-5 space-y-4">
          <h3 className="text-sm font-extrabold text-white uppercase tracking-wider">
            Action Presets
          </h3>

          {/* Raise Multipliers */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <label className="text-xs font-bold text-slate-300">Facing a Bet</label>
              <span className="text-[10px] text-slate-500">Multiplier of bet size</span>
            </div>
            <div className="flex gap-2">
              {mults.map((val, i) => (
                <div key={i} className="flex items-center gap-1">
                  <input
                    type="number"
                    value={val}
                    min={1}
                    max={20}
                    step={0.5}
                    onChange={(e) => {
                      const next = [...mults] as [number, number];
                      next[i] = Number(e.target.value) || 2;
                      updatePref('raiseMultipliers', next);
                    }}
                    className="cp-input w-16 text-center text-sm font-bold"
                  />
                  <span className="text-xs text-slate-500 font-bold">x</span>
                </div>
              ))}
            </div>
          </div>

          <div className="border-t border-white/[0.04]" />

          {/* Pot Percentages */}
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <label className="text-xs font-bold text-slate-300">No Facing Bet</label>
              <span className="text-[10px] text-slate-500">% of pot</span>
            </div>
            <div className="flex gap-2">
              {pcts.map((val, i) => (
                <div key={i} className="flex items-center gap-1">
                  <input
                    type="number"
                    value={val}
                    min={1}
                    max={500}
                    onChange={(e) => {
                      const next = [...pcts] as [number, number, number];
                      next[i] = Number(e.target.value) || 33;
                      updatePref('potPercentages', next);
                    }}
                    className="cp-input w-16 text-center text-sm font-bold"
                  />
                  <span className="text-xs text-slate-500 font-bold">%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── Data Retention ── */}
        <div className="cp-lobby-card p-5">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <h3 className="text-sm font-extrabold text-white uppercase tracking-wider">
                Data Retention
              </h3>
              <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                Toggle to control local preference storage. Hand history follows room permissions.
              </p>
            </div>
            <button
              onClick={() => updatePref('dataRetention', !prefs.dataRetention)}
              className={`relative w-11 h-6 rounded-full transition-colors duration-150 shrink-0 ${prefs.dataRetention ? 'bg-emerald-500' : 'bg-slate-600'}`}
              aria-label="Toggle data retention"
            >
              <div
                className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${prefs.dataRetention ? 'translate-x-[22px]' : 'translate-x-0.5'}`}
              />
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
