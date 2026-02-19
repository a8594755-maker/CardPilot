import { createClient } from "@supabase/supabase-js";

export type AuthSession = {
  accessToken: string;
  userId: string;
  email?: string | null;
  displayName?: string | null;
  isGuest: boolean;
};

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const DEV_MODE = import.meta.env.DEV;

const GUEST_SESSION_STORAGE_KEY = "cardpilot_guest_session";
const GUEST_USER_ID_STORAGE_KEY = "cardpilot_guest_user_id";

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

export function getOrCreateGuestUserId(): string {
  const generated = generateGuestId();
  if (typeof window === "undefined") return generated;
  try {
    const raw = window.localStorage.getItem(GUEST_USER_ID_STORAGE_KEY);
    if (raw && raw.startsWith("guest-")) return raw;
    window.localStorage.setItem(GUEST_USER_ID_STORAGE_KEY, generated);
    return generated;
  } catch {
    return generated;
  }
}

export function normalizeClientUserId(userId: string, isGuest: boolean): string {
  const trimmed = userId.trim();
  if (!isGuest) return trimmed;
  return getOrCreateGuestUserId();
}

function getStoredGuestSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(GUEST_SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (parsed?.accessToken && parsed?.userId) {
      return {
        accessToken: parsed.accessToken,
        userId: parsed.userId,
        email: parsed.email ?? null,
        displayName: parsed.displayName ?? null,
        isGuest: parsed.isGuest ?? true,
      };
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
  const guestId = getOrCreateGuestUserId();
  const session: AuthSession = {
    accessToken: guestId,
    userId: guestId,
    email: null,
    displayName: displayName || "Guest",
    isGuest: true,
  };
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

let getSupabaseSessionInFlight: Promise<AuthSession | null> | null = null;
let invalidRefreshHandled = false;
let invalidRefreshSignOutInFlight: Promise<void> | null = null;

type AuthErrorDetails = {
  message: string;
  description: string | null;
  code: string | null;
  status: number | null;
};

function extractAuthErrorDetails(err: unknown): AuthErrorDetails {
  if (err && typeof err === "object") {
    const e = err as {
      message?: unknown;
      error_description?: unknown;
      code?: unknown;
      status?: unknown;
    };

    const message =
      typeof e.message === "string" && e.message.trim().length > 0
        ? e.message
        : String(err);
    const description = typeof e.error_description === "string" ? e.error_description : null;
    const code = typeof e.code === "string" ? e.code : null;
    const status = typeof e.status === "number" ? e.status : null;

    return { message, description, code, status };
  }

  const message = err instanceof Error ? err.message : String(err);
  return { message, description: null, code: null, status: null };
}

function isInvalidRefreshTokenError(err: unknown): boolean {
  const details = extractAuthErrorDetails(err);
  const text = `${details.message} ${details.description ?? ""}`.toLowerCase();
  return text.includes("invalid refresh token") || text.includes("refresh token not found");
}

async function handleInvalidRefreshToken(err: unknown): Promise<void> {
  clearGuestSession();
  if (!supabase) return;
  if (invalidRefreshHandled) return;
  if (invalidRefreshSignOutInFlight) {
    await invalidRefreshSignOutInFlight;
    return;
  }

  invalidRefreshSignOutInFlight = (async () => {
    invalidRefreshHandled = true;
    const details = extractAuthErrorDetails(err);
    if (DEV_MODE) {
      console.warn("[auth] Invalid refresh token detected. Clearing local auth session.", {
        status: details.status,
        code: details.code,
        message: details.message,
        error_description: details.description,
      });
    }
    try {
      await supabase.auth.signOut({ scope: "local" });
    } catch (signOutErr) {
      if (DEV_MODE) {
        console.warn("[auth] Local sign-out after invalid refresh token failed", signOutErr);
      }
    }
  })().finally(() => {
    invalidRefreshSignOutInFlight = null;
  });

  await invalidRefreshSignOutInFlight;
}

async function getSupabaseSession(): Promise<AuthSession | null> {
  if (!supabase) return null;
  if (getSupabaseSessionInFlight) return getSupabaseSessionInFlight;

  getSupabaseSessionInFlight = (async () => {
    const { data: existing, error } = await supabase.auth.getSession();
    if (error) {
      if (isInvalidRefreshTokenError(error)) {
        await handleInvalidRefreshToken(error);
        return null;
      }
      throw error;
    }

    if (existing.session?.access_token && existing.session.user?.id) {
      invalidRefreshHandled = false;
      clearGuestSession();
      const meta = existing.session.user.user_metadata;
      const dn = (typeof meta?.display_name === "string" && meta.display_name) || (typeof meta?.name === "string" && meta.name) || null;
      const isGuest = Boolean((existing.session.user as { is_anonymous?: boolean }).is_anonymous);
      return {
        accessToken: existing.session.access_token,
        userId: normalizeClientUserId(existing.session.user.id, isGuest),
        email: existing.session.user.email,
        displayName: dn,
        isGuest,
      };
    }
    return null;
  })().finally(() => {
    getSupabaseSessionInFlight = null;
  });

  return getSupabaseSessionInFlight;
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
  const details = extractAuthErrorDetails(err);
  const msg = details.message;
  const combined = `${details.message} ${details.description ?? ""}`.toLowerCase();
  if (combined.includes("rate limit") || msg.includes("429") || details.status === 429) {
    return new Error("Email rate limit exceeded. Please wait a few minutes before trying again.");
  }
  if (
    combined.includes("signup is disabled") ||
    combined.includes("signups not allowed") ||
    combined.includes("allow new users to sign up")
  ) {
    return new Error("Signups are currently disabled for this project. Ask an admin to enable 'Allow new users to sign up' in Supabase Authentication settings.");
  }
  if (combined.includes("user already registered") || combined.includes("already registered") || combined.includes("already exists")) {
    return new Error("This email is already registered. Try logging in instead.");
  }
  if (combined.includes("invalid email") || combined.includes("unable to validate email")) {
    return new Error("Please check your email format and try again.");
  }
  if (msg.includes("Invalid login credentials")) {
    return new Error("Incorrect email or password.");
  }
  if (details.description) {
    return new Error(`${msg} (${details.description})`);
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
          userId: normalizeClientUserId(data.user.id, true),
          email: data.user.email,
          displayName: cached.displayName || "Guest",
          isGuest: true,
        };
      }
    } catch {
      // Fall through to return the local guest session
    }
  }

  return { ...cached, isGuest: cached.isGuest ?? true };
}

export async function ensureGuestSession(displayName?: string): Promise<AuthSession | null> {
  // Always prefer a real Supabase session (UUID-based) over a local guest
  const supabaseSession = await getSupabaseSession();
  if (supabaseSession) return supabaseSession;

  const cached = getStoredGuestSession();
  // If cached guest is already a UUID (from a previous anon sign-in), return it
  if (cached && isUuid(cached.userId)) {
    return { ...cached, isGuest: cached.isGuest ?? true };
  }

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
        userId: normalizeClientUserId(data.user.id, true),
        email: data.user.email,
        displayName: displayName || cached?.displayName || "Guest",
        isGuest: true,
      };
    } catch (err) {
      if (!isAnonDisabledError(err)) {
        throw friendlyAuthError(err);
      }
      // Anonymous sign-ins disabled — fall through to local guest
    }
  }

  // Fallback: return existing local guest or create a new one
  if (cached) return { ...cached, isGuest: cached.isGuest ?? true };
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
    invalidRefreshHandled = false;
    return {
      accessToken: data.session.access_token,
      userId: data.user.id,
      email: data.user.email,
      displayName: displayName || null,
      isGuest: false,
    };
  } catch (err) {
    if (DEV_MODE) {
      const details = extractAuthErrorDetails(err);
      console.error("[auth] signUpWithEmail failed", {
        status: details.status,
        code: details.code,
        message: details.message,
        error_description: details.description,
        rawError: err,
      });
    }
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
    invalidRefreshHandled = false;
    const meta = data.user.user_metadata;
    const dn = (typeof meta?.display_name === "string" && meta.display_name) || (typeof meta?.name === "string" && meta.name) || null;
    return {
      accessToken: data.session.access_token,
      userId: data.user.id,
      email: data.user.email,
      displayName: dn,
      isGuest: false,
    };
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
  invalidRefreshHandled = false;
  clearGuestSession();
}
