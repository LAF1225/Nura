/**
 * One error type for everything the API layer can fail with, plus the
 * user-facing wording for each case (PRD 0, section 20).
 *
 * Screens should never render a raw exception. They switch on `kind`, or call
 * `apiErrorMessage()` for a sentence that is safe to show someone.
 */

export type ApiErrorKind =
  /** The device has no network connection at all. */
  | 'offline'
  /** Network is up but the backend did not answer. */
  | 'unavailable'
  /** Request took longer than the configured timeout. */
  | 'timeout'
  /** 401 / 403 -- not signed in, or not allowed to see this resource. */
  | 'unauthorized'
  /** 404 */
  | 'notFound'
  /** 400 / 422 -- the request body was rejected. */
  | 'validation'
  /** 409 -- the request conflicts with current state (e.g. already claimed). */
  | 'conflict'
  /** 5xx, or a response we could not make sense of. */
  | 'server'
  /** No API URL was configured for this build. */
  | 'configuration'
  | 'unknown';

interface ApiErrorOptions {
  status?: number;
  cause?: unknown;
  code?: string;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  /**
   * Stable machine-readable reason, when the server gave one
   * (`{"detail": {"code": "already_claimed"}}`). Screens branch on this; they
   * never display the server's own message.
   */
  readonly code?: string;

  constructor(kind: ApiErrorKind, message: string, options: ApiErrorOptions = {}) {
    super(message, { cause: options.cause });
    this.name = 'ApiError';
    this.kind = kind;
    this.status = options.status;
    this.code = options.code;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Maps an HTTP status onto the closest error kind. */
export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 404) return 'notFound';
  if (status === 400 || status === 422) return 'validation';
  if (status === 409) return 'conflict';
  if (status >= 500) return 'server';
  return 'unknown';
}

const MESSAGES: Record<ApiErrorKind, string> = {
  offline: 'You appear to be offline. Check your connection and try again.',
  unavailable: 'Nura services are unreachable right now. Please try again shortly.',
  timeout: 'That took too long to respond. Please try again.',
  unauthorized: 'You do not have access to this. Please sign in again.',
  notFound: 'We could not find what you were looking for.',
  validation: 'Some of the details were not accepted. Please review and try again.',
  conflict: 'That could not be done right now. Please refresh and try again.',
  server: 'Something went wrong on our side. Please try again shortly.',
  configuration: 'Nura is not configured to reach its services in this build.',
  unknown: 'Something unexpected happened. Please try again.',
};

/**
 * A sentence that is safe to put in front of a user, for any thrown value.
 * Unknown/non-API errors fall back to the generic wording rather than leaking
 * an exception message.
 */
export function apiErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return MESSAGES[error.kind];
  }
  return MESSAGES.unknown;
}
