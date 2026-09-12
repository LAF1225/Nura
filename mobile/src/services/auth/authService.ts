/**
 * Authentication (PRD 1, sections 9-15).
 *
 * Every method here talks to a real provider. Nothing simulates a successful
 * sign-in: when a provider is not configured the call rejects with
 * `AuthError('notConfigured')` and the UI says so plainly (PRD 1, section 52).
 *
 * Sessions are stored by the Supabase client itself, in the device keychain --
 * see `secureSessionStorage`. This module never touches a token directly and
 * never logs one.
 */
import * as AppleAuthentication from 'expo-apple-authentication';
import { makeRedirectUri } from 'expo-auth-session';
import * as Linking from 'expo-linking';
import * as WebBrowser from 'expo-web-browser';
import { Platform } from 'react-native';
import type { Session, Subscription } from '@supabase/supabase-js';

import { config } from '../../constants/config';
import type { AuthProviderId } from '../../types/auth';
import { createLogger } from '../../utils/logger';
import { AuthError, toAuthError } from './authErrors';
import { supabase } from './supabaseClient';

const log = createLogger('auth');

// Lets the OAuth browser tab close itself cleanly when it redirects back.
WebBrowser.maybeCompleteAuthSession();

/** Result of a sign-in that may carry a display name from the provider. */
export interface SignInResult {
  session: Session;
  /**
   * Apple shares a name only on the very first sign-in (PRD 1, section 13),
   * so it is surfaced here for the profile step to prefill. Never treat its
   * absence as an error.
   */
  suggestedName?: string;
}

function requireClient() {
  if (!supabase) {
    throw new AuthError('notConfigured');
  }
  return supabase;
}

/**
 * Which providers this build can actually attempt.
 *
 * Apple is offered on iOS only. PRD 1 section 8 allows Apple on Android where
 * the provider supports it, but says it should not be awkwardly prioritised
 * there -- and it needs separate web-flow configuration, so it is left off
 * until that is set up.
 */
export function availableProviders(): readonly AuthProviderId[] {
  if (!config.isSupabaseConfigured) {
    return [];
  }
  const providers: AuthProviderId[] = ['email', 'phone'];
  if (config.googleClientId) {
    providers.push('google');
  }
  if (Platform.OS === 'ios') {
    providers.push('apple');
  }
  return providers;
}

export function isProviderConfigured(provider: AuthProviderId): boolean {
  return availableProviders().includes(provider);
}

async function signInWithOAuthProvider(
  provider: 'google' | 'apple'
): Promise<SignInResult> {
  const client = requireClient();
  const redirectTo = makeRedirectUri({ scheme: 'nura', path: 'auth/callback' });

  const { data, error } = await client.auth.signInWithOAuth({
    provider,
    options: { redirectTo, skipBrowserRedirect: true },
  });
  if (error) throw toAuthError(error);
  if (!data?.url) throw new AuthError('unknown');

  const result = await WebBrowser.openAuthSessionAsync(data.url, redirectTo);

  // Backing out of the sheet is a normal thing to do, not a failure to report
  // loudly (PRD 1, section 12).
  if (result.type !== 'success') {
    throw new AuthError('cancelled');
  }

  // Parsed with expo-linking rather than `new URL`, whose React Native
  // implementation is incomplete.
  const code = Linking.parse(result.url).queryParams?.code;
  if (typeof code !== 'string') {
    throw new AuthError('unknown');
  }

  const exchanged = await client.auth.exchangeCodeForSession(code);
  if (exchanged.error) throw toAuthError(exchanged.error);
  if (!exchanged.data.session) throw new AuthError('unknown');

  return { session: exchanged.data.session };
}

export const AuthService = {
  isConfigured: () => supabase !== null,
  availableProviders,
  isProviderConfigured,

  // --- email (PRD 1, section 10) ---

  async signUpWithEmail(email: string, password: string): Promise<Session | null> {
    const client = requireClient();
    const { data, error } = await client.auth.signUp({
      email: email.trim(),
      password,
    });
    if (error) throw toAuthError(error);
    // Null session means the project requires email confirmation: the account
    // exists but is not usable until the link is followed. The caller shows
    // that as a "check your inbox" state, never as a successful sign-in.
    return data.session;
  },

  async signInWithEmail(email: string, password: string): Promise<Session> {
    const client = requireClient();
    const { data, error } = await client.auth.signInWithPassword({
      email: email.trim(),
      password,
    });
    if (error) throw toAuthError(error);
    if (!data.session) throw new AuthError('unknown');
    return data.session;
  },

  async sendPasswordReset(email: string): Promise<void> {
    const client = requireClient();
    const { error } = await client.auth.resetPasswordForEmail(email.trim(), {
      redirectTo: makeRedirectUri({ scheme: 'nura', path: 'auth/reset' }),
    });
    if (error) throw toAuthError(error);
  },

  // --- phone (PRD 1, section 11) ---

  /** Sends a one-time code. Never called automatically -- always on a tap. */
  async sendPhoneOtp(phoneE164: string): Promise<void> {
    const client = requireClient();
    const { error } = await client.auth.signInWithOtp({ phone: phoneE164 });
    if (error) throw toAuthError(error);
  },

  async verifyPhoneOtp(phoneE164: string, code: string): Promise<Session> {
    const client = requireClient();
    const { data, error } = await client.auth.verifyOtp({
      phone: phoneE164,
      token: code,
      type: 'sms',
    });
    if (error) throw toAuthError(error);
    if (!data.session) throw new AuthError('invalidCode');
    return data.session;
  },

  // --- OAuth (PRD 1, sections 12 and 13) ---

  signInWithGoogle: (): Promise<SignInResult> => signInWithOAuthProvider('google'),

  async signInWithApple(): Promise<SignInResult> {
    const client = requireClient();

    // Native Sign in with Apple on iOS; the web flow everywhere else.
    if (Platform.OS !== 'ios' || !(await AppleAuthentication.isAvailableAsync())) {
      return signInWithOAuthProvider('apple');
    }

    let credential: AppleAuthentication.AppleAuthenticationCredential;
    try {
      credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
    } catch (error) {
      if ((error as { code?: string }).code === 'ERR_REQUEST_CANCELED') {
        throw new AuthError('cancelled');
      }
      throw toAuthError(error);
    }

    if (!credential.identityToken) {
      throw new AuthError('unknown');
    }

    const { data, error } = await client.auth.signInWithIdToken({
      provider: 'apple',
      token: credential.identityToken,
    });
    if (error) throw toAuthError(error);
    if (!data.session) throw new AuthError('unknown');

    // Apple sends the name only on first sign-in, so capture it now or never.
    // Apple may also return a private-relay address rather than a real inbox;
    // nothing here assumes the email is reachable (PRD 1, section 13).
    const parts = [credential.fullName?.givenName, credential.fullName?.familyName];
    const suggestedName = parts.filter(Boolean).join(' ').trim() || undefined;

    return { session: data.session, suggestedName };
  },

  // --- session (PRD 1, section 15) ---

  async signOut(): Promise<void> {
    const client = requireClient();
    const { error } = await client.auth.signOut();
    if (error) throw toAuthError(error);
    log.info('signed out');
  },

  async getCurrentSession(): Promise<Session | null> {
    if (!supabase) return null;
    const { data } = await supabase.auth.getSession();
    return data.session;
  },

  async refreshSession(): Promise<Session | null> {
    if (!supabase) return null;
    const { data, error } = await supabase.auth.refreshSession();
    if (error) throw toAuthError(error);
    return data.session;
  },

  /** Subscribes to sign-in/sign-out/token-refresh events. */
  onAuthStateChange(handler: (session: Session | null) => void): Subscription | null {
    if (!supabase) return null;
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      handler(session);
    });
    return data.subscription;
  },
} as const;

export { AuthError } from './authErrors';
