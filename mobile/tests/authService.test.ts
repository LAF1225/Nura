/**
 * Authentication service behaviour (PRD 1, sections 9, 10 and 52).
 *
 * The test environment has no Supabase credentials, which is exactly the
 * "provider not configured" case the PRD cares about: every entry point must
 * reject with a clear error and none may ever resolve with a session.
 */
import { AuthError, toAuthError } from '../src/services/auth/authErrors';
import { AuthService, availableProviders } from '../src/services/auth/authService';

describe('when no auth provider is configured', () => {
  it('reports that it is not configured', () => {
    expect(AuthService.isConfigured()).toBe(false);
    expect(availableProviders()).toEqual([]);
  });

  it('has no session to return rather than inventing one', async () => {
    await expect(AuthService.getCurrentSession()).resolves.toBeNull();
    await expect(AuthService.refreshSession()).resolves.toBeNull();
  });

  it.each([
    ['signInWithEmail', () => AuthService.signInWithEmail('a@b.com', 'password123')],
    ['signUpWithEmail', () => AuthService.signUpWithEmail('a@b.com', 'password123')],
    ['sendPasswordReset', () => AuthService.sendPasswordReset('a@b.com')],
    ['sendPhoneOtp', () => AuthService.sendPhoneOtp('+447700900123')],
    ['verifyPhoneOtp', () => AuthService.verifyPhoneOtp('+447700900123', '123456')],
    ['signInWithGoogle', () => AuthService.signInWithGoogle()],
    ['signOut', () => AuthService.signOut()],
  ])('%s rejects instead of simulating success', async (_name, call) => {
    await expect(call()).rejects.toMatchObject({
      name: 'AuthError',
      kind: 'notConfigured',
    });
  });

  it('explains itself in words a user can read', () => {
    const error = new AuthError('notConfigured');
    expect(error.message).toMatch(/not available in this build/i);
  });
});

describe('provider error mapping', () => {
  it('never surfaces the provider’s own wording', () => {
    const raw = { code: 'invalid_credentials', message: 'Invalid login credentials' };

    const mapped = toAuthError(raw);

    expect(mapped.kind).toBe('invalidCredentials');
    expect(mapped.message).not.toContain('Invalid login credentials');
  });

  it('does not reveal whether an account exists', () => {
    const mapped = toAuthError({ code: 'invalid_credentials' });
    // Must not distinguish "no such user" from "wrong password".
    expect(mapped.message).not.toMatch(/no account|not found|unregistered/i);
  });

  it.each([
    ['email_exists', 'emailAlreadyRegistered'],
    ['weak_password', 'weakPassword'],
    ['otp_expired', 'expiredCode'],
    ['over_sms_send_rate_limit', 'rateLimited'],
    ['email_not_confirmed', 'emailNotConfirmed'],
    ['refresh_token_not_found', 'sessionExpired'],
  ])('maps %s to %s', (code, expected) => {
    expect(toAuthError({ code }).kind).toBe(expected);
  });

  it('falls back to the HTTP status when there is no code', () => {
    expect(toAuthError({ status: 429 }).kind).toBe('rateLimited');
    expect(toAuthError({ status: 401 }).kind).toBe('invalidCredentials');
  });

  it('treats an unrecognised failure as unknown rather than guessing', () => {
    const mapped = toAuthError(new Error('something odd happened'));
    expect(mapped.kind).toBe('unknown');
    expect(mapped.message).not.toContain('something odd happened');
  });

  it('passes an AuthError straight through', () => {
    const original = new AuthError('cancelled');
    expect(toAuthError(original)).toBe(original);
  });
});
