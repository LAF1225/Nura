/**
 * One retry policy, shared (PRD 13, sections 28, 30 and 35).
 *
 * **This module is a de-duplication, not a change.** Five features each had
 * their own `RETRYABLE` list and their own `isRetryable` -- medications,
 * symptoms, appointments, daily life and the daily check-in -- and PRD 13's
 * survey found all five already identical. So nothing here alters what any
 * queue does. What it changes is that the policy now has one place to be
 * read, argued with and tested, which is what section 30 asks for and what
 * section 57 permits: two or more systems genuinely reuse it, five in fact.
 *
 * The policy, as section 30 states it:
 *
 *     transport failure   -> retryable
 *     auth failure        -> retryable, after re-authenticating
 *     validation failure  -> stop, and surface the error
 *     conflict            -> stop; the resolver has already decided
 *
 * **Why an auth failure is retryable here.** Section 30 says "stop and
 * re-authenticate", and that is what happens: the request stops, the app
 * routes to sign-in, and the *queued action survives* so it is sent once
 * somebody is signed in again. Discarding a recorded dose because a token
 * expired overnight would lose something a person actually did -- and the
 * medication queue's own comment said exactly that before this module existed.
 *
 * **Why a validation failure is not.** A body the server will always refuse
 * will be refused on every retry, so retrying is a loop that never ends and
 * never tells anybody. The entry is dropped and the screen says so.
 */
import { ApiError, isApiError } from '../../services/api/errors';
import type { ApiErrorKind } from '../../services/api/errors';

/**
 * Kinds worth sending again.
 *
 * Deliberately a list of what *is* retryable rather than what is not: a new
 * error kind added to `ApiErrorKind` is then non-retryable until somebody
 * decides otherwise, which is the safer default for a queue -- it surfaces
 * rather than spins.
 */
export const RETRYABLE_KINDS: readonly ApiErrorKind[] = [
  // The connection, in its three shapes.
  'offline',
  'unavailable',
  'timeout',
  // The server broke. Not the request's fault, so it is worth sending again.
  'server',
  // Sign in again and it goes. See the module docstring.
  'unauthorized',
  // No API URL in this build. A developer problem, and the action should
  // survive being fixed.
  'configuration',
  // Something we could not classify. Retrying an unknown beats discarding
  // somebody's recorded dose because a response surprised us.
  'unknown',
];

/**
 * Kinds that stop, with why. Exhaustive against `ApiErrorKind` by the test, so
 * a new kind cannot quietly land in neither list.
 */
export const TERMINAL_KINDS: Readonly<Record<string, string>> = {
  validation:
    'The server will refuse this body every time. Retrying is a loop that ' +
    'never ends and never tells anybody.',
  conflict:
    'The server already had something newer and said so. The conflict ' +
    'resolver has decided; sending it again would ask the same question.',
  notFound:
    'Whatever this action was about is gone. A dose, task or appointment that ' +
    'no longer exists cannot be acted on.',
};

/** Whether a failed request is worth sending again. */
export function isRetryable(error: unknown): boolean {
  return isApiError(error) && RETRYABLE_KINDS.includes(error.kind);
}

/**
 * Whether this failure means the queue should stop and surface it.
 *
 * The complement of `isRetryable` for an `ApiError`, and `false` for anything
 * that is not one -- a thrown `TypeError` from a parser is a bug rather than a
 * server refusal, and `isRetryable` already treats it as not retryable, so a
 * caller asking "should I show this?" gets a straight answer either way.
 */
export function isTerminal(error: unknown): boolean {
  return isApiError(error) && !RETRYABLE_KINDS.includes(error.kind);
}

/** Why one terminal failure stopped, for a screen that wants to say so. */
export function terminalReason(error: unknown): string | null {
  if (!isApiError(error)) return null;
  return TERMINAL_KINDS[error.kind] ?? null;
}

/** Re-exported so a queue needs one import rather than two. */
export { ApiError, isApiError };
