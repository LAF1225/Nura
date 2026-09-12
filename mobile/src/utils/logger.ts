/**
 * Small logging utility (PRD 0, section 21).
 *
 * Rules that matter more than the implementation:
 *  - Never log passwords, authentication tokens, medical records or private
 *    conversations. `redact()` below exists to make that easy to honour.
 *  - `debug` and `info` are development-only so release builds stay quiet.
 *
 * Deliberately console-based. A crash/telemetry backend can replace the body
 * of `write()` later without touching any call site.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

/** Keys whose values are replaced before anything is written out. */
const SENSITIVE_KEYS = [
  'password',
  'token',
  'accessToken',
  'refreshToken',
  'idToken',
  'authorization',
  'apiKey',
  'secret',
  'otp',
  'code',
];

function isSensitiveKey(key: string): boolean {
  const lowered = key.toLowerCase();
  return SENSITIVE_KEYS.some((candidate) => lowered.includes(candidate.toLowerCase()));
}

/**
 * Returns a copy of `value` with sensitive fields masked, at any depth.
 * Use it whenever you log something that came from a request or a form.
 */
export function redact<T>(value: T): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redact(item));
  }
  if (value !== null && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    const output: Record<string, unknown> = {};
    for (const key of Object.keys(source)) {
      output[key] = isSensitiveKey(key) ? '[redacted]' : redact(source[key]);
    }
    return output;
  }
  return value;
}

function write(level: LogLevel, scope: string, message: string, context?: unknown): void {
  const prefix = `[nura:${scope}]`;
  const args: unknown[] =
    context === undefined ? [prefix, message] : [prefix, message, redact(context)];

  switch (level) {
    case 'debug':
    case 'info':
      if (__DEV__) {
        console.log(...args);
      }
      break;
    case 'warn':
      console.warn(...args);
      break;
    case 'error':
      console.error(...args);
      break;
  }
}

/**
 * Creates a logger bound to a scope, e.g. `createLogger('api')`.
 * The scope shows up in every line so logs stay searchable.
 */
export function createLogger(scope: string) {
  return {
    debug: (message: string, context?: unknown) =>
      write('debug', scope, message, context),
    info: (message: string, context?: unknown) => write('info', scope, message, context),
    warn: (message: string, context?: unknown) => write('warn', scope, message, context),
    error: (message: string, context?: unknown) =>
      write('error', scope, message, context),
  };
}

export type Logger = ReturnType<typeof createLogger>;
