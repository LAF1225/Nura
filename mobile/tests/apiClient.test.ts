/**
 * API client behaviour (PRD 0, section 22).
 *
 * The parse functions are tested directly, and `apiRequest` is tested against
 * a stubbed `fetch` so error mapping is verified without a running backend.
 *
 * Note: the jest-expo environment replaces the global `fetch` with a stub that
 * returns no `ok` or `status`, so these tests must supply their own. A test
 * that tries to reach a real server here will fail regardless of whether one
 * is running -- verify live endpoints with curl or the app itself instead.
 */
import { apiRequest } from '../src/services/api/client';
import { ApiError } from '../src/services/api/errors';
import { parseHealthResponse, parseVersionResponse } from '../src/services/api/system';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('parseHealthResponse', () => {
  it('parses the documented /health body', () => {
    expect(parseHealthResponse({ status: 'ok', service: 'nura-api' })).toEqual({
      status: 'ok',
      service: 'nura-api',
    });
  });

  it('rejects a body that is missing fields', () => {
    expect(() => parseHealthResponse({ status: 'ok' })).toThrow(ApiError);
    expect(() => parseHealthResponse(null)).toThrow(ApiError);
    expect(() => parseHealthResponse('ok')).toThrow(ApiError);
  });
});

describe('parseVersionResponse', () => {
  it('maps snake_case wire fields onto camelCase', () => {
    expect(
      parseVersionResponse({ api_version: '0.1.0', minimum_app_version: '0.1.0' })
    ).toEqual({ apiVersion: '0.1.0', minimumAppVersion: '0.1.0' });
  });
});

describe('apiRequest', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.restoreAllMocks();
  });

  it('returns the parsed body on success', async () => {
    globalThis.fetch = jest
      .fn()
      .mockResolvedValue(jsonResponse({ status: 'ok', service: 'nura-api' }));

    await expect(apiRequest('/health')).resolves.toEqual({
      status: 'ok',
      service: 'nura-api',
    });
  });

  it('requests the configured base URL', async () => {
    const fetchMock = jest
      .fn()
      .mockResolvedValue(jsonResponse({ status: 'ok', service: 'nura-api' }));
    globalThis.fetch = fetchMock;

    await apiRequest('/health');

    const [url] = fetchMock.mock.calls[0] as [string];
    expect(url).toMatch(/^http:\/\/[^/]+\/health$/);
  });

  it('maps HTTP statuses onto error kinds', async () => {
    const cases: [number, string][] = [
      [401, 'unauthorized'],
      [404, 'notFound'],
      [422, 'validation'],
      [500, 'server'],
    ];

    for (const [status, kind] of cases) {
      globalThis.fetch = jest.fn().mockResolvedValue(jsonResponse({}, status));
      await expect(apiRequest('/health')).rejects.toMatchObject({ kind });
    }
  });

  it('reports a transport failure rather than throwing a raw error', async () => {
    globalThis.fetch = jest
      .fn()
      .mockRejectedValue(new TypeError('Network request failed'));

    // NetInfo's mock reports a connected device, so a failed request means the
    // backend is unreachable rather than the phone being offline.
    await expect(apiRequest('/health')).rejects.toMatchObject({
      name: 'ApiError',
      kind: 'unavailable',
    });
  });

  it('surfaces a non-JSON body as a server error', async () => {
    globalThis.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    } as unknown as Response);

    await expect(apiRequest('/health')).rejects.toMatchObject({ kind: 'server' });
  });
});
