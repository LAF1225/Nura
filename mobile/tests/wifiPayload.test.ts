/**
 * The Wi-Fi payload and the form rules around it (PRD 2, sections 21-24).
 *
 * The security properties checked here are the ones that matter if someone is
 * listening during setup: the payload is unreadable without the verified
 * session key, and it cannot be replayed at a different robot.
 */
import { randomBytes } from 'crypto';

import { utf8ToBytes } from '@noble/hashes/utils.js';

import {
  decryptWifiConfig,
  deriveWifiKey,
  encryptWifiConfig,
  normaliseCode,
  PayloadTooLargeError,
  validateCode,
  validateSsid,
  validateWifiPassword,
} from '../src/services/provisioning/wifiPayload';

const HARDWARE_ID = 'NURA-3C84279A1B2C';
const KE = new Uint8Array(randomBytes(16));
const NONCE = new Uint8Array(randomBytes(12));
const CONFIG = {
  ssid: 'Home Network',
  password: 'correct horse battery staple',
  provisioningToken: 'npt_abcdefghijklmnopqrstuvwxyz',
  apiBaseUrl: 'http://192.168.1.20:8000',
};

describe('the encrypted Wi-Fi payload', () => {
  const key = deriveWifiKey(KE);

  it('round-trips through the robot side', () => {
    const payload = encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE);
    expect(decryptWifiConfig(key, HARDWARE_ID, payload)).toEqual(CONFIG);
  });

  it('never exposes the password in the bytes that go over the air', () => {
    const payload = encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE);
    const needle = utf8ToBytes(CONFIG.password);
    const haystack = Array.from(payload).join(',');
    expect(haystack.includes(Array.from(needle).join(','))).toBe(false);
  });

  it('cannot be read with a key from a different session', () => {
    const payload = encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE);
    const otherKey = deriveWifiKey(new Uint8Array(randomBytes(16)));
    expect(() => decryptWifiConfig(otherKey, HARDWARE_ID, payload)).toThrow();
  });

  it('cannot be replayed at a different robot', () => {
    const payload = encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE);
    // The hardware id is authenticated as associated data, not encrypted.
    expect(() => decryptWifiConfig(key, 'NURA-3C84279AFFFF', payload)).toThrow();
  });

  it('rejects a payload that has been tampered with', () => {
    const payload = encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE);
    payload[20] = (payload[20] ?? 0) ^ 0xff;
    expect(() => decryptWifiConfig(key, HARDWARE_ID, payload)).toThrow();
  });

  it('uses a different nonce each time, so two identical configs differ', () => {
    const first = encryptWifiConfig(
      key,
      HARDWARE_ID,
      CONFIG,
      new Uint8Array(randomBytes(12))
    );
    const second = encryptWifiConfig(
      key,
      HARDWARE_ID,
      CONFIG,
      new Uint8Array(randomBytes(12))
    );
    expect(Array.from(first)).not.toEqual(Array.from(second));
  });

  it('refuses a payload too large for one characteristic write', () => {
    expect(() =>
      encryptWifiConfig(
        key,
        HARDWARE_ID,
        { ...CONFIG, apiBaseUrl: `http://${'x'.repeat(500)}` },
        NONCE
      )
    ).toThrow(PayloadTooLargeError);
  });

  it('fits comfortably in a single write for realistic details', () => {
    expect(encryptWifiConfig(key, HARDWARE_ID, CONFIG, NONCE).length).toBeLessThan(512);
  });
});

describe('form rules', () => {
  it('accepts a normal home network', () => {
    expect(validateSsid('Home Network')).toBeNull();
    expect(validateWifiPassword('correct horse')).toBeNull();
  });

  it('requires a network name of at most 32 bytes', () => {
    expect(validateSsid('')).toMatch(/Enter the Wi-Fi network name/);
    expect(validateSsid('x'.repeat(33))).toMatch(/too long/);
    // Counted in bytes, not characters: emoji SSIDs are legal but wide.
    expect(validateSsid('📶'.repeat(9))).toMatch(/too long/);
    expect(validateSsid('x'.repeat(32))).toBeNull();
  });

  it('holds passwords to the WPA2 and WPA3 Personal range', () => {
    expect(validateWifiPassword('')).toMatch(/Enter the Wi-Fi password/);
    expect(validateWifiPassword('short')).toMatch(/at least 8/);
    expect(validateWifiPassword('x'.repeat(64))).toMatch(/at most 63/);
    expect(validateWifiPassword('x'.repeat(8))).toBeNull();
  });

  it('accepts the pairing code with or without spaces', () => {
    expect(normaliseCode('482 731')).toBe('482731');
    expect(validateCode('482 731')).toBeNull();
    expect(validateCode('')).toMatch(/Enter the code/);
    expect(validateCode('4827')).toMatch(/6 digits/);
    expect(validateCode('48273a')).toMatch(/6 digits/);
  });
});
