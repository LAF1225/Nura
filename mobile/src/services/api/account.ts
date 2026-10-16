/**
 * Account, onboarding and profile endpoints (PRD 1, section 35).
 *
 * The backend speaks snake_case; the app speaks camelCase. As with the system
 * endpoints, the mapping happens here so no screen ever sees wire format.
 */
import type {
  Account,
  AccountSettings,
  AgeRange,
  OnboardingProgress,
  OnboardingStatus,
  Profile,
  ProfileRole,
  SetupMode,
  ThemeChoice,
} from '../../types/account';
import { apiRequest } from './client';
import { ApiError } from './errors';

function asRecord(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function str(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function bool(value: unknown): boolean {
  return value === true;
}

function parseSettings(raw: unknown, endpoint: string): AccountSettings {
  const body = asRecord(raw, endpoint);
  return {
    theme: (str(body.theme) ?? 'system') as ThemeChoice,
    language: str(body.language) ?? 'en',
    largerText: bool(body.larger_text),
    highContrast: bool(body.high_contrast),
    reduceMotion: bool(body.reduce_motion),
    voiceFirstPreference: bool(body.voice_first_preference),
    simplifiedInterface: bool(body.simplified_interface),
    notifyCaregiverMessages: bool(body.notify_caregiver_messages),
    notifySuggestionRequests: bool(body.notify_suggestion_requests),
    notifyAppointmentSuggestions: bool(body.notify_appointment_suggestions),
    notifyRoutineSuggestions: bool(body.notify_routine_suggestions),
    safetyBedtime:
      typeof body.safety_bedtime === 'string' && body.safety_bedtime.length > 0
        ? body.safety_bedtime
        : null,
  };
}

export function parseProfile(raw: unknown): Profile {
  const body = asRecord(raw, '/api/v1/profiles');
  const id = str(body.id);
  const preferredName = str(body.preferred_name);
  if (!id || !preferredName) {
    throw new ApiError('server', 'Profile response was missing required fields.');
  }
  return {
    id,
    preferredName,
    ageRange: str(body.age_range) as AgeRange | null,
    countryRegion: str(body.country_region),
    pronouns: str(body.pronouns),
    avatarUrl: str(body.avatar_url),
    role: str(body.role) as ProfileRole | null,
  };
}

export function parseAccount(raw: unknown): Account {
  const body = asRecord(raw, '/api/v1/me');
  const id = str(body.id);
  if (!id) {
    throw new ApiError('server', 'Account response was missing an id.');
  }
  const profiles = Array.isArray(body.profiles) ? body.profiles : [];
  return {
    id,
    email: str(body.email),
    phone: str(body.phone),
    settings: parseSettings(body.settings, '/api/v1/me'),
    profiles: profiles.map(parseProfile),
  };
}

export function parseOnboarding(raw: unknown): OnboardingProgress {
  const body = asRecord(raw, '/api/v1/onboarding');
  const status = str(body.status);
  if (!status) {
    throw new ApiError('server', 'Onboarding response was missing a status.');
  }
  return {
    status: status as OnboardingStatus,
    setupMode: str(body.setup_mode) as SetupMode | null,
    termsAccepted: bool(body.terms_accepted),
    privacyAcknowledged: bool(body.privacy_acknowledged),
    step: typeof body.step === 'number' ? body.step : 0,
    totalSteps: typeof body.total_steps === 'number' ? body.total_steps : 5,
    readyForPairing: bool(body.ready_for_pairing),
  };
}

// --- requests -------------------------------------------------------------

export async function fetchAccount(signal?: AbortSignal): Promise<Account> {
  return parseAccount(await apiRequest<unknown>('/api/v1/me', { signal }));
}

/** Partial update of account preferences. Omitted fields are left alone. */
export interface SettingsPatch {
  theme?: ThemeChoice;
  language?: string;
  largerText?: boolean;
  highContrast?: boolean;
  reduceMotion?: boolean;
  voiceFirstPreference?: boolean;
  simplifiedInterface?: boolean;
  notifyCaregiverMessages?: boolean;
  notifySuggestionRequests?: boolean;
  notifyAppointmentSuggestions?: boolean;
  notifyRoutineSuggestions?: boolean;
  safetyBedtime?: string;
}

export async function updateSettings(patch: SettingsPatch): Promise<Account> {
  const body: Record<string, unknown> = {};
  if (patch.theme !== undefined) body.theme = patch.theme;
  if (patch.language !== undefined) body.language = patch.language;
  if (patch.largerText !== undefined) body.larger_text = patch.largerText;
  if (patch.highContrast !== undefined) body.high_contrast = patch.highContrast;
  if (patch.reduceMotion !== undefined) body.reduce_motion = patch.reduceMotion;
  if (patch.voiceFirstPreference !== undefined) {
    body.voice_first_preference = patch.voiceFirstPreference;
  }
  if (patch.notifyCaregiverMessages !== undefined) {
    body.notify_caregiver_messages = patch.notifyCaregiverMessages;
  }
  if (patch.notifySuggestionRequests !== undefined) {
    body.notify_suggestion_requests = patch.notifySuggestionRequests;
  }
  if (patch.notifyAppointmentSuggestions !== undefined) {
    body.notify_appointment_suggestions = patch.notifyAppointmentSuggestions;
  }
  if (patch.notifyRoutineSuggestions !== undefined) {
    body.notify_routine_suggestions = patch.notifyRoutineSuggestions;
  }
  if (patch.safetyBedtime !== undefined) body.safety_bedtime = patch.safetyBedtime;
  if (patch.simplifiedInterface !== undefined) {
    body.simplified_interface = patch.simplifiedInterface;
  }
  return parseAccount(await apiRequest<unknown>('/api/v1/me', { method: 'PATCH', body }));
}

export async function fetchOnboarding(signal?: AbortSignal): Promise<OnboardingProgress> {
  return parseOnboarding(await apiRequest<unknown>('/api/v1/onboarding', { signal }));
}

export interface OnboardingPatch {
  setupMode?: SetupMode;
  status?: OnboardingStatus;
  acceptTerms?: boolean;
  acknowledgePrivacy?: boolean;
}

export async function updateOnboarding(
  patch: OnboardingPatch
): Promise<OnboardingProgress> {
  const body: Record<string, unknown> = {};
  if (patch.setupMode !== undefined) body.setup_mode = patch.setupMode;
  if (patch.status !== undefined) body.status = patch.status;
  if (patch.acceptTerms !== undefined) body.accept_terms = patch.acceptTerms;
  if (patch.acknowledgePrivacy !== undefined) {
    body.acknowledge_privacy = patch.acknowledgePrivacy;
  }
  return parseOnboarding(
    await apiRequest<unknown>('/api/v1/onboarding', { method: 'PATCH', body })
  );
}

export interface ProfilePayload {
  preferredName: string;
  ageRange?: AgeRange | null;
  countryRegion?: string | null;
  pronouns?: string | null;
  role?: ProfileRole;
}

function profileBody(payload: Partial<ProfilePayload>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (payload.preferredName !== undefined) body.preferred_name = payload.preferredName;
  if (payload.ageRange !== undefined) body.age_range = payload.ageRange;
  if (payload.countryRegion !== undefined) body.country_region = payload.countryRegion;
  if (payload.pronouns !== undefined) body.pronouns = payload.pronouns;
  if (payload.role !== undefined) body.role = payload.role;
  return body;
}

export async function createProfile(payload: ProfilePayload): Promise<Profile> {
  return parseProfile(
    await apiRequest<unknown>('/api/v1/profiles', {
      method: 'POST',
      body: profileBody(payload),
    })
  );
}

export async function updateProfile(
  profileId: string,
  payload: Partial<ProfilePayload>
): Promise<Profile> {
  return parseProfile(
    await apiRequest<unknown>(`/api/v1/profiles/${profileId}`, {
      method: 'PATCH',
      body: profileBody(payload),
    })
  );
}
