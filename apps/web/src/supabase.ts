import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true
        }
      })
    : null;

export type AuthSession = { accessToken: string; userId: string; email?: string | null };

/* ── Client-side rate limiter ── */
const authAttempts: { timestamps: number[]; lockedUntil: number } = {
  timestamps: [],
  lockedUntil: 0,
};

const RATE_LIMIT_WINDOW_MS = 60_000;   // 1 minute window
const MAX_ATTEMPTS_PER_WINDOW = 5;      // max 5 attempts per window
const LOCKOUT_DURATION_MS = 60_000;     // 1 minute lockout after exceeding

function checkRateLimit(): void {
  const now = Date.now();
  if (now < authAttempts.lockedUntil) {
    const secsLeft = Math.ceil((authAttempts.lockedUntil - now) / 1000);
    throw new Error(`Too many attempts. Please wait ${secsLeft}s before trying again.`);
  }
  // Prune old timestamps
  authAttempts.timestamps = authAttempts.timestamps.filter(
    (t) => now - t < RATE_LIMIT_WINDOW_MS
  );
  if (authAttempts.timestamps.length >= MAX_ATTEMPTS_PER_WINDOW) {
    authAttempts.lockedUntil = now + LOCKOUT_DURATION_MS;
    throw new Error(`Too many attempts. Please wait 60s before trying again.`);
  }
  authAttempts.timestamps.push(now);
}

export function getRateLimitSecondsLeft(): number {
  const now = Date.now();
  if (now < authAttempts.lockedUntil) {
    return Math.ceil((authAttempts.lockedUntil - now) / 1000);
  }
  return 0;
}

/* ── Input validation ── */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateEmail(email: string): string | null {
  if (!email.trim()) return "Email is required.";
  if (!EMAIL_RE.test(email)) return "Please enter a valid email address.";
  return null;
}

export function validatePassword(password: string): string | null {
  if (!password) return "Password is required.";
  if (password.length < 6) return "Password must be at least 6 characters.";
  if (password.length > 72) return "Password must be 72 characters or fewer.";
  return null;
}

/* ── Friendly error mapping ── */
function friendlyAuthError(err: unknown): Error {
  const msg = err instanceof Error ? err.message : String(err);
  if (msg.includes("rate limit") || msg.includes("429")) {
    return new Error("Email rate limit exceeded. Please wait a few minutes before trying again.");
  }
  if (msg.includes("422") || msg.includes("invalid") || msg.includes("Unable to validate")) {
    return new Error("Invalid email or password format. Check your input and try again.");
  }
  if (msg.includes("User already registered")) {
    return new Error("This email is already registered. Try logging in instead.");
  }
  if (msg.includes("Invalid login credentials")) {
    return new Error("Incorrect email or password.");
  }
  return err instanceof Error ? err : new Error(msg);
}

export async function ensureGuestSession(): Promise<AuthSession | null> {
  if (!supabase) return null;

  const { data: existing } = await supabase.auth.getSession();
  if (existing.session?.access_token && existing.session.user?.id) {
    return {
      accessToken: existing.session.access_token,
      userId: existing.session.user.id,
      email: existing.session.user.email
    };
  }

  const { data, error } = await supabase.auth.signInAnonymously();
  if (error || !data.session || !data.user) {
    throw new Error(error?.message ?? "failed to sign in anonymously");
  }

  return {
    accessToken: data.session.access_token,
    userId: data.user.id,
    email: data.user.email
  };
}

export async function signUpWithEmail(email: string, password: string): Promise<AuthSession> {
  if (!supabase) throw new Error("Supabase not configured");

  const emailErr = validateEmail(email);
  if (emailErr) throw new Error(emailErr);
  const pwErr = validatePassword(password);
  if (pwErr) throw new Error(pwErr);

  checkRateLimit();

  try {
    const { data, error } = await supabase.auth.signUp({ email, password });
    if (error) throw error;
    if (!data.session || !data.user) throw new Error("Sign up succeeded but no session returned. Check your email for confirmation.");
    return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email };
  } catch (err) {
    throw friendlyAuthError(err);
  }
}

export async function signInWithEmail(email: string, password: string): Promise<AuthSession> {
  if (!supabase) throw new Error("Supabase not configured");

  const emailErr = validateEmail(email);
  if (emailErr) throw new Error(emailErr);
  const pwErr = validatePassword(password);
  if (pwErr) throw new Error(pwErr);

  checkRateLimit();

  try {
    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) throw error;
    if (!data.session || !data.user) throw new Error("Sign in failed");
    return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email };
  } catch (err) {
    throw friendlyAuthError(err);
  }
}

export async function signOut(): Promise<void> {
  if (!supabase) return;
  await supabase.auth.signOut();
}
