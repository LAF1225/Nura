/**
 * The app and the firmware must agree on the presentation protocol
 * (PRD 11, sections 116, 117 and 131).
 *
 * This reads the firmware header itself, so adding a layout, a face or an ack
 * state on one side and forgetting the other fails here rather than on a bench
 * with a robot. The same check runs from the backend's side in
 * `backend/tests/test_robot_protocol.py`, which makes the agreement
 * three-way.
 *
 * Parsed by hand rather than with regular expressions wherever the shape is
 * simple, exactly as `provisioningProtocol.test.ts` reads PRD 2's
 * `protocol.h` -- this stays readable next to the header it mirrors.
 *
 * The app does not speak this protocol. It is checked here because the preview
 * screen draws these layouts (section 95), and a preview of a layout the
 * firmware cannot render would be a preview of something that will never
 * happen.
 */
import { readFileSync } from 'fs';
import { join } from 'path';

import {
  ACK_STATES,
  CAPABILITY_KEYS,
  CAPABILITY_STATES,
  FACE_STATES,
  LAYOUTS,
  PRESENTATION_PROTOCOL_VERSION,
  TEXT_LIMITS,
} from '../src/features/robot/protocol';

const HEADER = readFileSync(
  join(
    __dirname,
    '..',
    '..',
    'firmware',
    'xiao_esp32s3',
    'src',
    'presentation_protocol.h'
  ),
  'utf8'
);
const LINES = HEADER.split('\n');

function declarationOf(name: string): string {
  const line = LINES.find(
    (candidate) => candidate.startsWith('constexpr ') && candidate.includes(` ${name} =`)
  );
  if (!line) throw new Error(`presentation_protocol.h has no constant named ${name}`);
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

/** `constexpr <type> NAME = 123;` */
function numberConstant(name: string): number {
  const line = declarationOf(name);
  const withoutComment = line.split('//')[0] ?? line;
  const value = withoutComment.slice(withoutComment.indexOf('=') + 1).replace(/;.*/, '');
  const parsed = Number(value.trim());
  if (Number.isNaN(parsed)) throw new Error(`${name} is not a number constant`);
  return parsed;
}

/** The member names of `enum class <name> : uint8_t { ... }`. */
function enumMembers(name: string): string[] {
  const start = HEADER.indexOf(`enum class ${name} : uint8_t {`);
  if (start < 0) throw new Error(`no enum class ${name}`);
  const end = HEADER.indexOf('};', start);
  const body = HEADER.slice(start, end);
  return [...body.matchAll(/^\s*([A-Z_]+)\s*=/gm)].map((match) => match[1] as string);
}

it('the protocol version matches', () => {
  expect(numberConstant('PRESENTATION_PROTOCOL_VERSION')).toBe(
    PRESENTATION_PROTOCOL_VERSION
  );
});

it('the firmware knows exactly these eight layouts', () => {
  // `UNKNOWN` is the firmware's own extra member: it is what an unrecognised
  // layout name becomes, and it is how the device reports `unsupported`
  // rather than drawing something close enough (section 111).
  const members = enumMembers('Layout').filter((name) => name !== 'UNKNOWN');
  expect(members.sort()).toEqual([...LAYOUTS].sort());
  for (const layout of LAYOUTS) {
    expect(stringConstant(`LAYOUT_NAME_${layout}`)).toBe(layout);
  }
});

it('the firmware knows exactly these nine face states', () => {
  const members = enumMembers('Face').map((name) => name.toLowerCase());
  expect(members.sort()).toEqual([...FACE_STATES].sort());
  for (const face of FACE_STATES) {
    expect(stringConstant(`FACE_NAME_${face.toUpperCase()}`)).toBe(face);
  }
});

it('the firmware can say exactly these five things about a presentation', () => {
  // Section 19. A device's whole vocabulary for reporting on a card.
  const members = enumMembers('Ack').map((name) => name.toLowerCase());
  expect(members.sort()).toEqual([...ACK_STATES].sort());
  for (const ack of ACK_STATES) {
    expect(stringConstant(`ACK_NAME_${ack.toUpperCase()}`)).toBe(ack);
  }
});

it('the firmware knows every capability key and state', () => {
  for (const key of CAPABILITY_KEYS) {
    expect(stringConstant(`CAPABILITY_${key.toUpperCase()}`)).toBe(key);
  }
  for (const state of CAPABILITY_STATES) {
    expect(stringConstant(`CAPABILITY_${state.toUpperCase()}`)).toBe(state);
  }
});

it('not_verified exists on the device side, because only a device can say it', () => {
  // Sections 12 and 91. The backend has never seen a build, so it cannot
  // write this state; the constant has to exist in the firmware or the state
  // is unreachable.
  expect(stringConstant('CAPABILITY_NOT_VERIFIED')).toBe('not_verified');
  expect(CAPABILITY_STATES).toContain('not_verified');
});

it('the text limits are the same on both sides', () => {
  // Section 77. A limit raised on one side without the other shows up as a
  // truncated reminder on somebody's shelf.
  expect(numberConstant('TITLE_MAX')).toBe(TEXT_LIMITS.title);
  expect(numberConstant('PRIMARY_MAX')).toBe(TEXT_LIMITS.primary);
  expect(numberConstant('SECONDARY_MAX')).toBe(TEXT_LIMITS.secondary);
  expect(numberConstant('BODY_MAX')).toBe(TEXT_LIMITS.body);
  expect(numberConstant('STATUS_LINE_MAX')).toBe(TEXT_LIMITS.statusLine);
  expect(numberConstant('MAX_LINES')).toBe(TEXT_LIMITS.maxLines);
  expect(numberConstant('CODE_MAX')).toBe(TEXT_LIMITS.code);
});

it('the firmware has a state machine of its own', () => {
  // Section 88: the presentation state machine is kept separate from
  // connectivity and from safety, and these are its states.
  expect(enumMembers('ManagerState').sort()).toEqual(
    ['ACKING', 'ERROR', 'FETCHING', 'IDLE', 'RENDERING', 'WAITING'].sort()
  );
});

it('the preview screen draws every layout the firmware can render', () => {
  // Section 95. A preview of something the robot cannot draw would be a
  // preview of something that will never happen.
  const preview = readFileSync(
    join(__dirname, '..', 'app', 'robot', 'preview.tsx'),
    'utf8'
  );
  for (const layout of LAYOUTS) {
    expect(preview).toContain(`${layout}:`);
  }
});
