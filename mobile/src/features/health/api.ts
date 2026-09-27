/**
 * Health endpoints (PRD 4, sections 26 and 33).
 *
 * Every path is nested under the profile the records belong to, because that
 * is what they belong to -- not to the account that is signed in.
 *
 * Records are parsed loosely on purpose: the screens read fields through their
 * section spec, so a field the server adds tomorrow arrives intact rather than
 * being dropped by a parser that has not heard of it. The parts the app
 * actually reasons about -- ids, the summary, the setup state -- are checked
 * properly, as everywhere else in the API layer.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  BloodType,
  HealthProfileStatus,
  HealthRecord,
  HealthSection,
  HealthSectionSummary,
  HealthSetup,
  HealthSummary,
  SectionSpec,
} from './types';

const SECTION_KEYS: readonly HealthSection[] = [
  'conditions',
  'medications',
  'allergies',
  'clinicians',
  'procedures',
  'blood_type',
  'medical_notes',
];

const STATUSES: readonly HealthProfileStatus[] = [
  'not_started',
  'in_progress',
  'complete',
];

const BLOOD_TYPES: readonly BloodType[] = [
  'A+',
  'A-',
  'B+',
  'B-',
  'AB+',
  'AB-',
  'O+',
  'O-',
  'unknown',
  'prefer_not_to_say',
];

function record(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(
  body: Record<string, unknown>,
  key: string,
  endpoint: string
): string {
  const value = body[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('server', `${endpoint} response is missing ${key}.`);
  }
  return value;
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function recordsUrl(profileId: string, spec: SectionSpec): string {
  return `/api/v1/profiles/${encodeURIComponent(profileId)}/${spec.path}`;
}

export function parseRecord(raw: unknown, endpoint: string): HealthRecord {
  const body = record(raw, endpoint);
  return {
    ...body,
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  } as HealthRecord;
}

function parseSection(raw: unknown): HealthSectionSummary | null {
  const body = record(raw, '/health-summary');
  const key = optionalString(body.key);
  if (!key || !SECTION_KEYS.includes(key as HealthSection)) return null;
  return {
    key: key as HealthSection,
    title: optionalString(body.title) ?? key,
    count: count(body.count),
    complete: body.complete === true,
    updatedAt: optionalString(body.updated_at),
  };
}

export function parseHealthSummary(raw: unknown): HealthSummary {
  const endpoint = '/api/v1/profiles/{id}/health-summary';
  const body = record(raw, endpoint);
  const sections = Array.isArray(body.sections) ? body.sections : [];
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    status: oneOf(body.status, STATUSES, 'not_started'),
    step: SECTION_KEYS.includes(body.step as HealthSection)
      ? (body.step as HealthSection)
      : null,
    bloodType: BLOOD_TYPES.includes(body.blood_type as BloodType)
      ? (body.blood_type as BloodType)
      : null,
    sections: sections
      .map(parseSection)
      .filter((section): section is HealthSectionSummary => section !== null),
    completedSections: count(body.completed_sections),
    totalSections: count(body.total_sections) || SECTION_KEYS.length,
    percent: count(body.percent),
    activeConditions: count(body.active_conditions),
    activeMedications: count(body.active_medications),
    activeSymptoms: count(body.active_symptoms),
    symptomUpdatesThisWeek: count(body.symptom_updates_this_week),
  };
}

export function parseHealthSetup(raw: unknown): HealthSetup {
  const endpoint = '/api/v1/profiles/{id}/health-setup';
  const body = record(raw, endpoint);
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    status: oneOf(body.status, STATUSES, 'not_started'),
    step: SECTION_KEYS.includes(body.step as HealthSection)
      ? (body.step as HealthSection)
      : null,
    bloodType: BLOOD_TYPES.includes(body.blood_type as BloodType)
      ? (body.blood_type as BloodType)
      : null,
  };
}

// --- requests ---------------------------------------------------------------

export async function fetchHealthSummary(
  profileId: string,
  signal?: AbortSignal
): Promise<HealthSummary> {
  return parseHealthSummary(
    await apiRequest<unknown>(
      `/api/v1/profiles/${encodeURIComponent(profileId)}/health-summary`,
      { signal }
    )
  );
}

export async function fetchHealthSetup(
  profileId: string,
  signal?: AbortSignal
): Promise<HealthSetup> {
  return parseHealthSetup(
    await apiRequest<unknown>(
      `/api/v1/profiles/${encodeURIComponent(profileId)}/health-setup`,
      { signal }
    )
  );
}

export interface HealthSetupPatch {
  status?: HealthProfileStatus;
  /** Explicit null clears the resume point. */
  step?: HealthSection | null;
  bloodType?: BloodType | null;
}

export async function updateHealthSetup(
  profileId: string,
  patch: HealthSetupPatch
): Promise<HealthSetup> {
  const body: Record<string, unknown> = {};
  if (patch.status !== undefined) body.status = patch.status;
  if (patch.step !== undefined) body.step = patch.step;
  if (patch.bloodType !== undefined) body.blood_type = patch.bloodType;

  return parseHealthSetup(
    await apiRequest<unknown>(
      `/api/v1/profiles/${encodeURIComponent(profileId)}/health-setup`,
      { method: 'PATCH', body }
    )
  );
}

export async function fetchRecords(
  profileId: string,
  spec: SectionSpec,
  signal?: AbortSignal
): Promise<HealthRecord[]> {
  const url = recordsUrl(profileId, spec);
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseRecord(entry, url));
}

export async function createRecord(
  profileId: string,
  spec: SectionSpec,
  payload: Record<string, unknown>
): Promise<HealthRecord> {
  const url = recordsUrl(profileId, spec);
  return parseRecord(
    await apiRequest<unknown>(url, { method: 'POST', body: payload }),
    url
  );
}

export async function updateRecord(
  profileId: string,
  spec: SectionSpec,
  recordId: string,
  payload: Record<string, unknown>
): Promise<HealthRecord> {
  const url = `${recordsUrl(profileId, spec)}/${encodeURIComponent(recordId)}`;
  return parseRecord(
    await apiRequest<unknown>(url, { method: 'PATCH', body: payload }),
    url
  );
}

export async function deleteRecord(
  profileId: string,
  spec: SectionSpec,
  recordId: string
): Promise<void> {
  await apiRequest<void>(
    `${recordsUrl(profileId, spec)}/${encodeURIComponent(recordId)}`,
    { method: 'DELETE' }
  );
}
