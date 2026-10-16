/**
 * The robot's capability, preference and presentation endpoints (PRD 11, s122).
 *
 * Responses are parsed field by field rather than cast, the same way the
 * safety and caregiver clients parse. Three decisions in here carry a rule.
 *
 * **An unrecognised capability state falls back to `not_connected`, never to
 * `available`.** The conservative direction, and the same choice PRD 10's
 * client made for the same reason: guessing optimistically about something
 * unrecognised is how a screen ends up offering a volume control for a speaker
 * that does not exist (sections 12 and 47).
 *
 * **`reducedMotion` keeps its three states.** `tristate` returns null for
 * anything that is not a boolean, and null means *follow the account's
 * accessibility setting* (sections 30 and 105). Collapsing it to false would
 * silently stop the robot following that setting.
 *
 * **A presentation's `line` is kept verbatim** (section 96). The sentence is
 * rendered by `services/robot/wording.py`, which is the one place that knows
 * "sent to Nura" and "shown" are different claims (section 14). A client that
 * assembled its own from `status` would be a second place that could blur
 * them.
 *
 * **Nothing here sends an acknowledgement.** Only a device may say what it
 * drew, and the app holds no device token -- so there is no function in this
 * file that could mark anything displayed (sections 14 and 19).
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  AckState,
  Capabilities,
  Capability,
  CapabilityKey,
  CapabilitySource,
  CapabilityState,
  FaceState,
  MedicationPrivacyLevel,
  Presentation,
  PresentationLayout,
  PresentationMode,
  PresentationPreferences,
  PresentationPreferencesInput,
  PresentationSource,
  PresentationStatus,
  PresentationType,
  RobotStatus,
  SleepScreenMode,
} from './types';

const CAPABILITY_KEYS: readonly CapabilityKey[] = [
  'display',
  'display_text',
  'display_animation',
  'speaker',
  'tts',
  'audio_playback',
  'microphone',
  'wake_word',
  'camera',
  'camera_detection',
  'buttons',
  'touch',
];

const CAPABILITY_STATES: readonly CapabilityState[] = [
  'available',
  'unavailable',
  'not_verified',
  'not_connected',
];

const CAPABILITY_SOURCES: readonly CapabilitySource[] = [
  'device_report',
  'self_test',
  'default',
];

const PRESENTATION_TYPES: readonly PresentationType[] = [
  'face_state',
  'info_card',
  'medication_reminder',
  'appointment_reminder',
  'family_message',
  'assistant_response',
  'safety_check',
  'safety_status',
  'emergency_status',
  'system_status',
  'setup_code',
];

const PRESENTATION_STATUSES: readonly PresentationStatus[] = [
  'queued',
  'sent',
  'acknowledged',
  'displayed',
  'completed',
  'expired',
  'failed',
  'cancelled',
  'not_supported',
];

const LAYOUTS: readonly PresentationLayout[] = [
  'FACE',
  'TITLE_BODY',
  'TITLE_VALUE',
  'REMINDER',
  'MESSAGE',
  'STATUS',
  'EMERGENCY',
  'PAIRING_CODE',
];

const SOURCES: readonly PresentationSource[] = [
  'medication',
  'appointment',
  'family_message',
  'assistant',
  'safety',
  'system',
  'user',
];

const ACK_STATES: readonly AckState[] = [
  'received',
  'render_started',
  'render_completed',
  'failed',
  'unsupported',
];

const MODES: readonly PresentationMode[] = [
  'companion',
  'information',
  'focus',
  'sleep',
  'privacy',
  'safety',
  'emergency',
  'offline',
  'setup',
  'error',
];

const FACE_STATES: readonly FaceState[] = [
  'idle',
  'listening',
  'thinking',
  'speaking',
  'happy',
  'concerned',
  'sleeping',
  'privacy',
  'offline',
];

export const MEDICATION_PRIVACY_LEVELS: readonly MedicationPrivacyLevel[] = [
  'full',
  'name_only',
  'private',
];

export const SLEEP_SCREEN_MODES: readonly SleepScreenMode[] = [
  'dim',
  'sleeping_face',
  'blank',
];

const CONNECTION_STATUSES = ['unknown', 'online', 'offline'] as const;

function base(deviceId: string): string {
  return `/api/v1/devices/${deviceId}`;
}

// --- parsing primitives ------------------------------------------------------

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

function level(value: unknown, fallback: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback;
  return Math.min(100, Math.max(0, Math.round(value)));
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function flag(value: unknown): boolean {
  return value === true;
}

/** `true`, `false`, or "nobody has chosen" -- three states (sections 30, 105). */
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
  const key = optional(body.key, CAPABILITY_KEYS);
  // A capability a later backend adds is dropped rather than rendered as a
  // mystery row. A *state* nobody recognises is not dropped -- it falls back
  // to not_connected, which is the conservative direction.
  if (key === null) return null;
  return {
    key,
    state: oneOf(body.state, CAPABILITY_STATES, 'not_connected'),
    reportedState: oneOf(body.reported_state, CAPABILITY_STATES, 'not_connected'),
    label: requiredString(body, 'label', endpoint),
    stateLabel: requiredString(body, 'state_label', endpoint),
    source: oneOf(body.source, CAPABILITY_SOURCES, 'default'),
    reportedAt: text(body.reported_at),
    firmwareVersion: text(body.firmware_version),
    stale: flag(body.stale),
  };
}

function parseCapabilities(value: unknown, endpoint: string): Capabilities {
  const body = object(value, endpoint);
  return {
    deviceId: requiredString(body, 'device_id', endpoint),
    capabilities: list(body.capabilities)
      .map((row) => parseCapability(row, endpoint))
      .filter((row): row is Capability => row !== null),
    displayAvailable: flag(body.display_available),
    textAvailable: flag(body.text_available),
    animationAvailable: flag(body.animation_available),
    audioAvailable: flag(body.audio_available),
    speechAvailable: flag(body.speech_available),
    inputAvailable: flag(body.input_available),
    hardwareNote: requiredString(body, 'hardware_note', endpoint),
  };
}

function parsePreferences(value: unknown, endpoint: string): PresentationPreferences {
  const body = object(value, endpoint);
  return {
    deviceId: requiredString(body, 'device_id', endpoint),
    brightness: level(body.brightness, 70),
    volume: level(body.volume, 40),
    reducedMotion: tristate(body.reduced_motion),
    effectiveReducedMotion: flag(body.effective_reduced_motion),
    medicationPrivacyLevel: oneOf(
      body.medication_privacy_level,
      MEDICATION_PRIVACY_LEVELS,
      // The conservative default (section 104): an unrecognised value must
      // never read as "show everything".
      'private'
    ),
    readMedicationsAloud: flag(body.read_medications_aloud),
    readMessagesAloud: flag(body.read_messages_aloud),
    readAssistantAloud: flag(body.read_assistant_aloud),
    sleepScreenMode: oneOf(body.sleep_screen_mode, SLEEP_SCREEN_MODES, 'dim'),
    faceAnimationEnabled: flag(body.face_animation_enabled),
    familyMessageDisplayEnabled: flag(body.family_message_display_enabled),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

function parsePresentation(value: unknown, endpoint: string): Presentation {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    presentationType: oneOf(body.presentation_type, PRESENTATION_TYPES, 'info_card'),
    // An unrecognised status reads as `queued`, never as `completed`: section
    // 14's whole point is that nothing may be assumed to have been shown.
    status: oneOf(body.status, PRESENTATION_STATUSES, 'queued'),
    layout: oneOf(body.layout, LAYOUTS, 'TITLE_BODY'),
    source: oneOf(body.source, SOURCES, 'system'),
    priority: count(body.priority),
    title: text(body.title),
    summary: text(body.summary),
    sensitive: flag(body.sensitive),
    createdAt: requiredString(body, 'created_at', endpoint),
    availableAt: requiredString(body, 'available_at', endpoint),
    expiresAt: text(body.expires_at),
    sentAt: text(body.sent_at),
    displayedAt: text(body.displayed_at),
    completedAt: text(body.completed_at),
    ackState: optional(body.ack_state, ACK_STATES),
    failureCode: text(body.failure_code),
    cancelReason: text(body.cancel_reason),
    line: requiredString(body, 'line', endpoint),
  };
}

function parseStatus(value: unknown, endpoint: string): RobotStatus {
  const body = object(value, endpoint);
  const current = body.current;
  return {
    deviceId: requiredString(body, 'device_id', endpoint),
    displayName: requiredString(body, 'display_name', endpoint),
    // An unrecognised value must never read as "online".
    connectionStatus: oneOf(body.connection_status, CONNECTION_STATUSES, 'unknown'),
    lastSeenAt: text(body.last_seen_at),
    mode: oneOf(body.mode, MODES, 'offline'),
    modeLabel: requiredString(body, 'mode_label', endpoint),
    face: optional(body.face, FACE_STATES),
    queueDepth: count(body.queue_depth),
    current:
      current === null || current === undefined
        ? null
        : parsePresentation(current, endpoint),
    setupComplete: flag(body.setup_complete),
    offlineNote: text(body.offline_note),
  };
}

// --- requests ----------------------------------------------------------------

export async function fetchRobotCapabilities(deviceId: string): Promise<Capabilities> {
  return parseCapabilities(
    await apiRequest<unknown>(`${base(deviceId)}/capabilities`),
    'robot capabilities'
  );
}

export async function fetchPresentationPreferences(
  deviceId: string
): Promise<PresentationPreferences> {
  return parsePreferences(
    await apiRequest<unknown>(`${base(deviceId)}/presentation-preferences`),
    'robot preferences'
  );
}

export async function updatePresentationPreferences(
  deviceId: string,
  input: PresentationPreferencesInput
): Promise<PresentationPreferences> {
  const body: Record<string, unknown> = {};
  // Built key by key, so `reducedMotion: null` reaches the server as null --
  // which means "follow my accessibility setting" and is a different request
  // from leaving it alone (sections 30 and 105).
  if ('brightness' in input) body.brightness = input.brightness;
  if ('volume' in input) body.volume = input.volume;
  if ('reducedMotion' in input) body.reduced_motion = input.reducedMotion;
  if ('medicationPrivacyLevel' in input) {
    body.medication_privacy_level = input.medicationPrivacyLevel;
  }
  if ('readMedicationsAloud' in input) {
    body.read_medications_aloud = input.readMedicationsAloud;
  }
  if ('readMessagesAloud' in input) body.read_messages_aloud = input.readMessagesAloud;
  if ('readAssistantAloud' in input) {
    body.read_assistant_aloud = input.readAssistantAloud;
  }
  if ('sleepScreenMode' in input) body.sleep_screen_mode = input.sleepScreenMode;
  if ('faceAnimationEnabled' in input) {
    body.face_animation_enabled = input.faceAnimationEnabled;
  }
  if ('familyMessageDisplayEnabled' in input) {
    body.family_message_display_enabled = input.familyMessageDisplayEnabled;
  }

  return parsePreferences(
    await apiRequest<unknown>(`${base(deviceId)}/presentation-preferences`, {
      method: 'PATCH',
      body,
    }),
    'update robot preferences'
  );
}

export async function fetchPresentationHistory(
  deviceId: string
): Promise<Presentation[]> {
  const endpoint = 'robot presentation history';
  const body = object(
    await apiRequest<unknown>(`${base(deviceId)}/presentation-history`),
    endpoint
  );
  return list(body.presentations).map((row) => parsePresentation(row, endpoint));
}

export async function fetchRobotStatus(deviceId: string): Promise<RobotStatus> {
  return parseStatus(
    await apiRequest<unknown>(`${base(deviceId)}/robot-status`),
    'robot status'
  );
}
