/**
 * Safety monitoring, SOS and caregiver-alert endpoints (PRD 10, §103).
 *
 * Responses are parsed rather than cast, the same way the caregiver client
 * parses. Three decisions in here carry a rule.
 *
 * **An unknown capability key is dropped, and an unknown state is not.** A
 * capability a later backend adds is not rendered as a mystery row; but a
 * *state* nobody recognises falls back to `unavailable`, which is the
 * conservative direction. Guessing `available` for something unrecognised is
 * how a screen ends up offering a call that cannot happen (section 64).
 *
 * **An attempt's rendered `line` is kept and never rebuilt.** Section 42's
 * wording lives on the server; a client that assembled its own sentence from
 * `channel` and `status` would be a second place "Ayesha has been contacted"
 * could be written.
 *
 * **Nothing here sends an event type the user did not press.** `raiseSos`
 * takes no type from a caller at all -- it posts `manual_sos`, which is the
 * only thing a button on a phone means (sections 12 and 16).
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  Capabilities,
  Capability,
  CapabilityKey,
  CapabilityState,
  DurationMode,
  EscalationAttempt,
  EscalationAttemptStatus,
  EscalationChannel,
  EscalationOutcome,
  EventResolution,
  FalsePositiveReason,
  MonitoringSession,
  MonitoringStartInput,
  MonitoringStatus,
  SafetyAlert,
  SafetyAlertList,
  SafetyEvent,
  SafetyEventDetail,
  SafetyEventStatus,
  SafetyEventType,
  SafetyStatus,
  UserResponse,
} from './types';

export const CAPABILITY_KEYS: readonly CapabilityKey[] = [
  'manual_sos',
  'in_app_safety_checks',
  'caregiver_in_app_alerts',
  'push_delivery',
  'sms_delivery',
  'audio_calling',
  'robot_detection',
];

const CAPABILITY_STATES: readonly CapabilityState[] = [
  'available',
  'not_configured',
  'not_connected',
  'unavailable',
];

const MONITORING_STATUSES: readonly MonitoringStatus[] = [
  'active',
  'ended',
  'cancelled',
  'expired',
  'error',
];

const DURATION_MODES: readonly DurationMode[] = [
  '30_minutes',
  '1_hour',
  'until_bedtime',
  'until_turned_off',
  'custom',
];

const EVENT_TYPES: readonly SafetyEventType[] = [
  'manual_sos',
  'possible_fall',
  'possible_prolonged_immobility',
  'possible_vomiting',
  'possible_seizure_like_activity',
  'possible_distress',
  'call_for_help',
  'test_event',
];

const EVENT_STATUSES: readonly SafetyEventStatus[] = [
  'checking_user',
  'second_prompt',
  'escalating',
  'escalated',
  'resolved',
  'cancelled',
];

const RESOLUTIONS: readonly EventResolution[] = [
  'user_confirmed_ok',
  'help_requested',
  'no_response_escalated',
  'false_alarm',
  'cancelled_by_user',
  'resolved_after_contact',
  'test_event',
  'system_error',
];

const OUTCOMES: readonly EscalationOutcome[] = [
  'complete',
  'partial',
  'failed',
  'no_contacts',
  'providers_not_configured',
  'cancelled',
];

const CHANNELS: readonly EscalationChannel[] = [
  'in_app',
  'push',
  'sms_future',
  'voice_call_future',
];

const ATTEMPT_STATUSES: readonly EscalationAttemptStatus[] = [
  'pending',
  'attempted',
  'delivered',
  'failed',
  'skipped',
  'not_configured',
];

const RESPONSES: readonly UserResponse[] = ['im_okay', 'need_help', 'false_alarm'];

export const FALSE_POSITIVE_REASONS: readonly FalsePositiveReason[] = [
  'normal_movement',
  'sensor_error',
  'user_testing',
  'other',
];

// --- parsing helpers ---------------------------------------------------------

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

function flag(value: unknown): boolean {
  return value === true;
}

/** `true`, `false` or "nobody said" -- three states, deliberately (section 48). */
function tristate(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function optional<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

// --- parsers -----------------------------------------------------------------

function parseCapability(value: unknown, endpoint: string): Capability | null {
  const body = object(value, endpoint);
  const key = body.key;
  if (!CAPABILITY_KEYS.includes(key as CapabilityKey)) return null;
  return {
    key: key as CapabilityKey,
    // Anything unrecognised is `unavailable`, never `available`: guessing in
    // the generous direction is how a screen offers something that cannot
    // happen (section 64).
    state: oneOf(body.state, CAPABILITY_STATES, 'unavailable'),
    label: text(body.label) ?? (key as string),
    stateLabel: text(body.state_label) ?? '',
  };
}

function parseCapabilities(value: unknown, endpoint: string): Capability[] {
  return list(value)
    .map((item) => parseCapability(item, endpoint))
    .filter((item): item is Capability => item !== null);
}

function parseSession(value: unknown, endpoint: string): MonitoringSession {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    status: oneOf(body.status, MONITORING_STATUSES, 'ended'),
    startedAt: text(body.started_at) ?? '',
    endsAt: text(body.ends_at),
    durationMode: oneOf(body.duration_mode, DURATION_MODES, 'until_turned_off'),
    timezone: text(body.timezone) ?? 'UTC',
    responseTimeoutSeconds: count(body.response_timeout_seconds),
    secondPromptEnabled: flag(body.second_prompt_enabled),
    secondPromptTimeoutSeconds: count(body.second_prompt_timeout_seconds),
  };
}

function parseAttempt(value: unknown, endpoint: string): EscalationAttempt {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    recipientLabel: text(body.recipient_label) ?? '',
    isCaregiver: flag(body.is_caregiver),
    priority: count(body.priority),
    channel: oneOf(body.channel, CHANNELS, 'in_app'),
    status: oneOf(body.status, ATTEMPT_STATUSES, 'pending'),
    failureCode: text(body.failure_code),
    attemptedAt: text(body.attempted_at),
    // Kept exactly as the server rendered it (section 42).
    line: text(body.line) ?? '',
  };
}

function parseEvent(value: unknown, endpoint: string): SafetyEvent {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    eventType: oneOf(body.event_type, EVENT_TYPES, 'possible_distress'),
    eventLabel: text(body.event_label) ?? '',
    triggeredAt: text(body.triggered_at) ?? '',
    status: oneOf(body.status, EVENT_STATUSES, 'resolved'),
    resolution: optional(body.resolution, RESOLUTIONS),
    resolutionLabel: text(body.resolution_label),
    escalationOutcome: optional(body.escalation_outcome, OUTCOMES),
    escalationOutcomeLabel: text(body.escalation_outcome_label),
    userResponse: optional(body.user_response, RESPONSES),
    falsePositive: tristate(body.false_positive),
  };
}

function parseEventDetail(value: unknown, endpoint: string): SafetyEventDetail {
  const body = object(value, endpoint);
  return {
    ...parseEvent(value, endpoint),
    description: text(body.description) ?? '',
    noResponseSeconds: nullableCount(body.no_response_seconds),
    noResponseLabel: text(body.no_response_label),
    responseDeadlineAt: text(body.response_deadline_at),
    secondPromptDeadlineAt: text(body.second_prompt_deadline_at),
    escalationStartedAt: text(body.escalation_started_at),
    resolvedAt: text(body.resolved_at),
    falsePositiveReason: optional(body.false_positive_reason, FALSE_POSITIVE_REASONS),
    attempts: list(body.attempts).map((item) => parseAttempt(item, endpoint)),
    alertCount: count(body.alert_count),
  };
}

function parseStatus(value: unknown, endpoint: string): SafetyStatus {
  const body = object(value, endpoint);
  return {
    monitoring:
      body.monitoring === null || body.monitoring === undefined
        ? null
        : parseSession(body.monitoring, endpoint),
    monitoringSentence: text(body.monitoring_sentence) ?? '',
    activeEvent:
      body.active_event === null || body.active_event === undefined
        ? null
        : parseEventDetail(body.active_event, endpoint),
    emergencyMode: flag(body.emergency_mode),
    capabilities: parseCapabilities(body.capabilities, endpoint),
    emergencyContactCount: count(body.emergency_contact_count),
    noContactsWarning: text(body.no_contacts_warning),
    noProvidersWarning: text(body.no_providers_warning),
    detectionNotice: text(body.detection_notice),
    checkPrompt: text(body.check_prompt) ?? '',
  };
}

function parseAlert(value: unknown, endpoint: string): SafetyAlert {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    safetyEventId: text(body.safety_event_id) ?? '',
    eventType: oneOf(body.event_type, EVENT_TYPES, 'possible_distress'),
    eventLabel: text(body.event_label) ?? '',
    triggeredAt: text(body.triggered_at) ?? '',
    createdAt: text(body.created_at) ?? '',
    readAt: text(body.read_at),
    acknowledgedAt: text(body.acknowledged_at),
    eventStatus: oneOf(body.event_status, EVENT_STATUSES, 'resolved'),
    eventResolution: optional(body.event_resolution, RESOLUTIONS),
    escalationOutcome: optional(body.escalation_outcome, OUTCOMES),
    sentence: text(body.sentence) ?? '',
  };
}

// --- requests ----------------------------------------------------------------

const base = (profileId: string) => `/api/v1/profiles/${profileId}/safety`;

export async function fetchSafetyStatus(profileId: string): Promise<SafetyStatus> {
  return parseStatus(
    await apiRequest<unknown>(`${base(profileId)}/status`),
    'safety status'
  );
}

export async function fetchCapabilities(profileId: string): Promise<Capabilities> {
  const endpoint = 'safety capabilities';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/capabilities`),
    endpoint
  );
  return {
    capabilities: parseCapabilities(body.capabilities, endpoint),
    externalDeliveryAvailable: flag(body.external_delivery_available),
    warning: text(body.warning),
  };
}

export async function startMonitoring(
  profileId: string,
  input: MonitoringStartInput
): Promise<MonitoringSession> {
  return parseSession(
    await apiRequest<unknown>(`${base(profileId)}/monitoring/start`, {
      method: 'POST',
      body: {
        duration_mode: input.durationMode,
        timezone: input.timezone,
        response_timeout_seconds: input.responseTimeoutSeconds,
        second_prompt_enabled: input.secondPromptEnabled,
        ...(input.customMinutes === undefined
          ? {}
          : { custom_minutes: input.customMinutes }),
      },
    }),
    'start monitoring'
  );
}

export async function stopMonitoring(
  profileId: string,
  options: { confirmActiveEvent?: boolean } = {}
): Promise<SafetyStatus> {
  const query = options.confirmActiveEvent ? '?confirm_active_event=true' : '';
  return parseStatus(
    await apiRequest<unknown>(`${base(profileId)}/monitoring/stop${query}`, {
      method: 'POST',
    }),
    'stop monitoring'
  );
}

/**
 * An emergency request (sections 12 and 77).
 *
 * `clientEventId` is what makes a retry safe: a request that timed out after
 * the server stored it comes back as the same event rather than a second
 * emergency. The caller passes nothing else -- there is no event type to
 * choose, because a button on a phone means one thing.
 */
export async function raiseSos(
  profileId: string,
  clientEventId: string
): Promise<SafetyEventDetail> {
  return parseEventDetail(
    await apiRequest<unknown>(`${base(profileId)}/sos`, {
      method: 'POST',
      body: { event_type: 'manual_sos', client_event_id: clientEventId },
    }),
    'emergency request'
  );
}

export async function respondToSafetyEvent(
  profileId: string,
  eventId: string,
  response: UserResponse
): Promise<SafetyEventDetail> {
  return parseEventDetail(
    await apiRequest<unknown>(`${base(profileId)}/events/${eventId}/respond`, {
      method: 'POST',
      body: { response },
    }),
    'safety response'
  );
}

export async function cancelSafetyEvent(
  profileId: string,
  eventId: string
): Promise<SafetyEventDetail> {
  return parseEventDetail(
    await apiRequest<unknown>(`${base(profileId)}/events/${eventId}/cancel`, {
      method: 'POST',
    }),
    'cancel safety event'
  );
}

export async function markFalseAlarm(
  profileId: string,
  eventId: string,
  falsePositive: boolean,
  reason: FalsePositiveReason | null
): Promise<SafetyEventDetail> {
  return parseEventDetail(
    await apiRequest<unknown>(`${base(profileId)}/events/${eventId}/false-alarm`, {
      method: 'POST',
      body: { false_positive: falsePositive, reason },
    }),
    'false alarm'
  );
}

export async function fetchSafetyEvents(profileId: string): Promise<SafetyEvent[]> {
  const endpoint = 'safety history';
  const body = object(await apiRequest<unknown>(`${base(profileId)}/events`), endpoint);
  return list(body.events).map((item) => parseEvent(item, endpoint));
}

export async function fetchSafetyEvent(
  profileId: string,
  eventId: string
): Promise<SafetyEventDetail> {
  return parseEventDetail(
    await apiRequest<unknown>(`${base(profileId)}/events/${eventId}`),
    'safety event'
  );
}

export async function fetchSafetyAlerts(profileId: string): Promise<SafetyAlertList> {
  const endpoint = 'safety alerts';
  const body = object(
    await apiRequest<unknown>(`/api/v1/profiles/${profileId}/care/safety-alerts`),
    endpoint
  );
  return {
    alerts: list(body.alerts).map((item) => parseAlert(item, endpoint)),
    unreadCount: count(body.unread_count),
  };
}

export async function acknowledgeSafetyAlert(
  profileId: string,
  alertId: string
): Promise<SafetyAlert> {
  return parseAlert(
    await apiRequest<unknown>(
      `/api/v1/profiles/${profileId}/care/safety-alerts/${alertId}/acknowledge`,
      { method: 'POST' }
    ),
    'acknowledge safety alert'
  );
}
