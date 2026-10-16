/**
 * Caregiver, suggestion, messaging and emergency-contact endpoints (PRD 9, §80).
 *
 * Every profile-scoped path is nested under the profile the records belong to,
 * because that is what they belong to -- not the account that is signed in.
 *
 * Responses are parsed rather than cast, the same way the assistant and
 * appointment clients parse. Three distinctions matter enough to be enforced
 * here rather than hoped for.
 *
 * **A missing section stays missing.** PRD 9 section 18 has the backend omit a
 * category the caregiver was not granted, and `optionalList` keeps `null` as
 * `null` instead of defaulting it to `[]`. Collapsing the two would turn "you
 * cannot see this" into "there is nothing here", which is the leak section 18
 * is about -- in the other direction.
 *
 * **An unknown permission key is dropped.** A category added by a later backend
 * is not rendered as a mystery toggle somebody might grant.
 *
 * **Nothing here sends a permission the client made up.** The only permission
 * input is the primary user's own `PATCH`, and its keys are checked against the
 * known set before the request is built. The server is authoritative regardless
 * (section 62); this just means a bug cannot ask it something incoherent.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  CallSession,
  CallState,
  Caregiver,
  CaregiverAdherence,
  CaregiverAppointment,
  CaregiverHealthCounts,
  CaregiverHome,
  CaregiverList,
  CaregiverMedication,
  CaregiverNotificationKey,
  CaregiverReport,
  CaregiverRoutine,
  CaregiverRole,
  CaregiverSafety,
  CaregiverSymptom,
  CareNotificationKey,
  CareSummary,
  CheckInCode,
  EmergencyContact,
  EmergencyContactInput,
  EmergencyContactList,
  FamilyMessage,
  FamilyThread,
  FamilyThreadDetail,
  FamilyThreadList,
  InvitationPreview,
  InviteCreated,
  InviteInput,
  MessageSide,
  MessageType,
  OwnerSuggestion,
  Permission,
  PermissionKey,
  RelationshipStatus,
  Suggestion,
  SuggestionActionType,
  SuggestionCategory,
  SuggestionInput,
  SuggestionList,
  SuggestionStatus,
  SupportedProfile,
} from './types';

export const PERMISSION_KEYS: readonly PermissionKey[] = [
  'medications',
  'appointments',
  'symptoms',
  'reports',
  'safety_alerts',
  'communication',
  'routines',
  'general_health_summary',
];

export const CAREGIVER_ROLES: readonly CaregiverRole[] = [
  'primary_caregiver',
  'family',
  'caregiver',
  'emergency_contact',
  'other',
];

const STATUSES: readonly RelationshipStatus[] = [
  'pending',
  'active',
  'declined',
  'revoked',
  'expired',
];

const SUGGESTION_STATUSES: readonly SuggestionStatus[] = [
  'pending',
  'approved',
  'declined',
  'expired',
  'cancelled',
];

const ACTION_TYPES: readonly SuggestionActionType[] = [
  'change_medication_reminder_time',
  'pause_medication_reminder',
  'resume_medication_reminder',
  'add_appointment',
  'change_appointment_time',
];

const CATEGORIES: readonly SuggestionCategory[] = [
  'medications',
  'appointments',
  'routines',
];

const MESSAGE_SIDES: readonly MessageSide[] = ['primary_user', 'caregiver', 'system'];

const MESSAGE_KINDS = ['text', 'check_in', 'photo', 'system'] as const;

export const CHECK_IN_CODES: readonly CheckInCode[] = [
  'im_okay',
  'not_great',
  'please_call_me',
  'need_help',
  'how_are_you',
  'thinking_of_you',
];

/** Which check-ins each side may send (sections 35 and 36). */
export const CHECK_INS_FROM_USER: readonly CheckInCode[] = [
  'im_okay',
  'not_great',
  'please_call_me',
  'need_help',
];
export const CHECK_INS_FROM_CAREGIVER: readonly CheckInCode[] = [
  'how_are_you',
  'thinking_of_you',
];

const CAREGIVER_NOTIFICATION_KEYS: readonly CaregiverNotificationKey[] = [
  'messages',
  'appointment_updates',
  'suggestion_outcomes',
  'safety_alerts',
];

const CARE_NOTIFICATION_KEYS: readonly CareNotificationKey[] = [
  'caregiver_messages',
  'suggestion_requests',
  'appointment_suggestions',
  'routine_suggestions',
];

/**
 * Each care notification key and the account-settings field it writes.
 *
 * The primary user's preferences live on the account, alongside the check-in
 * reminder PRD 3 added, so this is the one place the two namings meet.
 */
export const CARE_NOTIFICATION_FIELDS: readonly {
  key: CareNotificationKey;
  field:
    | 'notifyCaregiverMessages'
    | 'notifySuggestionRequests'
    | 'notifyAppointmentSuggestions'
    | 'notifyRoutineSuggestions';
}[] = [
  { key: 'caregiver_messages', field: 'notifyCaregiverMessages' },
  { key: 'suggestion_requests', field: 'notifySuggestionRequests' },
  { key: 'appointment_suggestions', field: 'notifyAppointmentSuggestions' },
  { key: 'routine_suggestions', field: 'notifyRoutineSuggestions' },
];

const CALL_STATES: readonly CallState[] = [
  'idle',
  'ringing',
  'connecting',
  'active',
  'ended',
  'failed',
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

function flag(value: unknown): boolean {
  return value === true;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/**
 * A list, or `null` when the key is absent.
 *
 * The one parsing decision in this file that carries a rule: PRD 9 section 18
 * has the backend omit a section the caregiver was not granted, so `null` must
 * survive the trip. Defaulting it to `[]` would make "not allowed to see this"
 * indistinguishable from "nothing here", which is the distinction the caregiver
 * screens are built on.
 */
/** A routine-run status, or null when the routine does not run today. */
function optionalRunStatus(value: unknown): CaregiverRoutine['todayStatus'] {
  const allowed = [
    'scheduled',
    'in_progress',
    'completed',
    'skipped',
    'missed',
    'cancelled',
  ] as const;
  return allowed.includes(value as (typeof allowed)[number])
    ? (value as (typeof allowed)[number])
    : null;
}

function optionalList(value: unknown): unknown[] | null {
  if (value === null || value === undefined) return null;
  return list(value);
}

function permissionKeys(value: unknown): PermissionKey[] {
  return list(value).filter((item): item is PermissionKey =>
    PERMISSION_KEYS.includes(item as PermissionKey)
  );
}

function stringList(value: unknown): string[] {
  return list(value).filter((item): item is string => typeof item === 'string');
}

// --- parsers ---------------------------------------------------------------

function parsePermission(value: unknown, endpoint: string): Permission | null {
  const body = object(value, endpoint);
  const key = body.key;
  // A category a later backend added is dropped rather than rendered as a
  // toggle nobody can explain.
  if (!PERMISSION_KEYS.includes(key as PermissionKey)) return null;
  return {
    key: key as PermissionKey,
    allowed: flag(body.allowed),
    label: text(body.label) ?? (key as string),
    description: text(body.description) ?? '',
    hasData: body.has_data !== false,
  };
}

function parsePermissions(value: unknown, endpoint: string): Permission[] {
  return list(value)
    .map((item) => parsePermission(item, endpoint))
    .filter((item): item is Permission => item !== null);
}

function parseCaregiver(value: unknown, endpoint: string): Caregiver {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    invitedName: text(body.invited_name) ?? 'Caregiver',
    role: oneOf(body.role, CAREGIVER_ROLES, 'other'),
    roleLabel: text(body.role_label) ?? 'Caregiver',
    status: oneOf(body.status, STATUSES, 'pending'),
    inviteEmail: text(body.invite_email),
    invitePhone: text(body.invite_phone),
    inviteExpiresAt: text(body.invite_expires_at),
    acceptedAt: text(body.accepted_at),
    revokedAt: text(body.revoked_at),
    createdAt: text(body.created_at) ?? '',
    permissions: parsePermissions(body.permissions, endpoint),
    grantedCount: count(body.granted_count),
  };
}

function parseSuggestion(value: unknown, endpoint: string): OwnerSuggestion {
  const body = object(value, endpoint);
  const diff = object(body.diff ?? {}, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    actionType: oneOf(body.action_type, ACTION_TYPES, 'pause_medication_reminder'),
    actionLabel: text(body.action_label) ?? 'A change',
    category: oneOf(body.category, CATEGORIES, 'medications'),
    status: oneOf(body.status, SUGGESTION_STATUSES, 'pending'),
    diff: {
      subject: text(diff.subject) ?? '',
      current: text(diff.current),
      proposed: text(diff.proposed) ?? '',
      targetMissing: flag(diff.target_missing),
    },
    caregiverName: text(body.caregiver_name) ?? 'A caregiver',
    createdAt: text(body.created_at) ?? '',
    reviewedAt: text(body.reviewed_at),
    declineNote: text(body.decline_note),
  };
}

function parseMessage(value: unknown, endpoint: string): FamilyMessage {
  const body = object(value, endpoint);
  const code = body.check_in_code;
  return {
    id: requiredString(body, 'id', endpoint),
    messageType: oneOf(body.message_type, MESSAGE_KINDS, 'text'),
    side: oneOf(body.side, MESSAGE_SIDES, 'system'),
    text: text(body.text),
    checkInCode: CHECK_IN_CODES.includes(code as CheckInCode)
      ? (code as CheckInCode)
      : null,
    createdAt: text(body.created_at) ?? '',
    readAt: text(body.read_at),
    clientMessageId: text(body.client_message_id),
  };
}

function parseThread(value: unknown, endpoint: string): FamilyThread {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    relationshipId: text(body.relationship_id) ?? '',
    withName: text(body.with_name) ?? '',
    unread: count(body.unread),
    lastMessage:
      body.last_message === null || body.last_message === undefined
        ? null
        : parseMessage(body.last_message, endpoint),
    lastMessageAt: text(body.last_message_at),
  };
}

function parseContact(value: unknown, endpoint: string): EmergencyContact {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    name: text(body.name) ?? '',
    phone: text(body.phone),
    relationshipLabel: text(body.relationship_label),
    priority: count(body.priority),
    isActive: body.is_active !== false,
    hasAccount: flag(body.has_account),
  };
}

function parseMedication(value: unknown, endpoint: string): CaregiverMedication {
  const body = object(value, endpoint);
  return {
    medicationId: requiredString(body, 'medication_id', endpoint),
    name: text(body.name) ?? '',
    dose: text(body.dose),
    scheduleLabel: text(body.schedule_label),
    remindersPaused: flag(body.reminders_paused),
    supplyLow: flag(body.supply_low),
    remainingDoses: nullableCount(body.remaining_doses),
    scheduleId: text(body.schedule_id),
  };
}

function parseAppointment(value: unknown, endpoint: string): CaregiverAppointment {
  const body = object(value, endpoint);
  return {
    appointmentId: requiredString(body, 'appointment_id', endpoint),
    title: text(body.title) ?? '',
    whenLabel: text(body.when_label) ?? '',
    dayLabel: text(body.day_label) ?? '',
    appointmentType: text(body.appointment_type) ?? 'other',
    locationName: text(body.location_name),
    questionCount: count(body.question_count),
    preparationStatus: text(body.preparation_status) ?? 'not_started',
  };
}

function parseSymptom(value: unknown, endpoint: string): CaregiverSymptom {
  const body = object(value, endpoint);
  return {
    episodeId: requiredString(body, 'episode_id', endpoint),
    name: text(body.name) ?? '',
    status: text(body.status) ?? 'active',
    severity: nullableCount(body.severity),
    changeState: text(body.change_state),
    lastRecordedAt: text(body.last_recorded_at),
  };
}

function parseReport(value: unknown, endpoint: string): CaregiverReport {
  const body = object(value, endpoint);
  return {
    reportId: requiredString(body, 'report_id', endpoint),
    appointmentTitle: text(body.appointment_title) ?? '',
    version: count(body.version),
    generatedAt: text(body.generated_at) ?? '',
    status: text(body.status) ?? 'ready',
  };
}

function parseAdherence(value: unknown, endpoint: string): CaregiverAdherence | null {
  if (value === null || value === undefined) return null;
  const body = object(value, endpoint);
  return {
    fromDate: text(body.from_date) ?? '',
    toDate: text(body.to_date) ?? '',
    taken: count(body.taken),
    skipped: count(body.skipped),
    missed: count(body.missed),
    percent: nullableCount(body.percent),
  };
}

/**
 * One routine as a caregiver sees it (PRD 12, section 16).
 *
 * Narrower than the owner's own routine: no steps, no provenance, no
 * completion rows. A caregiver is told what the routine is, when it runs and
 * how today is going -- a tick-by-tick log of somebody's morning is the
 * surveillance experience PRD 9 section 2 rules out.
 */
function parseCaregiverRoutine(value: unknown, endpoint: string): CaregiverRoutine {
  const row = object(value, endpoint);
  return {
    routineId: requiredString(row, 'routine_id', endpoint),
    title: requiredString(row, 'title', endpoint),
    scheduleLabel: text(row.schedule_label) ?? '',
    stepCount: count(row.step_count),
    paused: row.paused === true,
    todayStatus: optionalRunStatus(row.today_status),
    todayDone: typeof row.today_done === 'number' ? row.today_done : null,
    todayTotal: typeof row.today_total === 'number' ? row.today_total : null,
    todayProgressLabel: text(row.today_progress_label),
  };
}

function parseHealthCounts(
  value: unknown,
  endpoint: string
): CaregiverHealthCounts | null {
  if (value === null || value === undefined) return null;
  const body = object(value, endpoint);
  return {
    activeConditions: count(body.active_conditions),
    activeMedications: count(body.active_medications),
    activeSymptoms: count(body.active_symptoms),
    allergies: count(body.allergies),
  };
}

function parseSupportedProfile(value: unknown, endpoint: string): SupportedProfile {
  const body = object(value, endpoint);
  const notifications = object(body.notifications ?? {}, endpoint);
  return {
    relationshipId: requiredString(body, 'relationship_id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    profileName: text(body.profile_name) ?? '',
    role: oneOf(body.role, CAREGIVER_ROLES, 'other'),
    roleLabel: text(body.role_label) ?? 'Caregiver',
    granted: permissionKeys(body.granted),
    notifications: Object.fromEntries(
      CAREGIVER_NOTIFICATION_KEYS.map((key) => [key, notifications[key] === true])
    ) as Record<CaregiverNotificationKey, boolean>,
    acceptedAt: text(body.accepted_at),
  };
}

// --- the primary user's caregiver list --------------------------------------

const base = (profileId: string) => `/api/v1/profiles/${profileId}`;

export async function fetchCaregivers(
  profileId: string,
  includeInactive = false
): Promise<CaregiverList> {
  const endpoint = 'caregivers';
  const query = includeInactive ? '?include_inactive=true' : '';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/caregivers${query}`),
    endpoint
  );
  return {
    caregivers: list(body.caregivers).map((item) => parseCaregiver(item, endpoint)),
    hasAny: flag(body.has_any),
  };
}

export async function createInvitation(
  profileId: string,
  input: InviteInput
): Promise<InviteCreated> {
  const endpoint = 'caregiver invitation';
  // Only known keys are sent. The server would refuse an unknown one anyway;
  // this means a bug cannot ask it something incoherent.
  const permissions: Record<string, boolean> = {};
  for (const key of PERMISSION_KEYS) {
    if (input.permissions[key]) permissions[key] = true;
  }
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/caregivers/invitations`, {
      method: 'POST',
      body: {
        invited_name: input.invitedName,
        role: input.role,
        email: input.email ?? null,
        phone: input.phone ?? null,
        permissions,
      },
    }),
    endpoint
  );
  return {
    caregiver: parseCaregiver(body.caregiver, endpoint),
    token: requiredString(body, 'token', endpoint),
    expiresAt: text(body.expires_at) ?? '',
    delivery: 'share_manually',
  };
}

export async function updateCaregiverRole(
  profileId: string,
  relationshipId: string,
  role: CaregiverRole
): Promise<Caregiver> {
  return parseCaregiver(
    await apiRequest<unknown>(`${base(profileId)}/caregivers/${relationshipId}`, {
      method: 'PATCH',
      body: { role },
    }),
    'caregiver role'
  );
}

export async function updateCaregiverPermissions(
  profileId: string,
  relationshipId: string,
  permissions: Partial<Record<PermissionKey, boolean>>
): Promise<Caregiver> {
  const sent: Record<string, boolean> = {};
  for (const key of PERMISSION_KEYS) {
    const value = permissions[key];
    if (typeof value === 'boolean') sent[key] = value;
  }
  return parseCaregiver(
    await apiRequest<unknown>(
      `${base(profileId)}/caregivers/${relationshipId}/permissions`,
      { method: 'PATCH', body: { permissions: sent } }
    ),
    'caregiver permissions'
  );
}

export async function revokeCaregiver(
  profileId: string,
  relationshipId: string
): Promise<void> {
  await apiRequest<unknown>(`${base(profileId)}/caregivers/${relationshipId}`, {
    method: 'DELETE',
  });
}

export async function fetchCareSummary(profileId: string): Promise<CareSummary> {
  const endpoint = 'care summary';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/care-summary`),
    endpoint
  );
  return {
    caregiverCount: count(body.caregiver_count),
    pendingInvitationCount: count(body.pending_invitation_count),
    pendingSuggestionCount: count(body.pending_suggestion_count),
    unreadMessageCount: count(body.unread_message_count),
    emergencyContactCount: count(body.emergency_contact_count),
  };
}

/**
 * Every permission category with its label and description.
 *
 * Fetched rather than hard-coded here, so the invitation form shows the same
 * wording as the permission screen and the acceptance screen -- section 15's
 * rule about vague or inconsistent labels is only kept if there is one source
 * for them, and that source is the server.
 */
export async function fetchPermissionCatalogue(): Promise<Permission[]> {
  const endpoint = 'permission catalogue';
  const body = await apiRequest<unknown>('/api/v1/caregiver-permissions');
  return parsePermissions(body, endpoint);
}

// --- invitations (the caregiver's side) -------------------------------------

export async function fetchInvitation(token: string): Promise<InvitationPreview> {
  const endpoint = 'invitation';
  const body = object(
    await apiRequest<unknown>(
      `/api/v1/caregiver-invitations/${encodeURIComponent(token)}`
    ),
    endpoint
  );
  return {
    invitedName: text(body.invited_name) ?? '',
    profileName: text(body.profile_name) ?? '',
    role: oneOf(body.role, CAREGIVER_ROLES, 'other'),
    roleLabel: text(body.role_label) ?? 'Caregiver',
    permissions: parsePermissions(body.permissions, endpoint),
    willAccess: stringList(body.will_access),
    willNotAccess: stringList(body.will_not_access),
    expiresAt: text(body.expires_at) ?? '',
  };
}

export async function acceptInvitation(token: string): Promise<SupportedProfile> {
  return parseSupportedProfile(
    await apiRequest<unknown>(
      `/api/v1/caregiver-invitations/${encodeURIComponent(token)}/accept`,
      { method: 'POST' }
    ),
    'invitation accept'
  );
}

export async function declineInvitation(token: string): Promise<void> {
  await apiRequest<unknown>(
    `/api/v1/caregiver-invitations/${encodeURIComponent(token)}/decline`,
    { method: 'POST' }
  );
}

export async function fetchSupportedProfiles(): Promise<SupportedProfile[]> {
  const endpoint = 'supported profiles';
  const body = object(await apiRequest<unknown>('/api/v1/caregiver/profiles'), endpoint);
  return list(body.profiles).map((item) => parseSupportedProfile(item, endpoint));
}

// --- the caregiver's home ---------------------------------------------------

export async function fetchCaregiverHome(
  profileId: string,
  localDate: string
): Promise<CaregiverHome> {
  const endpoint = 'caregiver home';
  const body = object(
    await apiRequest<unknown>(
      `${base(profileId)}/care/home?local_date=${encodeURIComponent(localDate)}`
    ),
    endpoint
  );
  const medications = optionalList(body.medications);
  const appointments = optionalList(body.appointments);
  const symptoms = optionalList(body.symptoms);
  const reports = optionalList(body.reports);
  const routines = optionalList(body.routines);
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    profileName: text(body.profile_name) ?? '',
    role: oneOf(body.role, CAREGIVER_ROLES, 'other'),
    roleLabel: text(body.role_label) ?? 'Caregiver',
    granted: permissionKeys(body.granted),
    grantedWithoutData: permissionKeys(body.granted_without_data),
    medications:
      medications === null
        ? null
        : medications.map((item) => parseMedication(item, endpoint)),
    adherence: parseAdherence(body.adherence, endpoint),
    dosesRemainingToday: nullableCount(body.doses_remaining_today),
    dosesOverdue: nullableCount(body.doses_overdue),
    appointments:
      appointments === null
        ? null
        : appointments.map((item) => parseAppointment(item, endpoint)),
    symptoms:
      symptoms === null ? null : symptoms.map((item) => parseSymptom(item, endpoint)),
    reports: reports === null ? null : reports.map((item) => parseReport(item, endpoint)),
    // PRD 12, section 16. Null when `routines` was not granted, which is a
    // different fact from an empty list (PRD 9, section 18).
    routines:
      routines === null
        ? null
        : routines.map((item) => parseCaregiverRoutine(item, endpoint)),
    healthCounts: parseHealthCounts(body.health_counts, endpoint),
    unreadMessages: nullableCount(body.unread_messages),
    // Absent, not empty, when `safety_alerts` was not granted (PRD 10, s50).
    safety:
      body.safety === null || body.safety === undefined
        ? null
        : parseCaregiverSafety(body.safety, endpoint),
    pendingSuggestions: count(body.pending_suggestions),
    callingAvailable: flag(body.calling_available),
  };
}

function parseCaregiverSafety(value: unknown, endpoint: string): CaregiverSafety {
  const body = object(value, endpoint);
  return {
    unreadCount: count(body.unread_count),
    latestAlertId: text(body.latest_alert_id),
    latestEventLabel: text(body.latest_event_label),
    latestAt: text(body.latest_at),
    latestAcknowledged: flag(body.latest_acknowledged),
  };
}

export async function updateCaregiverNotifications(
  profileId: string,
  notifications: Partial<Record<CaregiverNotificationKey, boolean>>
): Promise<SupportedProfile> {
  const sent: Record<string, boolean> = {};
  for (const key of CAREGIVER_NOTIFICATION_KEYS) {
    const value = notifications[key];
    if (typeof value === 'boolean') sent[key] = value;
  }
  return parseSupportedProfile(
    await apiRequest<unknown>(`${base(profileId)}/care/notifications`, {
      method: 'PATCH',
      body: { notifications: sent },
    }),
    'caregiver notifications'
  );
}

// --- suggestions ------------------------------------------------------------

export async function fetchSuggestions(
  profileId: string,
  openOnly = false
): Promise<SuggestionList> {
  const endpoint = 'caregiver suggestions';
  const query = openOnly ? '?open_only=true' : '';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/caregiver-suggestions${query}`),
    endpoint
  );
  return {
    suggestions: list(body.suggestions).map((item) => parseSuggestion(item, endpoint)),
    pendingCount: count(body.pending_count),
  };
}

export async function createSuggestion(
  profileId: string,
  input: SuggestionInput
): Promise<Suggestion> {
  return parseSuggestion(
    await apiRequest<unknown>(`${base(profileId)}/caregiver-suggestions`, {
      method: 'POST',
      body: {
        action_type: input.actionType,
        target_resource_id: input.targetResourceId ?? null,
        payload: input.payload ?? {},
        client_suggestion_id: input.clientSuggestionId ?? null,
      },
    }),
    'caregiver suggestion'
  );
}

export async function approveSuggestion(
  profileId: string,
  suggestionId: string
): Promise<OwnerSuggestion> {
  return parseSuggestion(
    await apiRequest<unknown>(
      `${base(profileId)}/caregiver-suggestions/${suggestionId}/approve`,
      { method: 'POST' }
    ),
    'suggestion approve'
  );
}

export async function declineSuggestion(
  profileId: string,
  suggestionId: string,
  note?: string | null
): Promise<OwnerSuggestion> {
  return parseSuggestion(
    await apiRequest<unknown>(
      `${base(profileId)}/caregiver-suggestions/${suggestionId}/decline`,
      { method: 'POST', body: { note: note && note.length > 0 ? note : null } }
    ),
    'suggestion decline'
  );
}

export async function cancelSuggestion(
  profileId: string,
  suggestionId: string
): Promise<Suggestion> {
  return parseSuggestion(
    await apiRequest<unknown>(
      `${base(profileId)}/caregiver-suggestions/${suggestionId}/cancel`,
      { method: 'POST' }
    ),
    'suggestion cancel'
  );
}

// --- family messaging -------------------------------------------------------

export async function fetchThreads(profileId: string): Promise<FamilyThreadList> {
  const endpoint = 'family threads';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/family/threads`),
    endpoint
  );
  return { threads: list(body.threads).map((item) => parseThread(item, endpoint)) };
}

export async function createThread(
  profileId: string,
  relationshipId: string
): Promise<FamilyThread> {
  return parseThread(
    await apiRequest<unknown>(`${base(profileId)}/family/threads`, {
      method: 'POST',
      body: { relationship_id: relationshipId },
    }),
    'family thread'
  );
}

export async function fetchThread(
  profileId: string,
  threadId: string
): Promise<FamilyThreadDetail> {
  const endpoint = 'family thread';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/family/threads/${threadId}/messages`),
    endpoint
  );
  return {
    thread: parseThread(body.thread, endpoint),
    messages: list(body.messages).map((item) => parseMessage(item, endpoint)),
  };
}

export async function sendFamilyMessage(
  profileId: string,
  threadId: string,
  input: {
    messageType?: MessageType;
    text?: string | null;
    checkInCode?: CheckInCode | null;
    clientMessageId?: string | null;
  }
): Promise<FamilyMessage> {
  return parseMessage(
    await apiRequest<unknown>(`${base(profileId)}/family/threads/${threadId}/messages`, {
      method: 'POST',
      body: {
        message_type: input.messageType ?? 'text',
        text: input.text ?? null,
        check_in_code: input.checkInCode ?? null,
        client_message_id: input.clientMessageId ?? null,
      },
    }),
    'family message'
  );
}

// --- emergency contacts -----------------------------------------------------

export async function fetchEmergencyContacts(
  profileId: string
): Promise<EmergencyContactList> {
  const endpoint = 'emergency contacts';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/emergency-contacts`),
    endpoint
  );
  return { contacts: list(body.contacts).map((item) => parseContact(item, endpoint)) };
}

export async function createEmergencyContact(
  profileId: string,
  input: EmergencyContactInput
): Promise<EmergencyContact> {
  return parseContact(
    await apiRequest<unknown>(`${base(profileId)}/emergency-contacts`, {
      method: 'POST',
      body: {
        name: input.name,
        phone: input.phone ?? null,
        relationship_label: input.relationshipLabel ?? null,
        is_active: input.isActive ?? true,
      },
    }),
    'emergency contact'
  );
}

export async function updateEmergencyContact(
  profileId: string,
  contactId: string,
  input: Partial<EmergencyContactInput>
): Promise<EmergencyContact> {
  const body: Record<string, unknown> = {};
  if (input.name !== undefined) body.name = input.name;
  if (input.phone !== undefined) body.phone = input.phone;
  if (input.relationshipLabel !== undefined) {
    body.relationship_label = input.relationshipLabel;
  }
  if (input.isActive !== undefined) body.is_active = input.isActive;
  return parseContact(
    await apiRequest<unknown>(`${base(profileId)}/emergency-contacts/${contactId}`, {
      method: 'PATCH',
      body,
    }),
    'emergency contact'
  );
}

export async function deleteEmergencyContact(
  profileId: string,
  contactId: string
): Promise<void> {
  await apiRequest<unknown>(`${base(profileId)}/emergency-contacts/${contactId}`, {
    method: 'DELETE',
  });
}

export async function reorderEmergencyContacts(
  profileId: string,
  order: string[]
): Promise<EmergencyContactList> {
  const endpoint = 'emergency contact order';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/emergency-contacts/reorder`, {
      method: 'POST',
      body: { order },
    }),
    endpoint
  );
  return { contacts: list(body.contacts).map((item) => parseContact(item, endpoint)) };
}

// --- calling ----------------------------------------------------------------

/**
 * Asks for an audio call (section 38).
 *
 * Refused by every deployment today with `calling_not_configured`, because
 * section 38 forbids simulating a successful call. Kept here so the one place
 * that would change when a provider arrives is `calls.ts` on the server.
 */
export async function startCall(
  profileId: string,
  relationshipId: string
): Promise<CallSession> {
  const endpoint = 'call';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/family/calls`, {
      method: 'POST',
      body: { relationship_id: relationshipId },
    }),
    endpoint
  );
  return {
    callId: requiredString(body, 'call_id', endpoint),
    state: oneOf(body.state, CALL_STATES, 'failed'),
    credential: text(body.credential),
    expiresAt: text(body.expires_at),
  };
}

export { CARE_NOTIFICATION_KEYS, CAREGIVER_NOTIFICATION_KEYS };
