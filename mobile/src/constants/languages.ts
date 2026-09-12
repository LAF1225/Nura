/**
 * Languages Nura can be set to (PRD 1, section 21).
 *
 * Honest status: the interface itself is English only so far. Storing the
 * preference now means the choice survives until translations exist, and
 * nothing in the app hard-codes English in a way that would block adding them.
 * Codes are ISO 639-1, matching the `language` column on account settings.
 */

export interface Language {
  code: string;
  /** Shown in the picker, written in that language where practical. */
  name: string;
}

export const LANGUAGES: readonly Language[] = [
  { code: 'en', name: 'English' },
  { code: 'ur', name: 'اردو (Urdu)' },
  { code: 'ar', name: 'العربية (Arabic)' },
  { code: 'es', name: 'Español (Spanish)' },
  { code: 'fr', name: 'Français (French)' },
  { code: 'hi', name: 'हिन्दी (Hindi)' },
];

export const DEFAULT_LANGUAGE = 'en';
