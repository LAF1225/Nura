/**
 * Authentication types (PRD 0 section 5; PRD 1 section 9).
 *
 * Access and refresh tokens are deliberately absent: they are held by the
 * Supabase client in secure storage and never copied into app state.
 */
export type AuthProviderId = 'apple' | 'google' | 'phone' | 'email';

/** The states authentication can be in (PRD 1, section 9). */
export type AuthStatus =
  /** Still restoring a stored session on launch. */
  'unknown' | 'unauthenticated' | 'authenticating' | 'authenticated' | 'error';

export interface AuthSession {
  userId: string;
  /** Null when the provider did not tell us, e.g. a restored session. */
  provider: AuthProviderId | null;
  email: string | null;
  phone: string | null;
}
