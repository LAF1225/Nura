/**
 * Authentication types (PRD 0, section 5).
 *
 * The full sign-in experience lands in PRD 1. PRD 0 only fixes the shape of a
 * session and the set of providers, so the rest of the app can be written
 * against a stable contract.
 */
export type AuthProviderId = 'apple' | 'google' | 'phone' | 'email';

export interface AuthSession {
  userId: string;
  provider: AuthProviderId;
  /** ISO timestamp. Access tokens themselves live in secure storage only. */
  expiresAt: string;
}
