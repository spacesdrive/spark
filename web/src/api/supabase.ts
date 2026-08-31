/**
 * Google sign-in through Supabase.
 *
 * The Supabase client only exists to run the OAuth flow and hand back an
 * access token. That token is posted to the API once, which verifies it and
 * replies with an HttpOnly session cookie. The dashboard authenticates with
 * that cookie afterwards, so no long-lived token stays in browser storage
 * where a script could read it.
 *
 * The Supabase session is cleared as soon as it has been exchanged.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

let client: SupabaseClient | null = null;

export function initSupabase(url: string, anonKey: string): SupabaseClient | null {
  if (!url || !anonKey) return null;
  if (!client) {
    client = createClient(url, anonKey, {
      auth: {
        // The flow finishes on our own callback route, so the library only
        // needs to complete the exchange, not keep a session around.
        detectSessionInUrl: true,
        persistSession: true,
        autoRefreshToken: false,
        flowType: "pkce",
      },
    });
  }
  return client;
}

export function getSupabase(): SupabaseClient | null {
  return client;
}

/** Start Google sign-in. The browser leaves the page. */
export async function signInWithGoogle(redirectTo: string): Promise<void> {
  const supabase = getSupabase();
  if (!supabase) {
    throw new Error(
      "Sign-in is not configured on this server. See the deployment guide "
        + "for the Supabase and Google settings that are needed."
    );
  }
  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo },
  });
  if (error) throw new Error(error.message);
}

/** The access token from a just-completed OAuth redirect, if there is one. */
export async function takeAccessToken(): Promise<string | null> {
  const supabase = getSupabase();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** Drop the Supabase session once the API has issued its own cookie. */
export async function clearSupabaseSession(): Promise<void> {
  const supabase = getSupabase();
  if (supabase) await supabase.auth.signOut();
}
