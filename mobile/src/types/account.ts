/**
 * Account, profile and onboarding types (PRD 1, sections 31-34).
 *
 * The account is who signs in. The profile is who Nura is for. In assisted
 * setup those are different people, which is why they are separate types.
 */

export type SetupMode = 'self' | 'assisted';

export type ProfileRole = 'self' | 'setup_helper';

/** Onboarding state machine (PRD 1, section 31). */
export type OnboardingStatus =
  | 'not_started'
  | 'authenticated'
  | 'setup_mode_selected'
  | 'basic_profile_complete'
  | 'preferences_complete'
  | 'consent_complete'
  | 'ready_for_pairing'
  | 'onboarding_complete';

/** Privacy-conscious alternative to a date of birth (PRD 1, section 20). */
export type AgeRange =
  'under_18' | '18_29' | '30_44' | '45_59' | '60_74' | '75_plus' | 'prefer_not_to_say';

export type ThemeChoice = 'system' | 'light' | 'dark';

/** Preferences stored server-side against the account. */
export interface AccountSettings {
  theme: ThemeChoice;
  language: string;
  largerText: boolean;
  highContrast: boolean;
  reduceMotion: boolean;
  voiceFirstPreference: boolean;
  simplifiedInterface: boolean;
}

export interface Profile {
  id: string;
  preferredName: string;
  ageRange: AgeRange | null;
  countryRegion: string | null;
  pronouns: string | null;
  avatarUrl: string | null;
  role: ProfileRole | null;
}

export interface Account {
  id: string;
  email: string | null;
  phone: string | null;
  settings: AccountSettings;
  profiles: Profile[];
}

export interface OnboardingProgress {
  status: OnboardingStatus;
  setupMode: SetupMode | null;
  termsAccepted: boolean;
  privacyAcknowledged: boolean;
  /** For "Step 3 of 5" (PRD 1, section 29). */
  step: number;
  totalSteps: number;
  readyForPairing: boolean;
}
