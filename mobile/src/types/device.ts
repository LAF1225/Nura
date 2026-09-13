/**
 * A Nura robot linked to the account (PRD 0, section 17; PRD 2, section 34).
 *
 * Identity rules that later PRDs depend on:
 *  - `id` is an internal UUID issued by the backend. It is the stable identity.
 *  - `hardwareId` comes from the device itself and is what BLE discovery
 *    reports; it is never used as the primary key.
 *  - `displayName` is user-facing and editable ("Bedroom Nura"). It must never
 *    be treated as identity, and it is not the user's own name.
 */
export type ConnectionStatus = 'unknown' | 'online' | 'offline';
export type DeviceProvisioningStatus = 'unclaimed' | 'claimed';

export interface Device {
  id: string;
  hardwareId: string;
  displayName: string;
  deviceType: string;
  firmwareVersion: string | null;
  provisioningStatus: DeviceProvisioningStatus;
  /** Derived by the backend from heartbeats; never inferred by the app. */
  connectionStatus: ConnectionStatus;
  lastSeenAt: string | null;
  claimedAt: string | null;
  setupCompletedAt: string | null;
  introducedAt: string | null;
  ownerProfileId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface DeviceStatus {
  deviceId: string;
  connectionStatus: ConnectionStatus;
  lastSeenAt: string | null;
  /** True once the robot has sent a heartbeat with the token from its latest claim. */
  checkedInSinceClaim: boolean;
  onlineThresholdSeconds: number;
  provisioningStatus: DeviceProvisioningStatus;
  firmwareVersion: string | null;
  setupCompleted: boolean;
  introductionPending: boolean;
}

export interface ProvisioningSession {
  id: string;
  hardwareId: string;
  /** Never persisted by the app; handed to the robot over encrypted BLE. */
  provisioningToken: string;
  expiresAt: string;
  deviceApiBaseUrl: string;
}

export type ProvisioningSessionState = 'pending' | 'claimed' | 'expired';

export interface ProvisioningSessionStatus {
  id: string;
  hardwareId: string;
  state: ProvisioningSessionState;
  expiresAt: string;
  deviceId: string | null;
}
