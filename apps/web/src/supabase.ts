import { createClient } from '@supabase/supabase-js';

export type AuthSession = {
  accessToken: string;
  userId: string;
  email?: string | null;
  displayName?: string | null;
  isGuest: boolean;
};

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const oauthRedirectOverride = import.meta.env.VITE_OAUTH_REDIRECT_URL;
const DEV_MODE = import.meta.env.DEV;
const AUTH_REQUEST_TIMEOUT_MS = 15_000;

const GUEST_SESSION_STORAGE_KEY = 'cardpilot_guest_session';
const GUEST_USER_ID_STORAGE_KEY = 'cardpilot_guest_user_id';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

function generateGuestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `guest-${crypto.randomUUID().slice(0, 8)}`;
  }
  return `guest-${Math.random().toString(36).slice(2, 10)}`;
}

export function getOrCreateGuestUserId(): string {
  const generated = generateGuestId();
  if (typeof window === 'undefined') return generated;
  try {
    const raw = window.localStorage.getItem(GUEST_USER_ID_STORAGE_KEY);
    if (raw && raw.startsWith('guest-')) return raw;
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
  if (typeof window === 'undefined') return null;
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
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(GUEST_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore storage errors
  }
}

function clearGuestSession(): void {
  if (typeof window === 'undefined') return;
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
    displayName: displayName || 'Guest',
    isGuest: true,
  };
  persistGuestSession(session);
  return session;
}

function deriveSupabaseStorageKey(url: string): string | null {
  try {
    const host = new URL(url).hostname;
    const projectRef = host.split('.')[0];
    if (!projectRef) return null;
    return `sb-${projectRef}-auth-token`;
  } catch {
    return null;
  }
}

function listSupabaseAuthStorageKeys(targetKey: string | null): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const localKeys = Object.keys(window.localStorage).filter(
      (key) => key.startsWith('sb-') && key.endsWith('-auth-token'),
    );
    if (!targetKey) return localKeys;
    if (localKeys.includes(targetKey)) return [targetKey];
    return [targetKey, ...localKeys];
  } catch {
    return targetKey ? [targetKey] : [];
  }
}

function clearSupabaseStorageBundle(storageKey: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(storageKey);
    window.localStorage.removeItem(`${storageKey}-user`);
    window.localStorage.removeItem(`${storageKey}-code-verifier`);
  } catch {
    // ignore storage errors
  }
}

function isValidPersistedSupabaseSession(raw: string): boolean {
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return false;

    const accessToken = typeof parsed.access_token === 'string' ? parsed.access_token.trim() : '';
    const refreshToken =
      typeof parsed.refresh_token === 'string' ? parsed.refresh_token.trim() : '';
    const expiresAt = parsed.expires_at;

    return (
      accessToken.length > 0 &&
      refreshToken.length > 0 &&
      typeof expiresAt === 'number' &&
      Number.isFinite(expiresAt)
    );
  } catch {
    return false;
  }
}

function scrubMalformedSupabaseSessions(targetKey: string | null): void {
  if (typeof window === 'undefined') return;
  const keys = listSupabaseAuthStorageKeys(targetKey);
  keys.forEach((key) => {
    let raw: string | null = null;
    try {
      raw = window.localStorage.getItem(key);
    } catch {
      return;
    }
    if (!raw) return;
    if (isValidPersistedSupabaseSession(raw)) return;
    clearSupabaseStorageBundle(key);
    if (DEV_MODE) console.warn(`[auth] Removed malformed persisted Supabase session: ${key}`);
  });
}

const supabaseStorageKey = supabaseUrl ? deriveSupabaseStorageKey(supabaseUrl) : null;
scrubMalformedSupabaseSessions(supabaseStorageKey);

export const supabase =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      })
    : null;

/** Track whether Supabase is reachable. When unreachable, skip network calls to avoid blocking the UI. */
let supabaseUnreachable = false;

/**
 * Fast connectivity probe — resolves to `true` when Supabase is unreachable.
 * All auth functions `await probePromise` before making network calls so the
 * UI never hangs on a dead backend.
 */
const probeSubscribers = new Set<(unreachable: boolean) => void>();

const probePromise: Promise<boolean> = (() => {
  if (!supabase || !supabaseUrl) return Promise.resolve(false);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  return fetch(`${supabaseUrl}/auth/v1/settings`, {
    signal: controller.signal,
    headers: { apikey: supabaseAnonKey! },
  })
    .then((res) => {
      clearTimeout(timer);
      if (!res.ok) {
        supabaseUnreachable = true;
        if (DEV_MODE) console.warn(`[auth] Supabase probe failed: HTTP ${res.status}`);
      }
      return supabaseUnreachable;
    })
    .catch(() => {
      clearTimeout(timer);
      supabaseUnreachable = true;
      if (DEV_MODE) console.warn('[auth] Supabase probe failed: unreachable');
      return true;
    })
    .finally(() => {
      probeSubscribers.forEach((cb) => cb(supabaseUnreachable));
      probeSubscribers.clear();
    });
})();

/**
 * Subscribe to the probe result. If the probe already completed, fires
 * the callback synchronously. Returns an unsubscribe function.
 * Usage in React: `useEffect(() => onSupabaseProbeResult(setUnreachable), [])`
 */
export function onSupabaseProbeResult(cb: (unreachable: boolean) => void): () => void {
  // If probePromise is already settled, fire immediately
  probePromise.then((result) => cb(result));
  // Also subscribe in case it hasn't settled yet (Promise.then is async)
  probeSubscribers.add(cb);
  return () => {
    probeSubscribers.delete(cb);
  };
}

let getSupabaseSessionInFlight: Promise<AuthSession | null> | null = null;
let invalidRefreshHandled = false;
let invalidRefreshSignOutInFlight: Promise<void> | null = null;

type AuthErrorDetails = {
  message: string;
  description: string | null;
  code: string | null;
  status: number | null;
};

async function withAuthTimeout<T>(promise: Promise<T>, actionLabel: string): Promise<T> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  const timeoutPromise = new Promise<T>((_, reject) => {
    timeoutId = setTimeout(() => {
      reject(
        new Error(`${actionLabel} timed out after ${Math.round(AUTH_REQUEST_TIMEOUT_MS / 1000)}s.`),
      );
    }, AUTH_REQUEST_TIMEOUT_MS);
  });

  try {
    return await Promise.race([promise, timeoutPromise]);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

function extractAuthErrorDetails(err: unknown): AuthErrorDetails {
  if (err && typeof err === 'object') {
    const e = err as {
      message?: unknown;
      error_description?: unknown;
      code?: unknown;
      status?: unknown;
    };

    const message =
      typeof e.message === 'string' && e.message.trim().length > 0 ? e.message : String(err);
    const description = typeof e.error_description === 'string' ? e.error_description : null;
    const code = typeof e.code === 'string' ? e.code : null;
    const status = typeof e.status === 'number' ? e.status : null;

    return { message, description, code, status };
  }

  const message = err instanceof Error ? err.message : String(err);
  return { message, description: null, code: null, status: null };
}

function shouldRetrySignUpWithoutMetadata(details: AuthErrorDetails): boolean {
  if (details.status !== 422) return false;
  const code = (details.code ?? '').toLowerCase();
  const combined = `${details.message} ${details.description ?? ''}`.toLowerCase();

  if (code.includes('validation')) return true;
  return (
    combined.includes('metadata') ||
    combined.includes('user_metadata') ||
    combined.includes('additional properties') ||
    combined.includes('schema validation') ||
    combined.includes('invalid request payload')
  );
}

function isInvalidRefreshTokenError(err: unknown): boolean {
  const details = extractAuthErrorDetails(err);
  const code = (details.code ?? '').toLowerCase();
  if (code === 'refresh_token_not_found' || code === 'refresh_token_already_used') return true;
  const text = `${details.message} ${details.description ?? ''}`.toLowerCase();
  return text.includes('invalid refresh token') || text.includes('refresh token not found');
}

function clearSupabaseLocalStorage() {
  if (typeof window === 'undefined') return;
  listSupabaseAuthStorageKeys(supabaseStorageKey).forEach((key) => clearSupabaseStorageBundle(key));
}

async function handleInvalidRefreshToken(err: unknown): Promise<void> {
  clearGuestSession();
  clearSupabaseLocalStorage();

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
      console.warn('[auth] Invalid refresh token detected. Clearing local auth session.', {
        status: details.status,
        code: details.code,
        message: details.message,
        error_description: details.description,
      });
    }
    try {
      await supabase.auth.signOut({ scope: 'local' });
    } catch (signOutErr) {
      if (DEV_MODE) {
        console.warn('[auth] Local sign-out after invalid refresh token failed', signOutErr);
      }
    }
  })().finally(() => {
    invalidRefreshSignOutInFlight = null;
  });

  await invalidRefreshSignOutInFlight;
}

/** Expose unreachable state so AuthScreen can show a notice. */
export function isSupabaseUnreachable(): boolean {
  return supabaseUnreachable;
}

async function getSupabaseSession(): Promise<AuthSession | null> {
  if (!supabase) return null;
  if (supabaseUnreachable) return null;
  if (getSupabaseSessionInFlight) return getSupabaseSessionInFlight;

  getSupabaseSessionInFlight = (async () => {
    const { data: existing, error } = await withAuthTimeout(
      supabase.auth.getSession(),
      'Session check',
    );
    if (error) {
      if (isInvalidRefreshTokenError(error)) {
        await handleInvalidRefreshToken(error);
        return null;
      }
      // Mark Supabase as unreachable on network/timeout errors so subsequent calls skip immediately
      const msg = (error instanceof Error ? error.message : String(error)).toLowerCase();
      if (msg.includes('timed out') || msg.includes('failed to fetch') || msg.includes('network')) {
        supabaseUnreachable = true;
        if (DEV_MODE) console.warn('[auth] Supabase unreachable, falling back to local guest mode');
        return null;
      }
      throw error;
    }

    if (existing.session?.access_token && existing.session.user?.id) {
      invalidRefreshHandled = false;
      supabaseUnreachable = false;
      clearGuestSession();
      const meta = existing.session.user.user_metadata;
      const dn =
        (typeof meta?.display_name === 'string' && meta.display_name) ||
        (typeof meta?.name === 'string' && meta.name) ||
        null;
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
  return msg.toLowerCase().includes('anonymous sign-ins are disabled');
}

/* ── Client-side rate limiter ── */
const authAttempts: { timestamps: number[]; lockedUntil: number } = {
  timestamps: [],
  lockedUntil: 0,
};

const RATE_LIMIT_WINDOW_MS = 60_000; // 1 minute window
const MAX_ATTEMPTS_PER_WINDOW = 5; // max 5 attempts per window
const LOCKOUT_DURATION_MS = 60_000; // 1 minute lockout after exceeding

function checkRateLimit(): void {
  const now = Date.now();
  if (now < authAttempts.lockedUntil) {
    const secsLeft = Math.ceil((authAttempts.lockedUntil - now) / 1000);
    throw new Error(`Too many attempts. Please wait ${secsLeft}s before trying again.`);
  }
  // Prune old timestamps
  authAttempts.timestamps = authAttempts.timestamps.filter((t) => now - t < RATE_LIMIT_WINDOW_MS);
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
  if (!email.trim()) return 'Email is required.';
  if (!EMAIL_RE.test(email)) return 'Please enter a valid email address.';
  return null;
}

export function validatePassword(password: string): string | null {
  if (!password) return 'Password is required.';
  if (password.length < 6) return 'Password must be at least 6 characters.';
  if (password.length > 72) return 'Password must be 72 characters or fewer.';
  return null;
}

/* ── Friendly error mapping ── */
function friendlyAuthError(err: unknown): Error {
  const details = extractAuthErrorDetails(err);
  const msg = details.message;
  const combined = `${details.message} ${details.description ?? ''}`.toLowerCase();
  if (
    combined.includes('timed out') ||
    combined.includes('timeout') ||
    combined.includes('failed to fetch') ||
    combined.includes('network request failed')
  ) {
    return new Error('Unable to reach Supabase auth service. Check your network and try again.');
  }
  if (combined.includes('rate limit') || msg.includes('429') || details.status === 429) {
    return new Error('Email rate limit exceeded. Please wait a few minutes before trying again.');
  }
  if (
    combined.includes('signup is disabled') ||
    combined.includes('signups not allowed') ||
    combined.includes('allow new users to sign up')
  ) {
    return new Error(
      "Signups are currently disabled for this project. Ask an admin to enable 'Allow new users to sign up' in Supabase Authentication settings.",
    );
  }
  if (
    combined.includes('user already registered') ||
    combined.includes('already registered') ||
    combined.includes('already exists')
  ) {
    return new Error('This email is already registered. Try logging in instead.');
  }
  if (combined.includes('invalid email') || combined.includes('unable to validate email')) {
    return new Error('Please check your email format and try again.');
  }
  if (msg.includes('Invalid login credentials')) {
    return new Error('Incorrect email or password.');
  }
  if (details.status === 422) {
    if (combined.includes('database error saving new user')) {
      return new Error(
        'Signup failed while creating the user record. Check Supabase auth triggers/functions in your project.',
      );
    }
    if (combined.includes('captcha')) {
      return new Error(
        'Signup captcha verification failed. Disable captcha for local dev or provide a valid captcha token.',
      );
    }
    return new Error(
      'Signup request was rejected by Supabase (422). Check Email auth settings and any auth-user database triggers.',
    );
  }
  if (details.description) {
    return new Error(`${msg} (${details.description})`);
  }
  return err instanceof Error ? err : new Error(msg);
}

export async function getExistingSession(): Promise<AuthSession | null> {
  // Wait for the connectivity probe so we don't hang on a dead backend.
  await probePromise;

  // Always prefer a real Supabase session (UUID-based) over a local guest
  const sbSession = await getSupabaseSession();
  if (sbSession) return sbSession;

  const cached = getStoredGuestSession();
  if (!cached) return null;

  // If Supabase is available and the cached session is a local guest (non-UUID),
  // try to upgrade to an anonymous Supabase session for history persistence.
  if (supabase && !supabaseUnreachable && !isUuid(cached.userId)) {
    try {
      const { data, error } = await withAuthTimeout(
        supabase.auth.signInAnonymously(),
        'Guest sign-in',
      );
      if (!error && data.session && data.user) {
        clearGuestSession();
        return {
          accessToken: data.session.access_token,
          userId: normalizeClientUserId(data.user.id, true),
          email: data.user.email,
          displayName: cached.displayName || 'Guest',
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
  // Wait for the connectivity probe so we skip Supabase instantly when it's down.
  await probePromise;

  // Always prefer a real Supabase session (UUID-based) over a local guest
  const supabaseSession = await getSupabaseSession();
  if (supabaseSession) return supabaseSession;

  const cached = getStoredGuestSession();
  // If cached guest is already a UUID (from a previous anon sign-in), return it
  if (cached && isUuid(cached.userId)) {
    return { ...cached, isGuest: cached.isGuest ?? true };
  }

  // Try Supabase anonymous sign-in (even if we have a local guest — upgrade it)
  if (supabase && !supabaseUnreachable) {
    checkRateLimit();
    try {
      const { data, error } = await withAuthTimeout(
        supabase.auth.signInAnonymously(),
        'Guest sign-in',
      );
      if (error) throw error;
      if (!data.session || !data.user) throw new Error('Anonymous sign-in returned no session.');
      clearGuestSession();
      return {
        accessToken: data.session.access_token,
        userId: normalizeClientUserId(data.user.id, true),
        email: data.user.email,
        displayName: displayName || cached?.displayName || 'Guest',
        isGuest: true,
      };
    } catch (err) {
      if (!isAnonDisabledError(err)) {
        // On network/timeout errors, fall through to local guest instead of blocking the user
        const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
        if (
          msg.includes('timed out') ||
          msg.includes('failed to fetch') ||
          msg.includes('network')
        ) {
          supabaseUnreachable = true;
          if (DEV_MODE)
            console.warn('[auth] Supabase unreachable during guest sign-in, using local guest');
        } else {
          throw friendlyAuthError(err);
        }
      }
      // Anonymous sign-ins disabled or unreachable — fall through to local guest
    }
  }

  // Fallback: return existing local guest or create a new one
  if (cached) return { ...cached, isGuest: cached.isGuest ?? true };
  return createLocalGuestSession(displayName);
}

export async function signUpWithEmail(
  email: string,
  password: string,
  displayName?: string,
): Promise<AuthSession> {
  if (!supabase) throw new Error('Supabase not configured');

  const normalizedEmail = email.trim().toLowerCase();
  const normalizedDisplayName = displayName?.trim();

  const emailErr = validateEmail(normalizedEmail);
  if (emailErr) throw new Error(emailErr);
  const pwErr = validatePassword(password);
  if (pwErr) throw new Error(pwErr);

  checkRateLimit();

  try {
    const signUpPayload = {
      email: normalizedEmail,
      password,
      options: normalizedDisplayName
        ? { data: { display_name: normalizedDisplayName } }
        : undefined,
    };

    let { data, error } = await withAuthTimeout(supabase.auth.signUp(signUpPayload), 'Sign up');

    // Some Supabase projects reject metadata at signup (422). Retry once without metadata.
    if (error && normalizedDisplayName) {
      const details = extractAuthErrorDetails(error);
      if (shouldRetrySignUpWithoutMetadata(details)) {
        ({ data, error } = await withAuthTimeout(
          supabase.auth.signUp({
            email: normalizedEmail,
            password,
          }),
          'Sign up',
        ));
      }
    }

    if (error) throw error;
    if (!data.session || !data.user)
      throw new Error(
        'Sign up succeeded but no session returned. Check your email for confirmation.',
      );
    invalidRefreshHandled = false;
    return {
      accessToken: data.session.access_token,
      userId: data.user.id,
      email: data.user.email,
      displayName: normalizedDisplayName || null,
      isGuest: false,
    };
  } catch (err) {
    if (DEV_MODE) {
      const details = extractAuthErrorDetails(err);
      console.error('[auth] signUpWithEmail failed', {
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
  if (!supabase) throw new Error('Supabase not configured');
  if (supabaseUnreachable)
    throw new Error(
      'Supabase is currently unreachable. Try "Continue as Guest" or try again later.',
    );

  const emailErr = validateEmail(email);
  if (emailErr) throw new Error(emailErr);
  const pwErr = validatePassword(password);
  if (pwErr) throw new Error(pwErr);

  checkRateLimit();

  try {
    const { data, error } = await withAuthTimeout(
      supabase.auth.signInWithPassword({ email, password }),
      'Sign in',
    );
    if (error) throw error;
    if (!data.session || !data.user) throw new Error('Sign in failed');
    invalidRefreshHandled = false;
    supabaseUnreachable = false;
    const meta = data.user.user_metadata;
    const dn =
      (typeof meta?.display_name === 'string' && meta.display_name) ||
      (typeof meta?.name === 'string' && meta.name) ||
      null;
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
  if (!supabase) throw new Error('Supabase not configured');

  try {
    const fromEnv =
      typeof oauthRedirectOverride === 'string' && oauthRedirectOverride.trim().length > 0
        ? oauthRedirectOverride.trim()
        : undefined;
    const redirectTo =
      fromEnv || (typeof window !== 'undefined' ? window.location.origin : undefined);
    const { data, error } = await withAuthTimeout(
      supabase.auth.signInWithOAuth({
        provider: 'google',
        options: redirectTo
          ? { redirectTo, skipBrowserRedirect: true }
          : { skipBrowserRedirect: true },
      }),
      'Google sign-in',
    );
    if (error) throw error;
    const redirectUrl = data?.url;
    if (!redirectUrl) {
      throw new Error(
        'Google sign-in did not return a redirect URL. Check Supabase Google OAuth settings.',
      );
    }
    if (typeof window === 'undefined') {
      throw new Error('Google sign-in redirect is only available in the browser.');
    }
    window.location.assign(redirectUrl);
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

/** Reset the invalid-refresh guard. Call after any successful auth state transition. */
export function resetInvalidRefreshGuard(): void {
  invalidRefreshHandled = false;
}

if (supabase) {
  supabase.auth.onAuthStateChange((event, session) => {
    if (event === 'SIGNED_OUT' && !session) {
      clearGuestSession();
      clearSupabaseLocalStorage();
    }
  });
}
