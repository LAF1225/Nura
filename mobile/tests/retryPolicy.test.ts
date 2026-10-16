/**
 * One retry policy, and all five queues using it (PRD 13, ss28, 30, 31).
 *
 * The consolidation was a de-duplication rather than a change -- all five
 * copies were already identical -- so the interesting assertions are not
 * "retrying works" but these two:
 *
 * `describe('every error kind is decided')` makes the policy exhaustive. A new
 * `ApiErrorKind` that nobody classified is in neither list, and that fails
 * here rather than silently becoming non-retryable.
 *
 * `describe('the five queues share it')` reads the queue modules and asserts
 * none of them has grown its own copy back. A shared policy that one feature
 * quietly forks is worse than five honest copies, because the divergence is
 * invisible.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  RETRYABLE_KINDS,
  TERMINAL_KINDS,
  isRetryable,
  isTerminal,
  terminalReason,
} from '../src/features/reliability/retry';
import { ApiError } from '../src/services/api/errors';
import type { ApiErrorKind } from '../src/services/api/errors';

/** Every kind the API layer can produce. Kept in step by the test below. */
const ALL_KINDS: ApiErrorKind[] = [
  'offline',
  'unavailable',
  'timeout',
  'unauthorized',
  'notFound',
  'validation',
  'conflict',
  'server',
  'configuration',
  'unknown',
];

function error(kind: ApiErrorKind): ApiError {
  return new ApiError(kind, 'test');
}

describe('the policy', () => {
  it('retries a transport failure', () => {
    // Section 30's first line.
    for (const kind of ['offline', 'unavailable', 'timeout'] as ApiErrorKind[]) {
      expect(isRetryable(error(kind))).toBe(true);
    }
  });

  it('retries an auth failure, so the action survives signing in again', () => {
    // Section 30 says "stop and re-authenticate", and that is what happens:
    // the request stops, the app routes to sign-in, and the queued action is
    // still there afterwards. Discarding a recorded dose because a token
    // expired overnight would lose something somebody actually did.
    expect(isRetryable(error('unauthorized'))).toBe(true);
  });

  it('stops on a validation failure and says why', () => {
    expect(isRetryable(error('validation'))).toBe(false);
    expect(isTerminal(error('validation'))).toBe(true);
    expect(terminalReason(error('validation'))).toContain('refuse this body');
  });

  it('stops on a conflict, because the resolver has already decided', () => {
    expect(isRetryable(error('conflict'))).toBe(false);
    expect(terminalReason(error('conflict'))).toContain('something newer');
  });

  it('stops on a not-found, because the thing is gone', () => {
    expect(isRetryable(error('notFound'))).toBe(false);
    expect(terminalReason(error('notFound'))).toContain('no longer exists');
  });

  it('does not retry something that is not an ApiError', () => {
    // A thrown `TypeError` from a parser is a bug, not a server refusal.
    expect(isRetryable(new TypeError('boom'))).toBe(false);
    expect(isTerminal(new TypeError('boom'))).toBe(false);
    expect(terminalReason(new TypeError('boom'))).toBeNull();
  });
});

describe('every error kind is decided', () => {
  it('covers the kind list', () => {
    // A guard: if `ApiErrorKind` grows and this array is not updated, the
    // exhaustiveness check below would pass while ignoring the new kind.
    // TypeScript catches a *removed* kind; this catches an added one by
    // comparing against the union's own members as written in the source.
    const source = readFileSync(join('src', 'services', 'api', 'errors.ts'), 'utf8');
    const union = source.slice(
      source.indexOf('export type ApiErrorKind'),
      source.indexOf(';', source.indexOf('export type ApiErrorKind'))
    );
    const declared = [...union.matchAll(/'([a-zA-Z]+)'/g)].map((match) => match[1]);
    expect(declared.sort()).toEqual([...ALL_KINDS].sort());
  });

  it('classifies each one as retryable or terminal, never neither', () => {
    const unclassified = ALL_KINDS.filter(
      (kind) => !RETRYABLE_KINDS.includes(kind) && TERMINAL_KINDS[kind] === undefined
    );
    expect(unclassified).toEqual([]);
  });

  it('and never both', () => {
    const both = RETRYABLE_KINDS.filter((kind) => TERMINAL_KINDS[kind] !== undefined);
    expect(both).toEqual([]);
  });

  it('gives every terminal kind a reason worth reading', () => {
    for (const [kind, reason] of Object.entries(TERMINAL_KINDS)) {
      expect(reason.length).toBeGreaterThan(30);
      expect(ALL_KINDS).toContain(kind as ApiErrorKind);
    }
  });
});

describe('the five queues share it', () => {
  const QUEUES = [
    join('src', 'features', 'medications', 'pendingActions.ts'),
    join('src', 'features', 'symptoms', 'pendingEntries.ts'),
    join('src', 'features', 'appointments', 'pending.ts'),
    join('src', 'features', 'productivity', 'pending.ts'),
    join('src', 'services', 'checkins', 'pendingCheckIn.ts'),
  ];

  it('none of them declares its own kind list', () => {
    // The five identical copies PRD 13 consolidated. A feature growing one
    // back is a fork nobody would notice from the behaviour.
    for (const file of QUEUES) {
      const source = readFileSync(file, 'utf8');
      expect(source).not.toContain('const RETRYABLE');
    }
  });

  it('all of them import the shared policy', () => {
    for (const file of QUEUES) {
      const source = readFileSync(file, 'utf8');
      expect(source).toMatch(/from '[./]*(?:features\/)?reliability\/retry'/);
    }
  });
});
