/**
 * Nura provisioning protocol, version 1 -- app side (PRD 2, sections 12-13).
 *
 * The contract is docs/device/provisioning-protocol.md. The firmware defines
 * the same values in firmware/xiao_esp32s3/src/protocol.h, and
 * tests/provisioningProtocol.test.ts fails if the two disagree.
 *
 * Everything here is pure: encoding and decoding bytes, no Bluetooth calls, so
 * it is all unit-testable.
 */
import { utf8Decode } from './bytes';

export const PROTOCOL_VERSION = 1;

export const UUIDS = {
  service: '3326ea00-822c-4b86-884f-74b2d9c77b2f',
  deviceInfo: '3326ea01-822c-4b86-884f-74b2d9c77b2f',
  pairing: '3326ea02-822c-4b86-884f-74b2d9c77b2f',
  wifiConfig: '3326ea03-822c-4b86-884f-74b2d9c77b2f',
  command: '3326ea04-822c-4b86-884f-74b2d9c77b2f',
  status: '3326ea05-822c-4b86-884f-74b2d9c77b2f',
} as const;

export const BLE_NAME_PREFIX = 'Nura-';
export const HARDWARE_ID_PATTERN = /^NURA-[0-9A-F]{12}$/;

export const PairingMessage = {
  PAKE_START: 0x01,
  PAKE_RESPONSE: 0x02,
  PAKE_CONFIRM: 0x03,
  PAIRING_RESULT: 0x04,
} as const;

export const PairingResult = {
  VERIFIED: 0x00,
  WRONG_CODE: 0x01,
  CODE_EXPIRED: 0x02,
  TOO_MANY_ATTEMPTS: 0x03,
  MALFORMED: 0x04,
  NOT_PAIRING: 0x05,
} as const;
export type PairingResultName = keyof typeof PairingResult;

export const Command = {
  CONNECT_WIFI: 0x01,
  RETRY_WIFI: 0x02,
  CLEAR_WIFI: 0x03,
  FINISH: 0x04,
} as const;
export type CommandName = keyof typeof Command;

export const ProvisioningState = {
  WAITING: 0x00,
  VERIFIED: 0x01,
  RECEIVED_CREDENTIALS: 0x02,
  WIFI_CONNECTING: 0x03,
  WIFI_CONNECTED: 0x04,
  REGISTERING: 0x05,
  REGISTERED: 0x06,
  FAILED: 0x07,
} as const;
export type ProvisioningStateName = keyof typeof ProvisioningState;

export const ProvisioningError = {
  NONE: 0x00,
  WIFI_AUTH_FAILED: 0x01,
  WIFI_NOT_FOUND: 0x02,
  WIFI_TIMEOUT: 0x03,
  WIFI_UNSUPPORTED: 0x04,
  BACKEND_UNREACHABLE: 0x05,
  REGISTRATION_REJECTED: 0x06,
  ALREADY_CLAIMED: 0x07,
  IDENTITY_MISMATCH: 0x08,
  INVALID_PAYLOAD: 0x09,
  NOT_VERIFIED: 0x0a,
  NO_CREDENTIALS: 0x0b,
  UNKNOWN_ERROR: 0xff,
} as const;
export type ProvisioningErrorName = keyof typeof ProvisioningError;

export const PAKE_IDENTITY_APP = 'nura-app';
export const PAKE_AAD = 'nura-provisioning-v1';
export const PAKE_W_DOMAIN = 'nura-pake-w-v1';
export const WIFI_KEY_INFO = 'nura wifi config v1';

export const POINT_LENGTH = 65;
export const MAC_LENGTH = 32;
export const NONCE_LENGTH = 12;
export const TAG_LENGTH = 16;
export const WIFI_KEY_LENGTH = 16;
export const WIFI_CONFIG_VERSION = 1;
export const MAX_ATTRIBUTE_LENGTH = 512;

export const CODE_DIGITS = 6;
export const CODE_TTL_MS = 120_000;
export const MAX_FAILED_ATTEMPTS_PER_CONNECTION = 3;

export const SSID_MAX_BYTES = 32;
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 63;

/** App-side timings (docs section 8). */
export const SCAN_DURATION_SECONDS = 12;
export const CONNECT_TIMEOUT_MS = 10_000;
export const REQUESTED_MTU = 247;
export const ONLINE_POLL_INTERVAL_MS = 2_000;
export const ONLINE_WAIT_TIMEOUT_MS = 90_000;
/** How long to wait for the robot to answer a PAIRING or STATUS exchange. */
export const RESPONSE_TIMEOUT_MS = 15_000;

function nameFor<T extends Record<string, number>>(table: T, value: number): keyof T | null {
  const entry = Object.entries(table).find(([, code]) => code === value);
  return entry ? (entry[0] as keyof T) : null;
}

export function sameUuid(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

// --- DEVICE_INFO -------------------------------------------------------------

export interface DeviceInfo {
  protocol: number;
  hardwareId: string;
  model: string;
  firmwareVersion: string;
  provisioned: boolean;
  registered: boolean;
}

export class ProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ProtocolError';
  }
}

/** Parses the DEVICE_INFO JSON, refusing anything malformed or from a newer protocol. */
export function parseDeviceInfo(bytes: Uint8Array): DeviceInfo {
  let raw: unknown;
  try {
    raw = JSON.parse(utf8Decode(bytes));
  } catch {
    throw new ProtocolError('Device info is not valid JSON.');
  }
  if (raw === null || typeof raw !== 'object') {
    throw new ProtocolError('Device info is not an object.');
  }
  const info = raw as Record<string, unknown>;
  if (info.protocol !== PROTOCOL_VERSION) {
    throw new ProtocolError(`Unsupported protocol version: ${String(info.protocol)}.`);
  }
  if (typeof info.hardware_id !== 'string' || !HARDWARE_ID_PATTERN.test(info.hardware_id)) {
    throw new ProtocolError('Device info has no valid hardware id.');
  }
  return {
    protocol: info.protocol,
    hardwareId: info.hardware_id,
    model: typeof info.model === 'string' ? info.model : 'Nura',
    firmwareVersion:
      typeof info.firmware_version === 'string' ? info.firmware_version : 'unknown',
    provisioned: info.provisioned === true,
    registered: info.registered === true,
  };
}

/** `NURA-3C84279A1B2C` -> `1B2C`, the id shown on the robot and in the list. */
export function shortIdFor(hardwareId: string): string {
  return hardwareId.slice(-4);
}

// --- PAIRING -----------------------------------------------------------------

export function encodePakeStart(pA: Uint8Array): Uint8Array {
  if (pA.length !== POINT_LENGTH) throw new ProtocolError('pA must be 65 bytes.');
  return Uint8Array.of(PairingMessage.PAKE_START, ...pA);
}

export function encodePakeConfirm(cA: Uint8Array): Uint8Array {
  if (cA.length !== MAC_LENGTH) throw new ProtocolError('cA must be 32 bytes.');
  return Uint8Array.of(PairingMessage.PAKE_CONFIRM, ...cA);
}

export type PairingNotification =
  | { type: 'pakeResponse'; pB: Uint8Array; cB: Uint8Array }
  | { type: 'result'; result: PairingResultName };

export function decodePairingNotification(bytes: Uint8Array): PairingNotification {
  const type = bytes[0];
  if (type === PairingMessage.PAKE_RESPONSE) {
    if (bytes.length !== 1 + POINT_LENGTH + MAC_LENGTH) {
      throw new ProtocolError('PAKE response has the wrong length.');
    }
    return {
      type: 'pakeResponse',
      pB: bytes.slice(1, 1 + POINT_LENGTH),
      cB: bytes.slice(1 + POINT_LENGTH),
    };
  }
  if (type === PairingMessage.PAIRING_RESULT && bytes.length === 2) {
    const result = nameFor(PairingResult, bytes[1] ?? -1);
    if (result) return { type: 'result', result };
  }
  throw new ProtocolError('Unrecognised pairing message.');
}

// --- STATUS ------------------------------------------------------------------

export interface RobotStatus {
  state: ProvisioningStateName;
  error: ProvisioningErrorName;
}

export function decodeStatus(bytes: Uint8Array): RobotStatus {
  if (bytes.length !== 2) throw new ProtocolError('Status must be 2 bytes.');
  const state = nameFor(ProvisioningState, bytes[0] ?? -1);
  // An error code this build does not know is still an error, not success.
  const error = nameFor(ProvisioningError, bytes[1] ?? -1) ?? 'UNKNOWN_ERROR';
  if (!state) throw new ProtocolError('Unknown provisioning state.');
  return { state, error };
}

export function encodeCommand(command: CommandName): Uint8Array {
  return Uint8Array.of(Command[command]);
}
