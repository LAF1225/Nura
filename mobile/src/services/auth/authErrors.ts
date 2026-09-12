/**
 * Turns provider failures into something safe to show a person
 * (PRD 1, sections 10, 38 and 49).
 *
 * Supabase error messages are written for developers and sometimes leak
 * detail about which accounts exist. Screens render `AuthError.message`, which
 * is always one of the sentences below -- never the provider's own text.
 */
import type { AuthError as SupabaseAuthError } from '@supabase/supabase-js';

export type AuthErrorKind =
  /** No provider configured in this build. */
  | 'notConfigured'
  /** Wrong email/password, or no such account. */
  | 'invalidCredentials'
  | 'emailAlreadyRegistered'
  | 'emailNotConfirmed'
  | 'weakPassword'
  | 'invalidEmail'
  | 'invalidPhone'
  | 'invalidCode'
  | 'expiredCode'
  /** Too many attempts; the provider is asking us to slow down. */
  | 'rateLimited'
  /** The person backed out of an OAuth sheet. Not really an error. */
  | 'cancelled'
  | 'network'
  | 'sessionExpired'
  | 'unknown';

const MESSAGES: Record<AuthErrorKind, string> = {
  notConfigured:
    'Sign-in is not available in this build yet. See the README for provider setup.',
  // Deliberately does not say which half was wrong -- that would let someone
  // probe for registered addresses.
  invalidCredentials: 'That email and password combination did not work.',
  emailAlreadyRegistered: 'There is already an account with this email. Try signing in.',
  emailNotConfirmed: 'Check your inbox and confirm your email address first.',
  weakPassword: 'Please choose a longer password, at least 8 characters.',
  invalidEmail: 'That does not look like a valid email address.',
  invalidPhone: 'That does not look like a valid phone number.',
  invalidCode: 'That code was not correct. Please check and try again.',
  expiredCode: 'That code has expired. Request a new one.',
  rateLimited: 'Too many attempts. Please wait a moment before trying again.',
  cancelled: 'Sign-in was cancelled.',
  network: 'We could not reach the sign-in service. Check your connection.',
  sessionExpired: 'Your session has expired. Please sign in again.',
  unknown: 'Something went wrong signing in. Please try again.',
};

export class AuthError extends Error {
  readonly kind: AuthErrorKind;

  constructor(kind: AuthErrorKind, cause?: unknown) {
    super(MESSAGES[kind], { cause });
    this.name = 'AuthError';
    this.kind = kind;
  }
}

export function isAuthError(error: unknown): error is AuthError {
  return error instanceof AuthError;
}

/** Supabase's stable `code` values, which are preferred over message text. */
const CODE_MAP: Record<string, AuthErrorKind> = {
  invalid_credentials: 'invalidCredentials',
  email_address_invalid: 'invalidEmail',
  email_exists: 'emailAlreadyRegistered',
  user_already_exists: 'emailAlreadyRegistered',
  email_not_confirmed: 'emailNotConfirmed',
  weak_password: 'weakPassword',
  otp_expired: 'expiredCode',
  otp_disabled: 'notConfigured',
  over_request_rate_limit: 'rateLimited',
  over_email_send_rate_limit: 'rateLimited',
  over_sms_send_rate_limit: 'rateLimited',
  validation_failed: 'invalidCode',
  session_expired: 'sessionExpired',
  session_not_found: 'sessionExpired',
  refresh_token_not_found: 'sessionExpired',
  phone_exists: 'invalidPhone',
};

/**
 * Classifies a Supabase error.
 *
 * Falls back to the HTTP status and then to message matching, because not
 * every failure carries a `code` yet.
 */
export function toAuthError(error: SupabaseAuthError | Error | unknown): AuthError {
  if (isAuthError(error)) {
    return error;
  }

  const candidate = error as Partial<SupabaseAuthError> & { message?: string };
  const code = candidate?.code;
  if (typeof code === 'string' && code in CODE_MAP) {
    return new AuthError(CODE_MAP[code]!, error);
  }

  const status = candidate?.status;
  if (status === 429) {
    return new AuthError('rateLimited', error);
  }
  if (status === 401 || status === 403) {
    return new AuthError('invalidCredentials', error);
  }

  const message = (candidate?.message ?? '').toLowerCase();
  if (message.includes('network') || message.includes('fetch')) {
    return new AuthError('network', error);
  }
  if (message.includes('expired')) {
    return new AuthError('expiredCode', error);
  }
  if (message.includes('invalid login') || message.includes('invalid credentials')) {
    return new AuthError('invalidCredentials', error);
  }

  return new AuthError('unknown', error);
}
