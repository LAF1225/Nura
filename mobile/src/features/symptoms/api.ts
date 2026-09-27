/**
 * Symptom endpoints (PRD 6, sections 50-53 and 63).
 *
 * Every path is nested under the profile the records belong to, because that is
 * what they belong to -- not to the account that is signed in.
 *
 * Responses are parsed rather than cast. The fields the app reasons about -- a
 * status, a change state, whether the safety notice is urgent -- are checked and
 * given safe fallbacks, so a field the server renames cannot turn into a screen
 * that silently shows the wrong thing. `urgent` in particular defaults to
 * *false*: a missing field must never read as an emergency.
 *
 * A photo is fetched through `photoSource`, which returns a URL and a bearer
 * token together. There is no public or signed URL anywhere in this module
 * (PRD 6, section 63).
 */
import { apiRequest, apiUpload, mediaSource } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  ChangeState,
  EntryPayload,
  EpisodePayload,
  EpisodeStatus,
  LocalPhotoDraft,
  PhotoContentType,
  SymptomEntry,
  SymptomEpisode,
  SymptomPhoto,
  SymptomSafety,
  SymptomSource,
  SymptomSummary,
  TodaySymptoms,
  WorseningReason,
} from './types';

const EPISODE_STATUSES: readonly EpisodeStatus[] = [
  'active',
  'resolved',
  'recurring',
  'historical',
];
const CHANGE_STATES: readonly ChangeState[] = [
  'improving',
  'same',
  'worsening',
  'unsure',
];
const SOURCES: readonly SymptomSource[] = [
  'manual_app',
  'guided_app',
  'robot_voice_future',
  'caregiver_future',
  'import_future',
];
const CONTENT_TYPES: readonly PhotoContentType[] = [
  'image/jpeg',
  'image/png',
  'image/heic',
  'image/heif',
];
const REASONS: readonly WorseningReason[] = [
  'reported_worsening',
  'severity_increase',
  'new_associated_symptom',
];

// --- small parsing helpers --------------------------------------------------

function object(value: unknown, endpoint: string): Record<string, unknown> {
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

function text(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function nullableCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function maybeOneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

// --- parsing ----------------------------------------------------------------

export function parsePhoto(raw: unknown, endpoint: string): SymptomPhoto {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    entryId: requiredString(body, 'symptom_entry_id', endpoint),
    contentType: oneOf(body.content_type, CONTENT_TYPES, 'image/jpeg'),
    byteSize: count(body.byte_size),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    syncStatus: 'synced',
  };
}

export function parseEntry(raw: unknown, endpoint: string): SymptomEntry {
  const body = object(raw, endpoint);
  const photos = Array.isArray(body.photos) ? body.photos : [];
  return {
    id: requiredString(body, 'id', endpoint),
    episodeId: requiredString(body, 'symptom_episode_id', endpoint),
    recordedAt: requiredString(body, 'recorded_at', endpoint),
    mainSymptom: text(body.main_symptom),
    site: text(body.site),
    onsetText: text(body.onset_text),
    onsetAt: text(body.onset_at),
    onsetDate: text(body.onset_date),
    character: text(body.character),
    radiation: text(body.radiation),
    timing: text(body.timing),
    severity: nullableCount(body.severity),
    changeState: maybeOneOf(body.change_state, CHANGE_STATES),
    freeTextNote: text(body.free_text_note),
    associatedSymptoms: stringList(body.associated_symptoms),
    exacerbatingFactors: stringList(body.exacerbating_factors),
    relievingFactors: stringList(body.relieving_factors),
    negatedItems: stringList(body.negated_items),
    uncertainItems: stringList(body.uncertain_items),
    contextDependentItems: stringList(body.context_dependent_items),
    source: oneOf(body.source, SOURCES, 'manual_app'),
    photos: photos.map((entry) => parsePhoto(entry, endpoint)),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    syncStatus: 'synced',
  };
}

/**
 * The safety block.
 *
 * `urgent` and `worsening` both default to false. A response that is missing
 * them, or one from an older server, must read as "nothing to say" -- the
 * failure mode of a safety field defaulting the other way is unacceptable.
 */
export function parseSafety(raw: unknown): SymptomSafety {
  if (raw === null || raw === undefined) {
    return { worsening: false, reasons: [], notice: null, urgent: false };
  }
  const body = object(raw, '/symptoms');
  const reasons = Array.isArray(body.reasons) ? body.reasons : [];
  return {
    worsening: body.worsening === true,
    reasons: reasons.filter((value): value is WorseningReason =>
      REASONS.includes(value as WorseningReason)
    ),
    notice: text(body.notice),
    urgent: body.urgent === true,
  };
}

export function parseEpisode(raw: unknown, endpoint: string): SymptomEpisode {
  const body = object(raw, endpoint);
  const entries = Array.isArray(body.entries) ? body.entries : undefined;
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    name: text(body.name) ?? 'Symptom',
    bodySite: text(body.body_site),
    status: oneOf(body.status, EPISODE_STATUSES, 'active'),
    firstNoticedAt: text(body.first_noticed_at),
    firstNoticedDate: text(body.first_noticed_date),
    firstNoticedYear: nullableCount(body.first_noticed_year),
    firstNoticedText: text(body.first_noticed_text),
    resolvedAt: text(body.resolved_at),
    previousEpisodeId: text(body.previous_episode_id),
    source: oneOf(body.source, SOURCES, 'manual_app'),
    entryCount: count(body.entry_count),
    latestEntry:
      body.latest_entry === null || body.latest_entry === undefined
        ? null
        : parseEntry(body.latest_entry, endpoint),
    safety: parseSafety(body.safety),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    updatedAt: text(body.updated_at) ?? new Date().toISOString(),
    entries: entries?.map((entry) => parseEntry(entry, endpoint)),
  };
}

export function parseSummary(raw: unknown, endpoint: string): SymptomSummary {
  const body = object(raw, endpoint);
  return {
    activeCount: count(body.active_count),
    worseningCount: count(body.worsening_count),
    recentUpdatesCount: count(body.recent_updates_count),
    hasEpisodes: body.has_episodes === true,
  };
}

export function parseTodaySymptoms(raw: unknown): TodaySymptoms | null {
  if (raw === null || raw === undefined) return null;
  const endpoint = '/api/v1/today';
  const body = object(raw, endpoint);
  const recent = body.most_recent;

  return {
    activeCount: count(body.active_count),
    worseningCount: count(body.worsening_count),
    mostRecent:
      recent === null || recent === undefined
        ? null
        : (() => {
            const entry = object(recent, endpoint);
            return {
              episodeId: requiredString(entry, 'episode_id', endpoint),
              name: text(entry.name) ?? 'Symptom',
              severity: nullableCount(entry.severity),
              changeState: maybeOneOf(entry.change_state, CHANGE_STATES),
              updatedAt: text(entry.updated_at) ?? new Date().toISOString(),
            };
          })(),
    hasEpisodes: body.has_episodes === true,
  };
}

// --- requests ---------------------------------------------------------------

function base(profileId: string): string {
  return `/api/v1/profiles/${encodeURIComponent(profileId)}/symptoms`;
}

export interface EpisodeFilter {
  /** True for what is ongoing: active and recurring together. */
  active?: boolean;
  status?: EpisodeStatus;
  name?: string;
}

export async function fetchEpisodes(
  profileId: string,
  filter: EpisodeFilter = {},
  signal?: AbortSignal
): Promise<SymptomEpisode[]> {
  const query = new URLSearchParams();
  if (filter.active) query.set('active', 'true');
  if (filter.status) query.set('status', filter.status);
  if (filter.name) query.set('name', filter.name);

  const suffix = query.toString();
  const url = suffix ? `${base(profileId)}?${suffix}` : base(profileId);
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseEpisode(entry, url));
}

export async function fetchEpisode(
  profileId: string,
  episodeId: string,
  signal?: AbortSignal
): Promise<SymptomEpisode> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}`;
  return parseEpisode(await apiRequest<unknown>(url, { signal }), url);
}

export async function fetchSymptomSummary(
  profileId: string,
  signal?: AbortSignal
): Promise<SymptomSummary> {
  const url = `${base(profileId)}/summary`;
  return parseSummary(await apiRequest<unknown>(url, { signal }), url);
}

/** Creates an episode and its first observation in one request (s30). */
export async function createEpisode(
  profileId: string,
  payload: EpisodePayload
): Promise<SymptomEpisode> {
  const url = base(profileId);
  const body = object(
    await apiRequest<unknown>(url, { method: 'POST', body: payload }),
    url
  );
  return parseEpisode(body.episode, url);
}

export interface EntrySaved {
  entry: SymptomEntry;
  /** False for a replay of a client id the server already has (s61). */
  created: boolean;
  safety: SymptomSafety;
}

export async function createEntry(
  profileId: string,
  episodeId: string,
  payload: EntryPayload
): Promise<EntrySaved> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}/entries`;
  const body = object(
    await apiRequest<unknown>(url, { method: 'POST', body: payload }),
    url
  );
  return {
    entry: parseEntry(body.entry, url),
    created: body.created === true,
    safety: parseSafety(body.safety),
  };
}

export async function updateEntry(
  profileId: string,
  episodeId: string,
  entryId: string,
  patch: Partial<EntryPayload>
): Promise<EntrySaved> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}/entries/${encodeURIComponent(entryId)}`;
  const body = object(
    await apiRequest<unknown>(url, { method: 'PATCH', body: patch }),
    url
  );
  return {
    entry: parseEntry(body.entry, url),
    created: false,
    safety: parseSafety(body.safety),
  };
}

export interface EpisodePatch {
  name?: string;
  body_site?: string | null;
  status?: EpisodeStatus;
  first_noticed_date?: string | null;
  first_noticed_text?: string | null;
}

export async function updateEpisode(
  profileId: string,
  episodeId: string,
  patch: EpisodePatch
): Promise<SymptomEpisode> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}`;
  return parseEpisode(
    await apiRequest<unknown>(url, { method: 'PATCH', body: patch }),
    url
  );
}

export async function resolveEpisode(
  profileId: string,
  episodeId: string
): Promise<SymptomEpisode> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}/resolve`;
  return parseEpisode(await apiRequest<unknown>(url, { method: 'POST' }), url);
}

/** Records that a resolved symptom has come back (PRD 6, section 38). */
export async function recordRecurrence(
  profileId: string,
  episodeId: string,
  payload: Omit<EpisodePayload, 'name'> & { name?: string }
): Promise<SymptomEpisode> {
  const url = `${base(profileId)}/${encodeURIComponent(episodeId)}/recur`;
  const body = object(
    await apiRequest<unknown>(url, { method: 'POST', body: payload }),
    url
  );
  return parseEpisode(body.episode, url);
}

export async function deleteEpisode(profileId: string, episodeId: string): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/${encodeURIComponent(episodeId)}`, {
    method: 'DELETE',
  });
}

// --- photos -----------------------------------------------------------------

function photoBase(profileId: string, episodeId: string, entryId: string): string {
  return `${base(profileId)}/${encodeURIComponent(episodeId)}/entries/${encodeURIComponent(entryId)}/photos`;
}

const EXTENSIONS: Record<PhotoContentType, string> = {
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/heic': 'heic',
  'image/heif': 'heif',
};

export async function uploadPhoto(
  profileId: string,
  episodeId: string,
  entryId: string,
  photo: LocalPhotoDraft
): Promise<SymptomPhoto> {
  const url = photoBase(profileId, episodeId, entryId);
  // A generic name: the server ignores it, and a filename from a camera roll
  // can carry a date and a place (PRD 6, section 62).
  const name = `symptom.${EXTENSIONS[photo.contentType]}`;
  const raw = await apiUpload<unknown>(url, {
    file: { uri: photo.localUri, name, type: photo.contentType },
    fields: { client_photo_id: photo.clientPhotoId },
  });
  return parsePhoto(raw, url);
}

export async function deletePhoto(
  profileId: string,
  episodeId: string,
  entryId: string,
  photoId: string
): Promise<void> {
  await apiRequest<void>(
    `${photoBase(profileId, episodeId, entryId)}/${encodeURIComponent(photoId)}`,
    { method: 'DELETE' }
  );
}

/**
 * An authenticated `<Image>` source for one photo, or null when signed out.
 *
 * The URL is only ever used with the token beside it: the route authorizes the
 * profile, the episode, the entry and the photo before it serves a byte
 * (PRD 6, section 63).
 */
export async function photoSource(
  profileId: string,
  episodeId: string,
  entryId: string,
  photoId: string
): Promise<{ uri: string; headers: Record<string, string> } | null> {
  return mediaSource(
    `${photoBase(profileId, episodeId, entryId)}/${encodeURIComponent(photoId)}/content`
  );
}
