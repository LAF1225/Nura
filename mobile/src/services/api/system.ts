/**
 * System / meta endpoints (PRD 0, sections 15 and 29).
 *
 * Named "system" rather than "health" to keep it clearly separate from the
 * Health tab, which will be about medical data in later PRDs.
 *
 * The backend speaks snake_case; the app speaks camelCase. The mapping happens
 * here, in the parse functions, so the rest of the app never sees wire format.
 */
import type { HealthResponse, VersionResponse } from '../../types/api';
import { apiRequest } from './client';
import { ApiError } from './errors';

function asRecord(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requireString(
  source: Record<string, unknown>,
  key: string,
  endpoint: string
): string {
  const value = source[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('server', `Missing "${key}" in response from ${endpoint}.`);
  }
  return value;
}

/**
 * Validates a `GET /health` body.
 *
 * Exported separately from the request so it can be unit-tested without a
 * network (PRD 0, section 22).
 */
export function parseHealthResponse(raw: unknown): HealthResponse {
  const body = asRecord(raw, '/health');
  return {
    status: requireString(body, 'status', '/health'),
    service: requireString(body, 'service', '/health'),
  };
}

export function parseVersionResponse(raw: unknown): VersionResponse {
  const body = asRecord(raw, '/api/v1/version');
  return {
    apiVersion: requireString(body, 'api_version', '/api/v1/version'),
    minimumAppVersion: requireString(body, 'minimum_app_version', '/api/v1/version'),
  };
}

/** Liveness probe. Deliberately unversioned (PRD 0, section 15). */
export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return parseHealthResponse(await apiRequest<unknown>('/health', { signal }));
}

export async function fetchVersion(signal?: AbortSignal): Promise<VersionResponse> {
  return parseVersionResponse(await apiRequest<unknown>('/api/v1/version', { signal }));
}
