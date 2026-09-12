/**
 * Authentication surface (PRD 0, section 5).
 *
 * PRD 0 establishes the *shape* of authentication and nothing more. The real
 * sign-in experience, provider configuration and onboarding arrive in PRD 1.
 *
 * The important rule here: no fake flows. Calling a sign-in method for a
 * provider that has not been configured throws `AuthProviderNotConfiguredError`
 * so the UI can state plainly that it is unavailable in this build. Nothing in
 * this file ever returns a session it did not genuinely obtain.
 */
import { useAppStore } from '../../store/appStore';
import type { AuthProviderId, AuthSession } from '../../types/auth';
import { createLogger } from '../../utils/logger';
import { clearSecureStorage } from '../storage/secureStorage';

const log = createLogger('auth');

export class AuthProviderNotConfiguredError extends Error {
  readonly provider: AuthProviderId;

  constructor(provider: AuthProviderId) {
    super(
      `Sign in with ${provider} is not configured yet. Authentication is implemented in PRD 1.`
    );
    this.name = 'AuthProviderNotConfiguredError';
    this.provider = provider;
  }
}

/**
 * Which providers this build can actually use.
 *
 * PRD 0 ships with none configured, so this is empty. PRD 1 will populate it
 * from the auth backend's configuration; the set is read at call time so the
 * rest of the app does not need to change when that happens.
 */
export function configuredProviders(): readonly AuthProviderId[] {
  return [];
}

export function isProviderConfigured(provider: AuthProviderId): boolean {
  return configuredProviders().includes(provider);
}

function startSignIn(provider: AuthProviderId): Promise<AuthSession> {
  if (!isProviderConfigured(provider)) {
    log.info('sign-in attempted for an unconfigured provider', { provider });
    return Promise.reject(new AuthProviderNotConfiguredError(provider));
  }
  // Unreachable in PRD 0: nothing is configured, so the guard above always
  // rejects. PRD 1 replaces this with the real provider handshake.
  return Promise.reject(new Error(`No sign-in implementation wired up for ${provider}.`));
}

export const AuthService = {
  signInWithApple: () => startSignIn('apple'),
  signInWithGoogle: () => startSignIn('google'),
  signInWithPhone: () => startSignIn('phone'),
  signInWithEmail: () => startSignIn('email'),

  /**
   * Clears local session state and every stored secret. Safe to call even
   * when signed out, which is the only state PRD 0 can be in.
   */
  async signOut(): Promise<void> {
    await clearSecureStorage();
    useAppStore.getState().setSession(null);
    log.info('signed out and cleared local secrets');
  },

  /** The current session, or null when signed out. Never a placeholder. */
  getCurrentSession(): AuthSession | null {
    return useAppStore.getState().session;
  },

  /**
   * Refreshes the active session. With no provider configured there is nothing
   * to refresh, so this resolves to null rather than inventing a session.
   */
  async refreshSession(): Promise<AuthSession | null> {
    const session = useAppStore.getState().session;
    if (!session) {
      return null;
    }
    throw new Error('Session refresh is implemented in PRD 1.');
  },
} as const;
