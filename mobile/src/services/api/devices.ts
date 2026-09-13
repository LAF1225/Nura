/**
 * Device and provisioning endpoints (PRD 2, section 33).
 *
 * Wire format is snake_case; the app sees camelCase. Responses are checked
 * field by field so a malformed body becomes an `ApiError`, never a screen
 * rendering `undefined`.
 */
import type {
  ConnectionStatus,
  Device,
  DeviceProvisioningStatus,
  DeviceStatus,
  ProvisioningSession,
  ProvisioningSessionState,
  ProvisioningSessionStatus,
} from '../../types/device';
import { apiRequest } from './client';
import { ApiError } from './errors';

function record(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(body: Record<string, unknown>, key: string, endpoint: string): string {
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

const CONNECTION_STATUSES: readonly ConnectionStatus[] = ['unknown', 'online', 'offline'];
const PROVISIONING_STATUSES: readonly DeviceProvisioningStatus[] = ['unclaimed', 'claimed'];
const SESSION_STATES: readonly ProvisioningSessionState[] = ['pending', 'claimed', 'expired'];

export function parseDevice(raw: unknown): Device {
  const endpoint = '/api/v1/devices';
  const body = record(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    hardwareId: requiredString(body, 'hardware_id', endpoint),
    displayName: requiredString(body, 'display_name', endpoint),
    deviceType: optionalString(body.device_type) ?? 'xiao-esp32-s3',
    firmwareVersion: optionalString(body.firmware_version),
    provisioningStatus: oneOf(body.provisioning_status, PROVISIONING_STATUSES, 'claimed'),
    // An unrecognised value must never read as "online".
    connectionStatus: oneOf(body.connection_status, CONNECTION_STATUSES, 'unknown'),
    lastSeenAt: optionalString(body.last_seen_at),
    claimedAt: optionalString(body.claimed_at),
    setupCompletedAt: optionalString(body.setup_completed_at),
    introducedAt: optionalString(body.introduced_at),
    ownerProfileId: optionalString(body.owner_profile_id),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

export function parseDeviceStatus(raw: unknown): DeviceStatus {
  const endpoint = '/api/v1/devices/{id}/status';
  const body = record(raw, endpoint);
  return {
    deviceId: requiredString(body, 'device_id', endpoint),
    connectionStatus: oneOf(body.connection_status, CONNECTION_STATUSES, 'unknown'),
    lastSeenAt: optionalString(body.last_seen_at),
    checkedInSinceClaim: body.checked_in_since_claim === true,
    onlineThresholdSeconds:
      typeof body.online_threshold_seconds === 'number' ? body.online_threshold_seconds : 90,
    provisioningStatus: oneOf(body.provisioning_status, PROVISIONING_STATUSES, 'claimed'),
    firmwareVersion: optionalString(body.firmware_version),
    setupCompleted: body.setup_completed === true,
    introductionPending: body.introduction_pending === true,
  };
}

export async function fetchDevices(signal?: AbortSignal): Promise<Device[]> {
  const raw = await apiRequest<unknown>('/api/v1/devices', { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', 'Unexpected response shape from /api/v1/devices.');
  }
  return raw.map(parseDevice);
}

export async function fetchDevice(id: string, signal?: AbortSignal): Promise<Device> {
  return parseDevice(
    await apiRequest<unknown>(`/api/v1/devices/${encodeURIComponent(id)}`, { signal })
  );
}

export async function fetchDeviceStatus(
  id: string,
  signal?: AbortSignal
): Promise<DeviceStatus> {
  return parseDeviceStatus(
    await apiRequest<unknown>(`/api/v1/devices/${encodeURIComponent(id)}/status`, { signal })
  );
}

export async function renameDevice(id: string, displayName: string): Promise<Device> {
  return parseDevice(
    await apiRequest<unknown>(`/api/v1/devices/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: { display_name: displayName },
    })
  );
}

export async function completeDeviceSetup(id: string): Promise<Device> {
  return parseDevice(
    await apiRequest<unknown>(`/api/v1/devices/${encodeURIComponent(id)}/complete-setup`, {
      method: 'POST',
    })
  );
}

export async function createProvisioningSession(
  hardwareId: string
): Promise<ProvisioningSession> {
  const endpoint = '/api/v1/devices/provisioning-sessions';
  const body = record(
    await apiRequest<unknown>(endpoint, {
      method: 'POST',
      body: { hardware_id: hardwareId },
    }),
    endpoint
  );
  return {
    id: requiredString(body, 'id', endpoint),
    hardwareId: requiredString(body, 'hardware_id', endpoint),
    provisioningToken: requiredString(body, 'provisioning_token', endpoint),
    expiresAt: requiredString(body, 'expires_at', endpoint),
    deviceApiBaseUrl: requiredString(body, 'device_api_base_url', endpoint),
  };
}

export async function fetchProvisioningSession(
  id: string,
  signal?: AbortSignal
): Promise<ProvisioningSessionStatus> {
  const endpoint = '/api/v1/devices/provisioning-sessions/{id}';
  const body = record(
    await apiRequest<unknown>(
      `/api/v1/devices/provisioning-sessions/${encodeURIComponent(id)}`,
      { signal }
    ),
    endpoint
  );
  return {
    id: requiredString(body, 'id', endpoint),
    hardwareId: requiredString(body, 'hardware_id', endpoint),
    state: oneOf(body.state, SESSION_STATES, 'expired'),
    expiresAt: requiredString(body, 'expires_at', endpoint),
    deviceId: optionalString(body.device_id),
  };
}
