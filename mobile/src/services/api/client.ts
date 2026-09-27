/**
 * The one place that talks HTTP to the Nura backend (PRD 0, section 15).
 *
 * Nothing else in the app should call `fetch` or know a URL. Callers get a
 * parsed body on success, or an `ApiError` with a `kind` they can branch on.
 */
import NetInfo from '@react-native-community/netinfo';

import { config } from '../../constants/config';
import { createLogger } from '../../utils/logger';
import { ApiError, kindForStatus } from './errors';

const log = createLogger('api');

/** Supplies the bearer token for outgoing requests, or null when signed out. */
type TokenProvider = () => Promise<string | null>;

let getAccessToken: TokenProvider = async () => null;

/**
 * Registers where the access token comes from.
 *
 * Injected rather than imported so this module stays independent of the auth
 * provider: the client can be exercised in tests without pulling in Supabase,
 * and swapping auth backends later touches one call site. The app registers
 * its provider once, at startup.
 */
export function setAuthTokenProvider(provider: TokenProvider): void {
  getAccessToken = provider;
}

/**
 * Uploads get longer than the usual timeout: a photo over a slow connection is
 * not a stalled request, and failing it early would send the user back to a
 * picker they have already used.
 */
const UPLOAD_TIMEOUT_MS = 60_000;

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** Serialised as JSON. Omit for GET. */
  body?: unknown;
  /** Lets a caller (or TanStack Query) cancel the request. */
  signal?: AbortSignal;
  timeoutMs?: number;
}

/**
 * Distinguishes "the phone has no network" from "the backend is down".
 * Only consulted after a request has already failed, so the common path does
 * not pay for it.
 */
async function classifyNetworkFailure(): Promise<'offline' | 'unavailable'> {
  try {
    const state = await NetInfo.fetch();
    // `isInternetReachable` is null while still being determined; treat an
    // unknown result as "connected" so we do not wrongly blame the network.
    const connected = state.isConnected && state.isInternetReachable !== false;
    return connected ? 'unavailable' : 'offline';
  } catch {
    return 'unavailable';
  }
}

/**
 * The `code` from a `{"detail": {"code": ...}}` error body, if there is one.
 * Only the code is kept; the server's message is never shown to users.
 */
async function readErrorCode(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { detail?: { code?: unknown } };
    const code = body?.detail?.code;
    return typeof code === 'string' ? code : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Performs a JSON request against the API.
 *
 * @param path path beginning with `/`, e.g. `/health` or `/api/v1/version`.
 * @throws ApiError for every failure mode, including transport failures.
 */
export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  if (!config.apiBaseUrl) {
    // Release build with no EXPO_PUBLIC_API_URL. Fail loudly and clearly
    // instead of firing a request at a meaningless URL.
    throw new ApiError('configuration', 'No API base URL is configured.');
  }

  const { method = 'GET', body, signal, timeoutMs = config.apiTimeoutMs } = options;
  const url = `${config.apiBaseUrl}${path}`;

  // Our own timeout, combined with any caller-supplied cancellation.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  signal?.addEventListener('abort', abortFromCaller);

  // Attached whenever the user is signed in. Public routes ignore it, so
  // there is no need for call sites to say which routes are protected.
  const token = await getAccessToken();

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (cause) {
    // A caller-initiated cancel is not an error worth reporting as one, but it
    // still has to reject so the caller stops waiting.
    if (signal?.aborted) {
      throw new ApiError('unknown', 'Request was cancelled.', { cause });
    }
    if (controller.signal.aborted) {
      log.warn('request timed out', { path, timeoutMs });
      throw new ApiError('timeout', `Request to ${path} timed out.`, { cause });
    }
    const kind = await classifyNetworkFailure();
    log.warn('request failed before a response', { path, kind });
    throw new ApiError(kind, `Could not reach ${path}.`, { cause });
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener('abort', abortFromCaller);
  }

  if (!response.ok) {
    const code = await readErrorCode(response);
    log.warn('request returned an error status', { path, status: response.status, code });
    throw new ApiError(
      kindForStatus(response.status),
      `Request to ${path} failed with status ${response.status}.`,
      { status: response.status, code }
    );
  }

  // 204 and friends have no body.
  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    log.error('response body was not valid JSON', { path });
    throw new ApiError('server', `Response from ${path} was not valid JSON.`, { cause });
  }
}

/** One file, as React Native describes a local file to `fetch`. */
export interface UploadFile {
  /** A `file://` URI on this device. */
  uri: string;
  name: string;
  type: string;
}

/**
 * Sends one file as multipart form data.
 *
 * Separate from `apiRequest` because the two have almost nothing in common
 * beyond the base URL and the token: there is no JSON body to serialise, the
 * Content-Type must be left for the runtime to set with its own boundary, and a
 * photo needs a longer timeout than a JSON call. Everything else -- the error
 * shapes, the offline classification, the `code` extraction -- is shared.
 *
 * Kept in this module because it is still `fetch`, and this is still the only
 * place in the app allowed to call it (PRD 0, section 15).
 */
export async function apiUpload<T>(
  path: string,
  options: { file: UploadFile; fields?: Record<string, string>; timeoutMs?: number }
): Promise<T> {
  if (!config.apiBaseUrl) {
    throw new ApiError('configuration', 'No API base URL is configured.');
  }

  const body = new FormData();
  // Cast: React Native accepts a `{ uri, name, type }` descriptor where the
  // DOM types insist on a Blob, and reading the file into a Blob first would
  // put a whole photo in memory for no reason.
  body.append('file', options.file as unknown as Blob);
  for (const [key, value] of Object.entries(options.fields ?? {})) {
    body.append(key, value);
  }

  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? UPLOAD_TIMEOUT_MS;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const token = await getAccessToken();

  let response: Response;
  try {
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body,
      signal: controller.signal,
    });
  } catch (cause) {
    if (controller.signal.aborted) {
      log.warn('upload timed out', { path, timeoutMs });
      throw new ApiError('timeout', `Upload to ${path} timed out.`, { cause });
    }
    const kind = await classifyNetworkFailure();
    // The filename is never logged: a photo path is as sensitive as what is in
    // it (PRD 6, section 62).
    log.warn('upload failed before a response', { path, kind });
    throw new ApiError(kind, `Could not reach ${path}.`, { cause });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const code = await readErrorCode(response);
    log.warn('upload returned an error status', { path, status: response.status, code });
    throw new ApiError(
      kindForStatus(response.status),
      `Upload to ${path} failed with status ${response.status}.`,
      { status: response.status, code }
    );
  }

  try {
    return (await response.json()) as T;
  } catch (cause) {
    throw new ApiError('server', `Response from ${path} was not valid JSON.`, { cause });
  }
}

/**
 * An authenticated source for an `<Image>`, or null when signed out.
 *
 * Private media -- a symptom photo -- is served by a route that re-checks the
 * profile on every request, so there is no public URL to hand a component and no
 * signed one either (PRD 6, section 63). What a component needs instead is the
 * URL *and* the bearer token, and building both here keeps URLs and tokens
 * inside this module where they belong.
 */
export async function mediaSource(
  path: string
): Promise<{ uri: string; headers: Record<string, string> } | null> {
  if (!config.apiBaseUrl) return null;
  const token = await getAccessToken();
  if (token === null) return null;
  return {
    uri: `${config.apiBaseUrl}${path}`,
    headers: { Authorization: `Bearer ${token}` },
  };
}
