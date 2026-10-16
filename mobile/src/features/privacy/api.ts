/**
 * The privacy endpoints (PRD 13, sections 43, 44 and 45).
 *
 * Parsed field by field like every other client here. Three things are worth
 * reading.
 *
 * **`downloadable` comes from the server and is never recomputed.** The expiry
 * is a server rule -- PRD 11's "applied on every read" shape -- and a client
 * comparing timestamps itself would be a second implementation that disagrees
 * on a clock skew.
 *
 * **The confirmation phrase is echoed, never composed.** `requestDeletion`
 * returns what `confirmDeletion` must send, and the screen passes it straight
 * back. A client that built the string itself would still work and would be
 * one typo away from a confirmation step that cannot be satisfied.
 *
 * **No sentence here is written in the app.** Every warning, note and
 * limitation is the server's prose, for the reason PRD 12 gave for the alarm
 * limitation: a truthfulness sentence with two sources eventually has two
 * meanings.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  CapabilityLine,
  CaregiverAccess,
  ConversationsDeleted,
  DataExport,
  DeletionInventory,
  DeletionResult,
  ExportList,
  ExportStatus,
  PrivacySummary,
} from './types';

const EXPORT_STATUSES: readonly ExportStatus[] = [
  'requested',
  'generating',
  'ready',
  'failed',
  'expired',
];

function base(profileId: string): string {
  return `/api/v1/profiles/${profileId}/privacy`;
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

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function flag(value: unknown): boolean {
  return value === true;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function strings(value: unknown): string[] {
  return list(value).filter((entry): entry is string => typeof entry === 'string');
}

// --- capability rows ---------------------------------------------------------

function parseCapability(value: unknown, endpoint: string): CapabilityLine {
  const body = object(value, endpoint);
  return {
    key: requiredString(body, 'key', endpoint),
    label: requiredString(body, 'label', endpoint),
    state: requiredString(body, 'state', endpoint),
    stateLabel: requiredString(body, 'state_label', endpoint),
  };
}

function parseCaregiver(value: unknown, endpoint: string): CaregiverAccess {
  const body = object(value, endpoint);
  return {
    relationshipId: requiredString(body, 'relationship_id', endpoint),
    name: requiredString(body, 'name', endpoint),
    role: requiredString(body, 'role', endpoint),
    granted: strings(body.granted),
    acceptedAt: text(body.accepted_at),
  };
}

// --- exports -----------------------------------------------------------------

export function parseExport(value: unknown, endpoint = 'export'): DataExport {
  const body = object(value, endpoint);
  const status = body.status;
  return {
    id: requiredString(body, 'id', endpoint),
    // An unrecognised status reads as `failed`, which is the quietest wrong
    // answer available: it offers nothing to download. Falling back to `ready`
    // would offer a download that cannot work.
    status: EXPORT_STATUSES.includes(status as ExportStatus)
      ? (status as ExportStatus)
      : 'failed',
    statusLabel: requiredString(body, 'status_label', endpoint),
    requestedAt: requiredString(body, 'requested_at', endpoint),
    generatedAt: text(body.generated_at),
    expiresAt: text(body.expires_at),
    byteSize: typeof body.byte_size === 'number' ? body.byte_size : null,
    fileCount: count(body.file_count),
    schemaVersion: count(body.schema_version),
    includedCategories: strings(body.included_categories),
    excludedCategories: strings(body.excluded_categories),
    failureReason: text(body.failure_reason),
    // The server's answer, with the expiry already compared.
    downloadable: flag(body.downloadable),
  };
}

export function parseExportList(value: unknown): ExportList {
  const endpoint = 'exports';
  const body = object(value, endpoint);
  return {
    exports: list(body.exports).map((entry) => parseExport(entry, endpoint)),
    note: requiredString(body, 'note', endpoint),
    privacyNote: requiredString(body, 'privacy_note', endpoint),
    // Section 18's claim, and the parser requires it: a screen that offered an
    // export without saying it holds no tokens would be dropping the one
    // sentence that makes the offer safe to accept.
    secretsNote: requiredString(body, 'secrets_note', endpoint),
    sections: strings(body.sections),
  };
}

export async function fetchExports(profileId: string): Promise<ExportList> {
  return parseExportList(await apiRequest(`${base(profileId)}/export`));
}

export async function createExport(profileId: string): Promise<DataExport> {
  return parseExport(
    await apiRequest(`${base(profileId)}/export`, { method: 'POST' }),
    'export'
  );
}

export async function deleteExport(profileId: string, exportId: string): Promise<void> {
  await apiRequest(`${base(profileId)}/export/${exportId}`, { method: 'DELETE' });
}

/** Where the archive is read from. An authenticated route, never a signed URL. */
export function exportContentPath(profileId: string, exportId: string): string {
  return `${base(profileId)}/export/${exportId}/content`;
}

// --- the hub -----------------------------------------------------------------

export function parsePrivacySummary(value: unknown): PrivacySummary {
  const endpoint = 'privacy summary';
  const body = object(value, endpoint);
  const latest = body.latest_export;
  return {
    profileId: requiredString(body, 'profile_id', endpoint),

    assistantMode: requiredString(body, 'assistant_mode', endpoint),
    privacyMode: flag(body.privacy_mode),
    privacyModeNote: requiredString(body, 'privacy_mode_note', endpoint),
    privacyModeLimit: requiredString(body, 'privacy_mode_limit', endpoint),

    microphoneNote: requiredString(body, 'microphone_note', endpoint),
    cameraNote: requiredString(body, 'camera_note', endpoint),
    photoPermissionNote: requiredString(body, 'photo_permission_note', endpoint),
    robotInputCapabilities: list(body.robot_input_capabilities).map((entry) =>
      parseCapability(entry, endpoint)
    ),

    memoryCount: count(body.memory_count),
    activeMemoryCount: count(body.active_memory_count),
    conversationCount: count(body.conversation_count),

    caregivers: list(body.caregivers).map((entry) => parseCaregiver(entry, endpoint)),

    safetyMonitoringActive: flag(body.safety_monitoring_active),
    safetyCapabilities: list(body.safety_capabilities).map((entry) =>
      parseCapability(entry, endpoint)
    ),

    robotLinked: flag(body.robot_linked),
    robotCapabilities: list(body.robot_capabilities).map((entry) =>
      parseCapability(entry, endpoint)
    ),
    robotPreviews: list(body.robot_previews)
      .map((entry) => strings(entry))
      .filter((pair): pair is [string, string] => pair.length === 2)
      .map((pair) => [pair[0], pair[1]] as [string, string]),

    externalCapabilities: list(body.external_capabilities).map((entry) =>
      parseCapability(entry, endpoint)
    ),

    latestExport: latest === null || latest === undefined ? null : parseExport(latest),
    exportNote: requiredString(body, 'export_note', endpoint),
    exportPrivacyNote: requiredString(body, 'export_privacy_note', endpoint),

    deletionWarning: requiredString(body, 'deletion_warning', endpoint),
    deletionKeeps: requiredString(body, 'deletion_keeps', endpoint),
    // Section 44's documented limitation. Required, for the same reason the
    // alarm limitation is: it is the sentence somebody needs at the moment
    // they are about to delete everything.
    deletionReauthLimitation: requiredString(
      body,
      'deletion_reauth_limitation',
      endpoint
    ),

    dataCategories: strings(body.data_categories),
    securityStatements: strings(body.security_statements),
    buildHonestyNote: requiredString(body, 'build_honesty_note', endpoint),
  };
}

export async function fetchPrivacySummary(profileId: string): Promise<PrivacySummary> {
  return parsePrivacySummary(await apiRequest(`${base(profileId)}/summary`));
}

// --- conversations -----------------------------------------------------------

export async function deleteAllConversations(
  profileId: string
): Promise<ConversationsDeleted> {
  const endpoint = 'delete all conversations';
  const body = object(
    await apiRequest(`${base(profileId)}/conversations/delete-all`, {
      method: 'POST',
    }),
    endpoint
  );
  return {
    deleted: count(body.deleted),
    note: requiredString(body, 'note', endpoint),
  };
}

// --- deletion ----------------------------------------------------------------

export function parseDeletionInventory(value: unknown): DeletionInventory {
  const endpoint = 'delete request';
  const body = object(value, endpoint);
  const rows: Record<string, number> = {};
  const raw = body.rows;
  if (raw !== null && typeof raw === 'object' && !Array.isArray(raw)) {
    for (const [table, value_] of Object.entries(raw as Record<string, unknown>)) {
      rows[table] = count(value_);
    }
  }
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    profileName: requiredString(body, 'profile_name', endpoint),
    rows,
    rowTotal: count(body.row_total),
    fileCount: count(body.file_count),
    caregiverCount: count(body.caregiver_count),
    deviceCount: count(body.device_count),
    otherProfileCount: count(body.other_profile_count),

    title: requiredString(body, 'title', endpoint),
    warning: requiredString(body, 'warning', endpoint),
    keeps: requiredString(body, 'keeps', endpoint),
    reauthLimitation: requiredString(body, 'reauth_limitation', endpoint),
    confirmPrompt: requiredString(body, 'confirm_prompt', endpoint),
    confirmationPhrase: requiredString(body, 'confirmation_phrase', endpoint),
  };
}

export async function requestDeletion(profileId: string): Promise<DeletionInventory> {
  return parseDeletionInventory(
    await apiRequest(`${base(profileId)}/delete-request`, { method: 'POST' })
  );
}

export function parseDeletionResult(value: unknown): DeletionResult {
  const endpoint = 'delete confirm';
  const body = object(value, endpoint);
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    rowsDeleted: count(body.rows_deleted),
    filesDeleted: count(body.files_deleted),
    filesMissing: count(body.files_missing),
    caregiversRevoked: count(body.caregivers_revoked),
    devicesUnlinked: count(body.devices_unlinked),
    completedAt: requiredString(body, 'completed_at', endpoint),
    otherProfilesRemaining: count(body.other_profiles_remaining),
  };
}

export async function confirmDeletion(
  profileId: string,
  confirmationPhrase: string
): Promise<DeletionResult> {
  return parseDeletionResult(
    await apiRequest(`${base(profileId)}/delete-confirm`, {
      method: 'POST',
      // Both halves, always. The server requires each one and neither has a
      // default, so an empty body cannot delete anything.
      body: { confirmation_phrase: confirmationPhrase, acknowledged: true },
    })
  );
}
