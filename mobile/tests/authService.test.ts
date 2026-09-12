/**
 * Authentication surface (PRD 0, section 5).
 *
 * PRD 0 must not contain a fake sign-in flow. These tests pin that down: with
 * no provider configured, every sign-in method *rejects*, and nothing ever
 * hands back a session it did not genuinely obtain.
 *
 * No screen imports this module yet, so without these tests it would only be
 * checked by the type checker. PRD 1 replaces the bodies; these assertions
 * should then be updated deliberately, not quietly deleted.
 */
import {
  AuthProviderNotConfiguredError,
  AuthService,
  configuredProviders,
  isProviderConfigured,
} from '../src/services/auth/authService';
import { useAppStore } from '../src/store/appStore';
import type { AuthProviderId } from '../src/types/auth';

const PROVIDERS: AuthProviderId[] = ['apple', 'google', 'phone', 'email'];

describe('provider configuration', () => {
  it('reports no configured providers in PRD 0', () => {
    expect(configuredProviders()).toEqual([]);
    for (const provider of PROVIDERS) {
      expect(isProviderConfigured(provider)).toBe(false);
    }
  });
});

describe('sign-in methods', () => {
  const methods: [AuthProviderId, () => Promise<unknown>][] = [
    ['apple', AuthService.signInWithApple],
    ['google', AuthService.signInWithGoogle],
    ['phone', AuthService.signInWithPhone],
    ['email', AuthService.signInWithEmail],
  ];

  it.each(methods)(
    'rejects %s rather than faking a session',
    async (provider, method) => {
      await expect(method()).rejects.toBeInstanceOf(AuthProviderNotConfiguredError);
      // The error names the provider and says why, so the UI can be explicit
      // about the development state instead of showing a generic failure.
      await expect(method()).rejects.toThrow(new RegExp(provider));
      await expect(method()).rejects.toThrow(/not configured yet/);

      // Critically: no session was created as a side effect.
      expect(useAppStore.getState().session).toBeNull();
      expect(AuthService.getCurrentSession()).toBeNull();
    }
  );
});

describe('session handling', () => {
  afterEach(() => {
    useAppStore.setState({ session: null });
  });

  it('reports no current session when signed out', () => {
    useAppStore.setState({ session: null });
    expect(AuthService.getCurrentSession()).toBeNull();
  });

  it('returns null from refreshSession instead of inventing one', async () => {
    useAppStore.setState({ session: null });
    await expect(AuthService.refreshSession()).resolves.toBeNull();
  });

  it('clears local session state on sign-out', async () => {
    useAppStore.setState({
      session: { userId: 'u1', provider: 'email', expiresAt: '2030-01-01T00:00:00Z' },
    });

    await AuthService.signOut();

    expect(useAppStore.getState().session).toBeNull();
  });
});
