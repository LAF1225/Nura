/**
 * Today, daily check-in and dashboard endpoints (PRD 3, sections 15 and 16).
 *
 * Wire format is snake_case; the app sees camelCase. Responses are checked
 * field by field, so a malformed body becomes an `ApiError` rather than a
 * screen rendering `undefined` (the same approach as `devices.ts`).
 */
import type { ConnectionStatus } from '../../types/device';
import type {
  DashboardCard,
  DashboardCardKey,
  DashboardPreferences,
  DailyCheckIn,
  TodayCheckInState,
  TodayDevice,
  TodayItem,
  TodayProfile,
  TodaySummary,
  WellbeingLevel,
} from '../../types/today';
import { apiRequest } from './client';
import { ApiError } from './errors';

const TODAY_ENDPOINT = '/api/v1/today';
const CHECKIN_ENDPOINT = '/api/v1/daily-checkins/today';
const PREFERENCES_ENDPOINT = '/api/v1/dashboard-preferences';

const CONNECTION_STATUSES: readonly ConnectionStatus[] = ['unknown', 'online', 'offline'];
const WELLBEING: readonly WellbeingLevel[] = ['good', 'okay', 'not_great'];
const CARD_KEYS: readonly DashboardCardKey[] = [
  'daily_checkin',
  'device_status',
  'quick_actions',
  'health_profile',
  'medications',
  'appointments',
  'symptoms',
  'routines',
  'hydration',
  'physiotherapy',
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

function count(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

export function parseCheckIn(raw: unknown): DailyCheckIn {
  const body = record(raw, CHECKIN_ENDPOINT);
  return {
    date: requiredString(body, 'checkin_date', CHECKIN_ENDPOINT),
    // An unrecognised level must not read as "good"; `okay` is the neutral
    // one, and the server's CHECK constraint means this cannot happen in
    // practice.
    wellbeingLevel: oneOf(body.wellbeing_level, WELLBEING, 'okay'),
    note: optionalString(body.note),
    updatedAt: optionalString(body.updated_at),
    syncStatus: 'synced',
  };
}

function parseCard(raw: unknown): DashboardCard | null {
  const body = record(raw, PREFERENCES_ENDPOINT);
  const key = optionalString(body.key);
  // A card this build has no renderer for is dropped rather than guessed at.
  // That is what lets the server add a card before the app ships support.
  if (!key || !CARD_KEYS.includes(key as DashboardCardKey)) return null;
  return {
    key: key as DashboardCardKey,
    title: optionalString(body.title) ?? key,
    available: body.available === true,
    visible: body.visible === true,
    position: count(body.position, 0),
  };
}

function parseCards(raw: unknown): DashboardCard[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(parseCard)
    .filter((card): card is DashboardCard => card !== null)
    .sort((a, b) => a.position - b.position);
}

function parseProfile(raw: unknown): TodayProfile | null {
  if (raw === null || raw === undefined) return null;
  const body = record(raw, TODAY_ENDPOINT);
  const id = optionalString(body.id);
  const preferredName = optionalString(body.preferred_name);
  if (!id || !preferredName) return null;
  return { id, preferredName };
}

function parseDevice(raw: unknown): TodayDevice | null {
  if (raw === null || raw === undefined) return null;
  const body = record(raw, TODAY_ENDPOINT);
  const deviceId = optionalString(body.device_id);
  if (!deviceId) return null;
  return {
    deviceId,
    displayName: optionalString(body.display_name) ?? 'Nura',
    // An unrecognised value must never read as "online".
    connectionStatus: oneOf(body.connection_status, CONNECTION_STATUSES, 'unknown'),
    lastSeenAt: optionalString(body.last_seen_at),
    setupCompleted: body.setup_completed === true,
  };
}

function parseCheckInState(raw: unknown): TodayCheckInState {
  const body = record(raw, TODAY_ENDPOINT);
  const checkIn = body.checkin ? parseCheckIn(body.checkin) : null;
  return {
    status: checkIn ? 'completed' : 'not_completed',
    checkIn,
    recentCompletedCount: count(body.recent_completed_count, 0),
    recentWindowDays: count(body.recent_window_days, 7),
  };
}

function parseImportant(raw: unknown): TodayItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry) => {
    const body = record(entry, TODAY_ENDPOINT);
    const id = optionalString(body.id);
    const title = optionalString(body.title);
    if (!id || !title) return [];
    return [
      {
        id,
        type: optionalString(body.type) ?? 'unknown',
        title,
        subtitle: optionalString(body.subtitle) ?? undefined,
        dueAt: optionalString(body.due_at) ?? undefined,
        priority:
          body.priority === 'important' ? ('important' as const) : ('normal' as const),
        actionRoute: optionalString(body.action_route) ?? undefined,
      },
    ];
  });
}

export function parseTodaySummary(raw: unknown): TodaySummary {
  const body = record(raw, TODAY_ENDPOINT);
  return {
    localDate: requiredString(body, 'local_date', TODAY_ENDPOINT),
    profile: parseProfile(body.profile),
    dailyCheckIn: parseCheckInState(body.daily_checkin),
    device: parseDevice(body.device),
    cards: parseCards(body.cards),
    important: parseImportant(body.important),
  };
}

export function parseDashboardPreferences(raw: unknown): DashboardPreferences {
  const body = record(raw, PREFERENCES_ENDPOINT);
  return {
    profileId: optionalString(body.profile_id),
    cards: parseCards(body.cards),
  };
}

// --- requests ---------------------------------------------------------------

/**
 * The summary, and the body it came from.
 *
 * The raw body is handed back so it can be cached in wire format and revalidated
 * by this same parser when it is read again (see `services/today/cache.ts`).
 */
export async function fetchTodaySummaryWithBody(
  localDate: string,
  signal?: AbortSignal
): Promise<{ summary: TodaySummary; raw: unknown }> {
  const raw = await apiRequest<unknown>(
    `${TODAY_ENDPOINT}?local_date=${encodeURIComponent(localDate)}`,
    { signal }
  );
  return { summary: parseTodaySummary(raw), raw };
}

export async function fetchTodaySummary(
  localDate: string,
  signal?: AbortSignal
): Promise<TodaySummary> {
  return (await fetchTodaySummaryWithBody(localDate, signal)).summary;
}

export interface CheckInSubmission {
  localDate: string;
  wellbeingLevel: WellbeingLevel;
  note?: string | null;
  /**
   * When the user made this choice. Sent so the server can keep a newer
   * answer if this submission has been waiting in the offline queue
   * (PRD 3, section 28).
   */
  clientUpdatedAt?: string;
}

export interface CheckInSaved {
  checkIn: DailyCheckIn;
  /** False when the server already had a more recent edit and kept it. */
  applied: boolean;
}

export async function submitDailyCheckIn(
  submission: CheckInSubmission
): Promise<CheckInSaved> {
  const body = record(
    await apiRequest<unknown>(CHECKIN_ENDPOINT, {
      method: 'PUT',
      body: {
        local_date: submission.localDate,
        wellbeing_level: submission.wellbeingLevel,
        note: submission.note ?? null,
        ...(submission.clientUpdatedAt
          ? { client_updated_at: submission.clientUpdatedAt }
          : {}),
      },
    }),
    CHECKIN_ENDPOINT
  );
  return {
    checkIn: parseCheckIn(body.checkin),
    applied: body.applied === true,
  };
}

export async function fetchDashboardPreferences(
  signal?: AbortSignal
): Promise<DashboardPreferences> {
  return parseDashboardPreferences(
    await apiRequest<unknown>(PREFERENCES_ENDPOINT, { signal })
  );
}

/** Saves the layout. Order of `cards` is the order Today shows them in. */
export async function saveDashboardPreferences(
  cards: { key: DashboardCardKey; visible: boolean }[]
): Promise<DashboardPreferences> {
  return parseDashboardPreferences(
    await apiRequest<unknown>(PREFERENCES_ENDPOINT, {
      method: 'PUT',
      body: {
        cards: cards.map((card) => ({ card_key: card.key, visible: card.visible })),
      },
    })
  );
}
