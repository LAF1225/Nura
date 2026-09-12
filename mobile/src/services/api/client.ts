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

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
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

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
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
    log.warn('request returned an error status', { path, status: response.status });
    throw new ApiError(
      kindForStatus(response.status),
      `Request to ${path} failed with status ${response.status}.`,
      { status: response.status }
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
