/**
 * The encrypted Wi-Fi payload (PRD 2, sections 23-24; protocol doc 3.3).
 *
 * AES-128-GCM under a key derived from the verified SPAKE2 session. The Wi-Fi
 * password exists in plaintext only inside `encryptWifiConfig`, and nothing in
 * this module logs.
 */
import { gcm } from '@noble/ciphers/aes.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { concatBytes, utf8ToBytes } from '@noble/hashes/utils.js';

import { utf8Decode } from './bytes';
import {
  MAX_ATTRIBUTE_LENGTH,
  NONCE_LENGTH,
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  SSID_MAX_BYTES,
  WIFI_CONFIG_VERSION,
  WIFI_KEY_INFO,
  WIFI_KEY_LENGTH,
} from './protocol';

export interface WifiConfig {
  ssid: string;
  password: string;
  provisioningToken: string;
  apiBaseUrl: string;
}

export function deriveWifiKey(ke: Uint8Array): Uint8Array {
  return hkdf(sha256, ke, undefined, utf8ToBytes(WIFI_KEY_INFO), WIFI_KEY_LENGTH);
}

function additionalData(hardwareId: string): Uint8Array {
  return concatBytes(Uint8Array.of(WIFI_CONFIG_VERSION), utf8ToBytes(hardwareId));
}

export class PayloadTooLargeError extends Error {
  constructor() {
    super('The Wi-Fi details are too long to send.');
    this.name = 'PayloadTooLargeError';
  }
}

/** `01 || nonce || ciphertext || tag`. */
export function encryptWifiConfig(
  key: Uint8Array,
  hardwareId: string,
  config: WifiConfig,
  nonce: Uint8Array
): Uint8Array {
  if (nonce.length !== NONCE_LENGTH) throw new Error('Nonce must be 12 bytes.');
  const plaintext = utf8ToBytes(
    JSON.stringify({
      ssid: config.ssid,
      password: config.password,
      provisioning_token: config.provisioningToken,
      api_base_url: config.apiBaseUrl,
    })
  );
  const sealed = gcm(key, nonce, additionalData(hardwareId)).encrypt(plaintext);
  plaintext.fill(0);
  const payload = concatBytes(Uint8Array.of(WIFI_CONFIG_VERSION), nonce, sealed);
  if (payload.length > MAX_ATTRIBUTE_LENGTH) throw new PayloadTooLargeError();
  return payload;
}

/** The robot's side. Used by tests to prove the robot can read what the app sends. */
export function decryptWifiConfig(
  key: Uint8Array,
  hardwareId: string,
  payload: Uint8Array
): WifiConfig {
  if (payload[0] !== WIFI_CONFIG_VERSION) throw new Error('Unknown payload version.');
  const nonce = payload.slice(1, 1 + NONCE_LENGTH);
  const sealed = payload.slice(1 + NONCE_LENGTH);
  const plaintext = gcm(key, nonce, additionalData(hardwareId)).decrypt(sealed);
  const parsed = JSON.parse(utf8Decode(plaintext)) as Record<string, string>;
  return {
    ssid: parsed.ssid ?? '',
    password: parsed.password ?? '',
    provisioningToken: parsed.provisioning_token ?? '',
    apiBaseUrl: parsed.api_base_url ?? '',
  };
}

// --- validation (PRD 2, sections 21-23) --------------------------------------

export function utf8Length(value: string): number {
  return utf8ToBytes(value).length;
}

/** Null when valid, otherwise a sentence to show under the field. */
export function validateSsid(ssid: string): string | null {
  if (ssid.length === 0) return 'Enter the Wi-Fi network name.';
  if (utf8Length(ssid) > SSID_MAX_BYTES) return 'That network name is too long.';
  return null;
}

export function validateWifiPassword(password: string): string | null {
  if (password.length === 0) return 'Enter the Wi-Fi password.';
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Wi-Fi passwords are at least ${PASSWORD_MIN_LENGTH} characters.`;
  }
  if (password.length > PASSWORD_MAX_LENGTH) {
    return `Wi-Fi passwords are at most ${PASSWORD_MAX_LENGTH} characters.`;
  }
  return null;
}

/** Six digits, ignoring spaces the user may type between groups. */
export function normaliseCode(input: string): string {
  return input.replace(/\s+/g, '');
}

export function validateCode(input: string): string | null {
  const code = normaliseCode(input);
  if (code.length === 0) return 'Enter the code shown on Nura.';
  if (!/^\d{6}$/.test(code)) return 'The code is 6 digits.';
  return null;
}
