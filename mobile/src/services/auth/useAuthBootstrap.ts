/**
 * Connects Supabase's auth state to the app (PRD 1, sections 6 and 15).
 *
 * Called once from the root layout. It restores a stored session on launch,
 * keeps the store in step with sign-ins, sign-outs and token refreshes, and
 * tells the API client where to get the bearer token from.
 */
import type { Session } from '@supabase/supabase-js';
import { useEffect } from 'react';

import { setAuthTokenProvider } from '../api/client';
import { useAppStore } from '../../store/appStore';
import type { AuthProviderId, AuthSession } from '../../types/auth';
import { createLogger } from '../../utils/logger';
import { AuthService } from './authService';
import { startAuthAutoRefresh, supabase } from './supabaseClient';

const log = createLogger('auth');

const KNOWN_PROVIDERS: AuthProviderId[] = ['apple', 'google', 'phone', 'email'];

/** Maps a Supabase session onto the small shape the app keeps in state. */
export function toAuthSession(session: Session | null): AuthSession | null {
  if (!session?.user) {
    return null;
  }
  const raw = session.user.app_metadata?.provider;
  const provider = KNOWN_PROVIDERS.find((candidate) => candidate === raw) ?? null;

  return {
    userId: session.user.id,
    provider,
    email: session.user.email ?? null,
    phone: session.user.phone ?? null,
  };
}

export function useAuthBootstrap(): void {
  const setSession = useAppStore((state) => state.setSession);
  const setAuthStatus = useAppStore((state) => state.setAuthStatus);

  useEffect(() => {
    // The API client asks for a token per request. Reading it from the client
    // each time means a token refreshed in the background is picked up without
    // anything having to push it here.
    setAuthTokenProvider(async () => {
      const session = await AuthService.getCurrentSession();
      return session?.access_token ?? null;
    });

    if (!supabase) {
      // No provider configured: settled, and definitely signed out.
      setAuthStatus('unauthenticated');
      return;
    }

    let active = true;

    // Restore whatever was in secure storage (PRD 1, section 6).
    void AuthService.getCurrentSession()
      .then((session) => {
        if (!active) return;
        setSession(toAuthSession(session));
        setAuthStatus(session ? 'authenticated' : 'unauthenticated');
      })
      .catch((error) => {
        if (!active) return;
        log.warn('could not restore a stored session', { message: String(error) });
        setSession(null);
        setAuthStatus('unauthenticated');
      });

    const subscription = AuthService.onAuthStateChange((session) => {
      setSession(toAuthSession(session));
      setAuthStatus(session ? 'authenticated' : 'unauthenticated');
    });

    const stopAutoRefresh = startAuthAutoRefresh();

    return () => {
      active = false;
      subscription?.unsubscribe();
      stopAutoRefresh();
    };
  }, [setSession, setAuthStatus]);
}
