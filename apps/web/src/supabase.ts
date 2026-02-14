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
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) throw error;
  if (!data.session || !data.user) throw new Error("Sign up succeeded but no session returned. Check your email for confirmation.");
  return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email };
}

export async function signInWithEmail(email: string, password: string): Promise<AuthSession> {
  if (!supabase) throw new Error("Supabase not configured");
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw error;
  if (!data.session || !data.user) throw new Error("Sign in failed");
  return { accessToken: data.session.access_token, userId: data.user.id, email: data.user.email };
}

export async function signOut(): Promise<void> {
  if (!supabase) return;
  await supabase.auth.signOut();
}
