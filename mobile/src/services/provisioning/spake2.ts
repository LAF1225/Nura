/**
 * SPAKE2 for verifying the physical robot (PRD 2, sections 14-16 and 24).
 *
 * The suite is SPAKE2-P256-SHA256-HKDF-HMAC from RFC 9382, unmodified, built
 * on the audited noble libraries. No cryptography is invented here; see
 * docs/device/provisioning-protocol.md section 4 for why a PAKE is needed at
 * all and how the six-digit code becomes the password.
 *
 * Both roles are implemented because the RFC's test vectors exercise both.
 * The app only ever plays role A. Role B is what the robot does, in C++, in
 * firmware/xiao_esp32s3/src/spake2.cpp; the TypeScript copy exists so the app
 * tests can check the maths against the RFC and simulate a robot.
 */
import { p256 } from '@noble/curves/nist.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { hmac } from '@noble/hashes/hmac.js';
import { sha256, sha512 } from '@noble/hashes/sha2.js';
import { concatBytes, hexToBytes, utf8ToBytes } from '@noble/hashes/utils.js';

import { MAC_LENGTH, PAKE_AAD, PAKE_IDENTITY_APP, PAKE_W_DOMAIN } from './protocol';

const Point = p256.Point;
type CurvePoint = InstanceType<typeof Point>;

/** Order of the P-256 prime subgroup. */
const N = Point.Fn.ORDER;

/** RFC 9382 section 6, P-256. */
const M = Point.fromBytes(
  hexToBytes('02886e2f97ace46e55ba9dd7242579f2993b64e16ef3dcab95afd497333d8fa12f')
);
const NPoint = Point.fromBytes(
  hexToBytes('03d8bbd6c639c62937b04d997f38c3770719c629d7014d49a24b4f98baa1292b49')
);

export class Spake2Error extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'Spake2Error';
  }
}

function bytesToBigInt(bytes: Uint8Array): bigint {
  let value = 0n;
  for (const byte of bytes) value = (value << 8n) | BigInt(byte);
  return value;
}

function bigIntTo32Bytes(value: bigint): Uint8Array {
  const out = new Uint8Array(32);
  let remaining = value;
  for (let index = 31; index >= 0; index -= 1) {
    out[index] = Number(remaining & 0xffn);
    remaining >>= 8n;
  }
  return out;
}

/** RFC 9382's len(): an 8-byte little-endian length prefix. */
function withLength(bytes: Uint8Array): Uint8Array {
  const prefix = new Uint8Array(8);
  let length = bytes.length;
  for (let index = 0; index < 8; index += 1) {
    prefix[index] = length & 0xff;
    length = Math.floor(length / 256);
  }
  return concatBytes(prefix, bytes);
}

/** Constant-time comparison of two MACs. */
export function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let index = 0; index < a.length; index += 1) {
    difference |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return difference === 0;
}

/**
 * Turns uniformly random bytes into a scalar in [1, n-1].
 *
 * Takes 16 bytes more than the scalar needs and reduces mod n-1, the standard
 * way to keep the modulo bias negligible (FIPS 186-5, A.2.1).
 */
export function scalarFromRandomBytes(random: Uint8Array): bigint {
  if (random.length < 48) throw new Spake2Error('Need at least 48 random bytes.');
  return (bytesToBigInt(random) % (N - 1n)) + 1n;
}

/**
 * The password scalar w for a code shown by a robot.
 *
 *   w = OS2IP(SHA-512("nura-pake-w-v1" || len(B) || B || len(code) || code)) mod n
 */
export function passwordScalar(hardwareId: string, code: string): bigint {
  const digest = sha512(
    concatBytes(
      utf8ToBytes(PAKE_W_DOMAIN),
      withLength(utf8ToBytes(hardwareId)),
      withLength(utf8ToBytes(code))
    )
  );
  const w = bytesToBigInt(digest) % N;
  if (w === 0n) throw new Spake2Error('Degenerate password scalar.');
  return w;
}

function decodePoint(bytes: Uint8Array): CurvePoint {
  if (bytes.length !== 65 || bytes[0] !== 0x04) {
    throw new Spake2Error('Expected an uncompressed P-256 point.');
  }
  let point: CurvePoint;
  try {
    // fromBytes rejects anything not on the curve.
    point = Point.fromBytes(bytes);
  } catch {
    throw new Spake2Error('Point is not on the curve.');
  }
  if (point.equals(Point.ZERO)) throw new Spake2Error('Point at infinity.');
  return point;
}

export interface SessionKeys {
  /** Shared secret from the exchange; keys the encrypted Wi-Fi payload. */
  ke: Uint8Array;
  /** Confirmation MAC the app (A) sends. */
  cA: Uint8Array;
  /** Confirmation MAC the robot (B) sends. */
  cB: Uint8Array;
}

/** RFC 9382 section 4: transcript -> Ke, Ka -> KcA, KcB -> MACs. */
export function keySchedule(input: {
  idA: Uint8Array;
  idB: Uint8Array;
  pA: Uint8Array;
  pB: Uint8Array;
  K: Uint8Array;
  w: bigint;
  aad: Uint8Array;
}): SessionKeys & { tt: Uint8Array; ka: Uint8Array; kcA: Uint8Array; kcB: Uint8Array } {
  const tt = concatBytes(
    withLength(input.idA),
    withLength(input.idB),
    withLength(input.pA),
    withLength(input.pB),
    withLength(input.K),
    withLength(bigIntTo32Bytes(input.w))
  );
  const hashed = sha256(tt);
  const ke = hashed.slice(0, 16);
  const ka = hashed.slice(16, 32);
  const confirmationKeys = hkdf(
    sha256,
    ka,
    undefined,
    concatBytes(utf8ToBytes('ConfirmationKeys'), input.aad),
    32
  );
  const kcA = confirmationKeys.slice(0, 16);
  const kcB = confirmationKeys.slice(16, 32);
  return {
    tt,
    ke,
    ka,
    kcA,
    kcB,
    cA: hmac(sha256, kcA, tt),
    cB: hmac(sha256, kcB, tt),
  };
}

/** Role A, first message: pA = x*G + w*M. */
export function computePA(w: bigint, x: bigint): Uint8Array {
  return Point.BASE.multiply(x).add(M.multiply(w)).toBytes(false);
}

/** Role B, first message: pB = y*G + w*N. */
export function computePB(w: bigint, y: bigint): Uint8Array {
  return Point.BASE.multiply(y).add(NPoint.multiply(w)).toBytes(false);
}

/** Role A: K = x*(pB - w*N). */
export function sharedPointForA(w: bigint, x: bigint, pB: Uint8Array): Uint8Array {
  const K = decodePoint(pB).subtract(NPoint.multiply(w)).multiply(x);
  if (K.equals(Point.ZERO)) throw new Spake2Error('Degenerate shared point.');
  return K.toBytes(false);
}

/** Role B: K = y*(pA - w*M). */
export function sharedPointForB(w: bigint, y: bigint, pA: Uint8Array): Uint8Array {
  const K = decodePoint(pA).subtract(M.multiply(w)).multiply(y);
  if (K.equals(Point.ZERO)) throw new Spake2Error('Degenerate shared point.');
  return K.toBytes(false);
}

/**
 * The app's side of one verification attempt.
 *
 * `start()` produces PAKE_START's payload. `finish()` takes the robot's reply,
 * checks the robot's confirmation MAC, and returns the app's MAC plus the
 * session key -- or throws `WrongCodeError` if the code was wrong.
 */
export class WrongCodeError extends Error {
  constructor() {
    super('The code did not match.');
    this.name = 'WrongCodeError';
  }
}

export interface AppPakeSession {
  pA: Uint8Array;
  finish(pB: Uint8Array, cB: Uint8Array): { cA: Uint8Array; ke: Uint8Array };
}

export function startAppPake(
  hardwareId: string,
  code: string,
  randomBytes: (length: number) => Uint8Array
): AppPakeSession {
  const w = passwordScalar(hardwareId, code);
  const x = scalarFromRandomBytes(randomBytes(48));
  const pA = computePA(w, x);

  return {
    pA,
    finish(pB, cB) {
      if (cB.length !== MAC_LENGTH) throw new Spake2Error('cB must be 32 bytes.');
      const K = sharedPointForA(w, x, pB);
      const keys = keySchedule({
        idA: utf8ToBytes(PAKE_IDENTITY_APP),
        idB: utf8ToBytes(hardwareId),
        pA,
        pB,
        K,
        w,
        aad: utf8ToBytes(PAKE_AAD),
      });
      if (!constantTimeEqual(keys.cB, cB)) {
        throw new WrongCodeError();
      }
      return { cA: keys.cA, ke: keys.ke };
    },
  };
}
