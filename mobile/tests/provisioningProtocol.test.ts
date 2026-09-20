/**
 * The app and the firmware must agree on every byte of the protocol
 * (PRD 2, section 12: "Store all UUID definitions in shared documentation").
 *
 * This reads the firmware header itself, so adding a status code on one side
 * and forgetting the other fails here rather than on a bench with a robot.
 *
 * Parsed by hand rather than with regular expressions: the shapes involved are
 * simple, and this stays readable next to the header it mirrors.
 */
import { readFileSync } from 'fs';
import { join } from 'path';

import {
  Command,
  MAX_ATTRIBUTE_LENGTH,
  NONCE_LENGTH,
  PAKE_AAD,
  PAKE_IDENTITY_APP,
  PAKE_W_DOMAIN,
  PairingMessage,
  PairingResult,
  POINT_LENGTH,
  PROTOCOL_VERSION,
  ProvisioningError,
  ProvisioningState,
  REQUESTED_MTU,
  UUIDS,
  WIFI_KEY_INFO,
} from '../src/services/provisioning/protocol';

const HEADER = readFileSync(
  join(__dirname, '..', '..', 'firmware', 'xiao_esp32s3', 'src', 'protocol.h'),
  'utf8'
);
const LINES = HEADER.split('\n');

function declarationOf(name: string): string {
  const line = LINES.find(
    (candidate) => candidate.startsWith('constexpr ') && candidate.includes(` ${name} =`)
  );
  if (!line) throw new Error(`protocol.h has no constant named ${name}`);
  return line;
}

/** `constexpr const char* NAME = "value";` */
function stringConstant(name: string): string {
  const line = declarationOf(name);
  const start = line.indexOf('"');
  const end = line.lastIndexOf('"');
  if (start < 0 || end <= start) throw new Error(`${name} is not a string constant`);
  return line.slice(start + 1, end);
}

/** `constexpr <type> NAME = 123;` -- decimal or hex. */
function numberConstant(name: string): number {
  const line = declarationOf(name);
  // Drop any trailing `// comment` before reading the value.
  const withoutComment = line.split('//')[0] ?? line;
  const value = withoutComment
    .slice(withoutComment.indexOf('=') + 1)
    .replace(';', '')
    .trim();
  const parsed = Number(value);
  if (Number.isNaN(parsed)) throw new Error(`${name} is not a numeric constant`);
  return parsed;
}

/** `enum class Name : uint8_t { A = 0x01, ... };` */
function enumConstants(name: string): Record<string, number> {
  const start = LINES.findIndex((line) => line.startsWith(`enum class ${name} `));
  if (start < 0) throw new Error(`protocol.h has no enum named ${name}`);
  const values: Record<string, number> = {};
  for (let index = start + 1; index < LINES.length; index += 1) {
    const line = (LINES[index] ?? '').trim();
    if (line.startsWith('}')) return values;
    const [key, rest] = line.split('=');
    if (key && rest) values[key.trim()] = Number(rest.replace(',', '').trim());
  }
  throw new Error(`enum ${name} is not closed`);
}

describe('protocol.h and protocol.ts agree', () => {
  it('on the protocol version', () => {
    expect(numberConstant('PROTOCOL_VERSION')).toBe(PROTOCOL_VERSION);
  });

  it('on every GATT UUID', () => {
    expect(stringConstant('UUID_SERVICE')).toBe(UUIDS.service);
    expect(stringConstant('UUID_DEVICE_INFO')).toBe(UUIDS.deviceInfo);
    expect(stringConstant('UUID_PAIRING')).toBe(UUIDS.pairing);
    expect(stringConstant('UUID_WIFI_CONFIG')).toBe(UUIDS.wifiConfig);
    expect(stringConstant('UUID_COMMAND')).toBe(UUIDS.command);
    expect(stringConstant('UUID_STATUS')).toBe(UUIDS.status);
  });

  it('on the SPAKE2 identities, which change every derived key if they differ', () => {
    expect(stringConstant('PAKE_IDENTITY_APP')).toBe(PAKE_IDENTITY_APP);
    expect(stringConstant('PAKE_AAD')).toBe(PAKE_AAD);
    expect(stringConstant('PAKE_W_DOMAIN')).toBe(PAKE_W_DOMAIN);
    expect(stringConstant('WIFI_KEY_INFO')).toBe(WIFI_KEY_INFO);
  });

  it.each([
    ['PairingMessage', PairingMessage],
    ['PairingResult', PairingResult],
    ['Command', Command],
    ['ProvisioningState', ProvisioningState],
    ['ProvisioningError', ProvisioningError],
  ])('on the %s values', (name, table) => {
    expect(enumConstants(name)).toEqual(table);
  });

  it('on the message sizes', () => {
    expect(numberConstant('POINT_LENGTH')).toBe(POINT_LENGTH);
    expect(numberConstant('NONCE_LENGTH')).toBe(NONCE_LENGTH);
    expect(numberConstant('MAX_ATTRIBUTE_LENGTH')).toBe(MAX_ATTRIBUTE_LENGTH);
    // The robot's preferred MTU must cover what the app asks Android for.
    expect(numberConstant('BLE_PREFERRED_MTU')).toBe(REQUESTED_MTU);
  });
});
