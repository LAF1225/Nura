/**
 * One vector, pinned on both sides of the protocol.
 *
 * The firmware checks these exact values in
 * firmware/xiao_esp32s3/test/test_crypto/test_main.cpp. If either
 * implementation changes how it derives a key, builds a transcript or
 * encrypts the Wi-Fi payload, one of the two suites fails -- rather than the
 * app and the robot silently failing to understand each other on a bench.
 *
 * The scalars are fixed so the vector is reproducible. Real sessions use
 * random ones.
 */
import { bytesToHex, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

import {
  computePA,
  computePB,
  keySchedule,
  passwordScalar,
  sharedPointForB,
} from '../src/services/provisioning/spake2';
import {
  decryptWifiConfig,
  deriveWifiKey,
  encryptWifiConfig,
} from '../src/services/provisioning/wifiPayload';

const HARDWARE_ID = 'NURA-3C84279A1B2C';
const CODE = '482731';
const X = BigInt(`0x${'11'.repeat(32)}`);
const Y = BigInt(`0x${'22'.repeat(32)}`);

const EXPECTED = {
  w: '1fa02665ed9b975df75bdb404d18ac479c86b98abd75b35cfaeb5ec458e03c26',
  pA:
    '042a0f9510abc7ebe2f09cd14a890d6ea9a09e7c13aa654a965ea0e37e14a06e09d8528145bfb49615' +
    '53e792dfc36640eb323ee89fa0f53d6f6259b831cf1caa1a',
  pB:
    '04a2be366662ed4452539804b1582bcd21e17a9f38981f65b3b3569c610664a4d2e52aafaf588c505f' +
    'bac21426616cbd8af5db8704a47564775b643d4062ad01d5',
  ke: 'da347a4571da9d8364533754b90058ef',
  cA: 'e8fbd3ba601584c0672bfe17d435036ea2ce384b65c47b67733817669d5134d6',
  cB: 'c04fdbf25ea4b9eec7be699170b43b3f9a8515045019a51aac09368572d13007',
  wifiKey: '9c3599e087412cfc3bff3035e06d4345',
  wifiPayload:
    '010102030405060708090a0b0c35ac3270d48248323c885376a3c38c423af7b06bc2f3a73c2ed51144' +
    '3320dabfed7cab53d0983bf11fb968d89469264c964fa92a6bdacea39ca54f2871e804c20ea2f2adb8' +
    'df0b82a7538d827f96d5a28cbb8418a43480988439648fd37dba967abb13a0066f62df512e9375c965' +
    '3d8b5bdae7055ff24cbe7e3d31f9d1cfbeee1b49ad21a42009ce4daf78d7b029bf979ad55e10a60885' +
    'de9a6980cb110facd3',
};

const CONFIG = {
  ssid: 'Home Network',
  password: 'correct horse battery staple',
  provisioningToken: 'npt_testtoken',
  apiBaseUrl: 'http://192.168.1.20:8000',
};

describe('the vector the firmware also checks', () => {
  const w = passwordScalar(HARDWARE_ID, CODE);
  const pA = computePA(w, X);
  const pB = computePB(w, Y);
  const keys = keySchedule({
    idA: utf8ToBytes('nura-app'),
    idB: utf8ToBytes(HARDWARE_ID),
    pA,
    pB,
    K: sharedPointForB(w, Y, pA),
    w,
    aad: utf8ToBytes('nura-provisioning-v1'),
  });

  it('derives the password scalar from the code and the hardware id', () => {
    expect(w.toString(16).padStart(64, '0')).toBe(EXPECTED.w);
  });

  it('produces the same exchange messages', () => {
    expect(bytesToHex(pA)).toBe(EXPECTED.pA);
    expect(bytesToHex(pB)).toBe(EXPECTED.pB);
  });

  it('agrees on the session key and both confirmations', () => {
    expect(bytesToHex(keys.ke)).toBe(EXPECTED.ke);
    expect(bytesToHex(keys.cA)).toBe(EXPECTED.cA);
    expect(bytesToHex(keys.cB)).toBe(EXPECTED.cB);
  });

  it('derives the same Wi-Fi payload key', () => {
    expect(bytesToHex(deriveWifiKey(keys.ke))).toBe(EXPECTED.wifiKey);
  });

  it('encrypts the Wi-Fi payload the firmware expects to receive', () => {
    const nonce = Uint8Array.from({ length: 12 }, (_, index) => index + 1);
    const payload = encryptWifiConfig(deriveWifiKey(keys.ke), HARDWARE_ID, CONFIG, nonce);
    expect(bytesToHex(payload)).toBe(EXPECTED.wifiPayload);
  });

  it('reads back what the firmware would read', () => {
    expect(
      decryptWifiConfig(
        deriveWifiKey(keys.ke),
        HARDWARE_ID,
        hexToBytes(EXPECTED.wifiPayload)
      )
    ).toEqual(CONFIG);
  });
});
