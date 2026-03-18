import { useState, useEffect } from 'react';
import {
  ensureGuestSession,
  signUpWithEmail,
  signInWithEmail,
  signInWithGoogle,
  supabase,
  isSupabaseUnreachable,
  onSupabaseProbeResult,
  validateEmail,
  validatePassword,
  getRateLimitSecondsLeft,
  type AuthSession,
} from '../supabase';

export function AuthScreen({
  onAuth,
  disableGuest = false,
  gateMessage,
}: {
  onAuth: (s: AuthSession) => void;
  disableGuest?: boolean;
  gateMessage?: string;
}) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [authDisplayName, setAuthDisplayName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [cooldown, setCooldown] = useState(0);
  const [sbDown, setSbDown] = useState(isSupabaseUnreachable());

  /* Re-render when connectivity probe completes */
  useEffect(() => onSupabaseProbeResult(setSbDown), []);

  /* Cooldown countdown timer */
  useEffect(() => {
    const secs = getRateLimitSecondsLeft();
    if (secs > 0) setCooldown(secs);
    if (cooldown <= 0) return;
    const t = setInterval(() => {
      const left = getRateLimitSecondsLeft();
      setCooldown(left);
      if (left <= 0) clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [cooldown]);

  /* Real-time validation hints */
  const emailHint = email ? validateEmail(email) : null;
  const pwHint = password ? validatePassword(password) : null;
  const confirmHint =
    mode === 'signup' && confirmPw && confirmPw !== password ? 'Passwords do not match.' : null;

  const nameHint =
    mode === 'signup' && authDisplayName.length > 0 && authDisplayName.trim().length < 2
      ? 'Name must be at least 2 characters.'
      : null;

  const formValid =
    !emailHint &&
    !pwHint &&
    !confirmHint &&
    !nameHint &&
    email.length > 0 &&
    password.length > 0 &&
    (mode === 'login' || (confirmPw === password && authDisplayName.trim().length >= 2));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!formValid) {
      setError(emailHint || pwHint || confirmHint || 'Please fill in all fields correctly.');
      return;
    }

    setLoading(true);
    try {
      if (mode === 'signup') {
        const session = await signUpWithEmail(email, password, authDisplayName.trim());
        onAuth(session);
      } else {
        const session = await signInWithEmail(email, password);
        onAuth(session);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('Check your email')) {
        setSuccessMsg(msg);
      } else {
        setError(msg);
      }
      /* Refresh cooldown in case rate limiter kicked in */
      const secs = getRateLimitSecondsLeft();
      if (secs > 0) setCooldown(secs);
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogleSignIn() {
    setError('');
    setSuccessMsg('');
    setLoading(true);
    try {
      await signInWithGoogle();
      setSuccessMsg('Redirecting to Google...');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleGuest() {
    if (disableGuest) {
      setError('Club access requires a logged-in account.');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const guestName = authDisplayName.trim() || 'Guest';
      const session = await ensureGuestSession(guestName);
      if (session) onAuth(session);
      else setError('Supabase not configured — cannot create guest session');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const isDisabled = loading || cooldown > 0;

  return (
    <div className="cp-auth-screen min-h-screen p-4 flex justify-center">
      <div className="cp-auth-shell w-full max-w-md my-auto">
        {/* Logo */}
        <div className="cp-auth-brand text-center mb-8">
          <div className="cp-auth-logo w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center text-3xl font-extrabold text-slate-900 shadow-xl mx-auto mb-4">
            C
          </div>
          <h1 className="cp-auth-title text-3xl font-bold text-white">
            Card<span className="text-amber-400">Pilot</span>
          </h1>
          <p className="cp-auth-subtitle text-slate-500 text-sm mt-2">GTO-powered poker training</p>
        </div>

        {/* Card */}
        <div className="cp-auth-card glass-card p-8">
          {gateMessage && (
            <div className="cp-auth-gate mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm text-amber-300">
              {gateMessage}
            </div>
          )}
          {sbDown && (
            <div className="mb-4 p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm text-amber-300">
              Auth service is temporarily unavailable. You can continue as Guest.
            </div>
          )}
          {/* Google OAuth — prominent, above email form */}
          {supabase && !sbDown && (
            <>
              <button
                type="button"
                onClick={handleGoogleSignIn}
                disabled={loading}
                className="cp-auth-google-btn w-full py-3.5 text-sm font-semibold rounded-xl border border-white/15 bg-white text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2.5 shadow-sm"
              >
                <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="#4285F4"
                    d="M21.2 12.2c0-.7-.1-1.4-.2-2H12v3.9h5.2c-.2 1.2-.9 2.2-2 2.9v2.4h3.2c1.9-1.7 3-4.3 3-7.2z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 22c2.7 0 4.9-.9 6.5-2.4l-3.2-2.4c-.9.6-2 1-3.4 1-2.6 0-4.8-1.8-5.6-4.1H3.1v2.5C4.7 19.8 8.1 22 12 22z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M6.4 14.1c-.2-.6-.3-1.3-.3-2s.1-1.4.3-2V7.5H3.1C2.4 8.9 2 10.4 2 12s.4 3.1 1.1 4.5l3.3-2.4z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.8c1.5 0 2.8.5 3.9 1.5l2.9-2.9C16.9 2.7 14.7 1.8 12 1.8 8.1 1.8 4.7 4 3.1 7.5l3.3 2.5c.8-2.4 3-4.2 5.6-4.2z"
                  />
                </svg>
                Continue with Google
              </button>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-white/10" />
                </div>
                <div className="relative flex justify-center">
                  <span className="bg-[#0f1724] px-3 text-xs text-slate-500">
                    or continue with email
                  </span>
                </div>
              </div>
            </>
          )}

          {/* Tab switcher */}
          <div className="cp-auth-tabs flex gap-1 bg-white/5 rounded-xl p-1 mb-6">
            {(['login', 'signup'] as const).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMode(m);
                  setError('');
                  setSuccessMsg('');
                  setConfirmPw('');
                }}
                className={`cp-auth-tab-btn flex-1 py-2.5 rounded-lg text-sm font-medium transition-all ${mode === m ? 'bg-white/10 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}
              >
                {m === 'login' ? 'Log In' : 'Sign Up'}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="cp-auth-form space-y-4">
            {mode === 'signup' && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Display Name
                </label>
                <input
                  value={authDisplayName}
                  onChange={(e) => setAuthDisplayName(e.target.value)}
                  placeholder="How others see you"
                  maxLength={32}
                  className="input-field w-full"
                />
                {nameHint && <p className="text-xs text-amber-400 mt-1">{nameHint}</p>}
              </div>
            )}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="input-field w-full"
              />
              {emailHint && <p className="text-xs text-amber-400 mt-1">{emailHint}</p>}
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Min 6 characters"
                minLength={6}
                className="input-field w-full"
              />
              {pwHint && <p className="text-xs text-amber-400 mt-1">{pwHint}</p>}
            </div>

            {mode === 'signup' && (
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">
                  Confirm Password
                </label>
                <input
                  type="password"
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  required
                  placeholder="Re-enter password"
                  minLength={6}
                  className="input-field w-full"
                />
                {confirmHint && <p className="text-xs text-red-400 mt-1">{confirmHint}</p>}
              </div>
            )}

            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-sm text-red-400">
                {error}
              </div>
            )}
            {successMsg && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-sm text-emerald-400">
                {successMsg}
              </div>
            )}

            {cooldown > 0 && (
              <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm text-amber-400 text-center">
                Rate limited — please wait {cooldown}s
              </div>
            )}

            <button
              type="submit"
              disabled={isDisabled || !formValid}
              className="cp-auth-submit-btn btn-primary w-full !py-3 text-base font-semibold disabled:opacity-40"
            >
              {loading
                ? '...'
                : cooldown > 0
                  ? `Wait ${cooldown}s`
                  : mode === 'login'
                    ? 'Log In'
                    : 'Create Account'}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-white/10" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-[#0f1724] px-3 text-xs text-slate-500">or</span>
            </div>
          </div>

          <div className="space-y-3">
            <input
              value={authDisplayName}
              onChange={(e) => setAuthDisplayName(e.target.value)}
              placeholder="Enter your name (optional)"
              maxLength={32}
              className="input-field w-full text-center text-sm"
            />
            <button
              onClick={handleGuest}
              disabled={isDisabled || disableGuest}
              className="cp-auth-guest-btn btn-ghost w-full !py-3 text-sm"
            >
              {disableGuest ? 'Guest Access Disabled for Clubs' : 'Continue as Guest'}
            </button>
          </div>
        </div>

        <p className="cp-auth-legal text-center text-xs text-slate-600 mt-4">
          By continuing, you agree to our Terms of Service
        </p>
      </div>
    </div>
  );
}
