import { createClient } from "@supabase/supabase-js";

export type AuthSession = { accessToken: string; userId: string; email?: string | null; displayName?: string | null };

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

const GUEST_SESSION_STORAGE_KEY = "cardpilot_guest_session";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

function generateGuestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `guest-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `guest-${Math.random().toString(36).slice(2, 10)}`;
}

function getStoredGuestSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(GUEST_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (parsed?.accessToken && parsed?.userId) {
      return { accessToken: parsed.accessToken, userId: parsed.userId, email: parsed.email ?? null, displayName: parsed.displayName ?? null };
    }
    window.localStorage.removeItem(GUEST_SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
  return null;
}

function persistGuestSession(session: AuthSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(GUEST_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage errors
  }
}

function clearGuestSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(GUEST_SESSION_STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
}

function createLocalGuestSession(displayName?: string): AuthSession {
  const guestId = generateGuestId();
  const session: AuthSession = { accessToken: guestId, userId: guestId, email: null, displayName: displayName || "Guest" };
  persistGuestSession(session);
  return session;
}

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

async function getSupabaseSession(): Promise<AuthSession | null> {
  if (!supabase) return null;
  const { data: existing } = await supabase.auth.getSession();
  if (existing.session?.access_token && existing.session.user?.id) {
    clearGuestSession();
    const meta = existing.session.user.user_metadata;
    const dn = (typeof meta?.display_name === "string" && meta.display_name) || (typeof meta?.name === "string" && meta.name) || null;
    return {
      accessToken: existing.session.access_token,
      userId: existing.session.user.id,
      email: existing.session.user.email,
      displayName: dn,
    };
  }
  return null;
}

function isAnonDisabledError(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  return msg.toLowerCase().includes("anonymous sign-ins are disabled");
}

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

export async function getExistingSession(): Promise<AuthSession | null> {
  // Always prefer a real Supabase session (UUID-based) over a local guest
  const sbSession = await getSupabaseSession();
  if (sbSession) return sbSession;

  const cached = getStoredGuestSession();
  if (!cached) return null;

  // If Supabase is available and the cached session is a local guest (non-UUID),
  // try to upgrade to an anonymous Supabase session for history persistence.
  if (supabase && !isUuid(cached.userId)) {
    try {
      const { data, error } = await supabase.auth.signInAnonymously();
      if (!error && data.session && data.user) {
        clearGuestSession();
        return {
          accessToken: data.session.access_token,
          userId: data.user.id,
          email: data.user.email,
          displayName: cached.displayName || "Guest",
        };
      }
    } catch {
      // Fall through to return the local guest session
    }
  }

  return cached;
}

export async function ensureGuestSession(displayName?: string): Promise<AuthSession | null> {
  // Always prefer a real Supabase session (UUID-based) over a local guest
  const supabaseSession = await getSupabaseSession();
  if (supabaseSession) return supabaseSession;

  const cached = getStoredGuestSession();
  // If cached guest is already a UUID (from a previous anon sign-in), return it
  if (cached && isUuid(cached.userId)) return cached;

  // Try Supabase anonymous sign-in (even if we have a local guest — upgrade it)
  if (supabase) {
    checkRateLimit();
    try {
      const { data, error } = await supabase.auth.signInAnonymously();
      if (error) throw error;
      if (!data.session || !data.user) throw new Error("Anonymous sign-in returned no session.");
      clearGuestSession();
      return {
        accessToken: data.session.access_token,
        userId: data.user.id,
        email: data.user.email,
        displayName: displayName || cached?.displayName || "Guest",
      };
    } catch (err) {
      if (!isAnonDisabledError(err)) {
        throw friendlyAuthError(err);
      }
      // Anonymous sign-ins disabled — fall through to local guest
    }
  }

  // Fallback: return existing local guest or create a new one
  if (cached) return cached;
  return createLocalGuestSession(displayName);
}

export async function signUpWithEmail(email: string, password: string, displayName?: string): Promise<AuthSession> {
  if (!supabase) throw new Error("Supabase not configured");

  const emailErr = validateEmail(email);
  if (emailErr) throw new Error(emailErr);
  const pwErr = validatePassword(password);
  if (pwErr) throw new Error(pwErr);

  checkRateLimit();

  try {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: displayName ? { data: { display_name: displayName } } : undefined,
    });
    if (error) throw error;
    if (!data.session || !data.user) throw new Error("Sign up succeeded but no session returned. Check your email for confirmation.");
    return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email, displayName: displayName || null };
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
    const meta = data.user.user_metadata;
    const dn = (typeof meta?.display_name === "string" && meta.display_name) || (typeof meta?.name === "string" && meta.name) || null;
    return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email, displayName: dn };
  } catch (err) {
    throw friendlyAuthError(err);
  }
}

export async function signInWithGoogle(): Promise<void> {
  if (!supabase) throw new Error("Supabase not configured");

  try {
    const redirectTo = typeof window !== "undefined" ? window.location.origin : undefined;
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: redirectTo ? { redirectTo } : undefined,
    });
    if (error) throw error;
  } catch (err) {
    throw friendlyAuthError(err);
  }
}

export async function signOut(): Promise<void> {
  if (supabase) {
    await supabase.auth.signOut();
  }
  clearGuestSession();
}
