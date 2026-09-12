/**
 * Runtime configuration (PRD 0, sections 15 and 18).
 *
 * Every value the app needs from the environment is resolved here, once. No
 * other file should read `process.env` or hard-code a host or port.
 *
 * Only `EXPO_PUBLIC_*` variables are readable from the app: Expo inlines them
 * into the bundle at build time. That also means they are *public* -- never put
 * a private key or secret in one. Backend-only secrets stay in backend/.env.
 */
import Constants from 'expo-constants';

/** Port the FastAPI backend listens on during local development. */
const DEV_BACKEND_PORT = 8000;

/** How long a single request may take before it is treated as timed out. */
export const API_TIMEOUT_MS = 10_000;

function stripTrailingSlash(url: string): string {
  return url.endsWith('/') ? url.slice(0, -1) : url;
}

/**
 * Works out the backend address during development.
 *
 * A phone running Expo Go cannot reach `localhost` -- that would be the phone
 * itself. Expo already knows the LAN address your machine is serving the
 * bundle from, so we reuse its host and swap in the backend port. That makes a
 * physical device work with no manual IP editing, while an emulator or web
 * still resolves correctly.
 */
function deriveDevApiUrl(): string {
  const hostUri =
    Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost ?? null;

  const host = hostUri?.split(':')[0];
  if (host) {
    return `http://${host}:${DEV_BACKEND_PORT}`;
  }
  return `http://localhost:${DEV_BACKEND_PORT}`;
}

/**
 * Base URL for the Nura API, without a trailing slash.
 *
 * Empty string means "not configured". The API client turns that into an
 * explicit configuration error rather than firing a request at a bad URL --
 * see `src/services/api/client.ts`.
 */
function resolveApiBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL?.trim();
  if (fromEnv) {
    return stripTrailingSlash(fromEnv);
  }
  if (__DEV__) {
    return deriveDevApiUrl();
  }
  // Release builds must be given an explicit HTTPS URL (PRD 0, section 18).
  return '';
}

export const config = {
  apiBaseUrl: resolveApiBaseUrl(),
  apiTimeoutMs: API_TIMEOUT_MS,
  /** App version from app.json, shown on the More tab. */
  appVersion: Constants.expoConfig?.version ?? '0.0.0',
  isDev: __DEV__,
} as const;
