/**
 * The Supabase client, or null when the project is not configured.
 *
 * Nothing else in the app constructs a client. Callers check
 * `isAuthConfigured()` (or handle the null) so an unconfigured build reports
 * that plainly instead of pretending to sign anyone in (PRD 1, sections 9
 * and 52).
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { AppState, type AppStateStatus } from 'react-native';

import { config } from '../../constants/config';
import { createLogger } from '../../utils/logger';
import { secureSessionStorage } from './secureSessionStorage';

const log = createLogger('supabase');

function createSupabaseClient(): SupabaseClient | null {
  if (!config.supabaseUrl || !config.supabaseAnonKey) {
    log.info('Supabase is not configured; authentication is unavailable');
    return null;
  }

  return createClient(config.supabaseUrl, config.supabaseAnonKey, {
    auth: {
      // Tokens go to the keychain, never to AsyncStorage (PRD 1, section 15).
      storage: secureSessionStorage,
      persistSession: true,
      autoRefreshToken: true,
      // There is no URL bar in a native app; the OAuth callback is handled
      // explicitly by the auth service instead.
      detectSessionInUrl: false,
      // PKCE is the flow recommended for public clients, which a mobile app is.
      flowType: 'pkce',
    },
  });
}

export const supabase = createSupabaseClient();

/** Whether this build can actually reach an authentication provider. */
export function isAuthConfigured(): boolean {
  return supabase !== null;
}

/**
 * Keeps token refresh tied to app lifecycle.
 *
 * Supabase's timer only makes sense while the app is in the foreground; left
 * running in the background it produces failed refreshes. Called once from the
 * root layout.
 */
export function startAuthAutoRefresh(): () => void {
  if (!supabase) {
    return () => {};
  }

  const handleChange = (state: AppStateStatus) => {
    if (state === 'active') {
      supabase.auth.startAutoRefresh();
    } else {
      supabase.auth.stopAutoRefresh();
    }
  };

  handleChange(AppState.currentState);
  const subscription = AppState.addEventListener('change', handleChange);

  return () => {
    subscription.remove();
    supabase.auth.stopAutoRefresh();
  };
}
