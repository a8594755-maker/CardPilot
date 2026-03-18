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

  return (
    <main className="flex-1 p-6 overflow-y-auto">
      <div className="max-w-2xl mx-auto space-y-6">
        <h2 className="text-2xl font-bold text-white">Profile</h2>

        {/* Avatar + Name */}
        <div className="glass-card p-6">
          <div className="flex items-start gap-4">
            <div className="flex w-16 sm:w-24 shrink-0 flex-col items-center gap-2">
              <div
                className={`w-12 h-12 sm:w-20 sm:h-20 rounded-full bg-gradient-to-br ${AVATAR_COLORS[prefs.avatarColor]} flex items-center justify-center text-xl sm:text-3xl font-bold text-white uppercase shadow-lg`}
              >
                {displayName[0]}
              </div>
              <div className="flex gap-1 mt-1">
                {AVATAR_COLORS.map((c: string, i: number) => (
                  <button
                    key={i}
                    onClick={() => updatePref('avatarColor', i)}
                    className={`w-3.5 h-3.5 sm:w-5 sm:h-5 rounded-full bg-gradient-to-br ${c} border-2 transition-all ${
                      prefs.avatarColor === i
                        ? 'border-white scale-110'
                        : 'border-transparent opacity-60 hover:opacity-100'
                    }`}
                  />
                ))}
              </div>
            </div>
            <div className="flex-1 min-w-0 space-y-2.5">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Display Name
                </label>
                <div className="flex items-center gap-1.5">
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="input-field flex-1 min-w-0 !py-1.5"
                    maxLength={32}
                  />
                  <button
                    onClick={handleSaveName}
                    className="btn-primary text-xs !py-1.5 !px-3 shrink-0"
                  >
                    Save
                  </button>
                </div>
                {saved && <p className="text-xs text-emerald-400">Name updated!</p>}
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Email
                </label>
                <p className="text-sm text-slate-300">{email || 'Guest account'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Bet Size Presets */}
        <div className="glass-card p-4 sm:p-6 space-y-4">
          <h3 className="text-lg font-bold text-white">Custom Bet Size Presets</h3>
          <p className="text-xs text-slate-400">
            Set your preferred bet sizes as % of pot for each street.
          </p>
          {(['flop', 'turn', 'river'] as const).map((street) => (
            <div key={street} className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                {street}
              </label>
              <div className="flex gap-1.5 sm:gap-2">
                {prefs.betPresets[street].map((val, i) => (
                  <div key={i} className="flex items-center gap-1 min-w-0">
                    <input
                      type="number"
                      value={val}
                      min={1}
                      max={500}
                      onChange={(e) => {
                        const next = [...prefs.betPresets[street]] as [number, number, number];
                        next[i] = Number(e.target.value) || 0;
                        updatePref('betPresets', { ...prefs.betPresets, [street]: next });
                      }}
                      className="input-field w-14 sm:w-20 text-center text-xs sm:text-sm"
                    />
                    <span className="text-xs text-slate-500">%</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Data Retention */}
        <div className="glass-card p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-bold text-white">Data Retention</h3>
              <p className="text-xs text-slate-400 mt-1">
                Hand history is server-authored and visible by room permissions. Toggle this to hide
                local preference data only.
              </p>
            </div>
            <button
              onClick={() => updatePref('dataRetention', !prefs.dataRetention)}
              className={`relative w-12 h-7 rounded-full transition-colors ${prefs.dataRetention ? 'bg-emerald-500' : 'bg-slate-600'}`}
            >
              <div
                className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${prefs.dataRetention ? 'translate-x-5' : 'translate-x-0.5'}`}
              />
            </button>
          </div>
          {prefs.dataRetention && (
            <div className="mt-3 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400">
              Local client preferences are stored in your browser. Hand history is stored on the
              server and follows room visibility rules.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
