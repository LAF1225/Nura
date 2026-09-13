/**
 * Shared test setup.
 *
 * Rendering any screen now goes through the auth gate, so tests have to say
 * whether the user is signed in and how far through onboarding they are.
 * These helpers make that a single line and keep the backend deterministic.
 */
import { useAppStore } from '../src/store/appStore';
import type { OnboardingStatus } from '../src/types/account';

/** A signed-out app, which is where a first launch starts. */
export function signOut(): void {
  useAppStore.setState({
    authStatus: 'unauthenticated',
    session: null,
    lastOnboardingStatus: null,
    suggestedName: null,
  });
}

/**
 * A signed-in user at a given point in onboarding.
 *
 * `lastOnboardingStatus` is the persisted routing hint, so the gate can route
 * immediately without waiting on the network -- the same path a real relaunch
 * takes.
 */
export function signInAt(status: OnboardingStatus): void {
  useAppStore.setState({
    authStatus: 'authenticated',
    session: {
      userId: 'test-user',
      provider: 'email',
      email: 'person@example.test',
      phone: null,
    },
    lastOnboardingStatus: status,
    suggestedName: null,
  });
}

interface BackendState {
  status?: OnboardingStatus;
  setupMode?: 'self' | 'assisted' | null;
  termsAccepted?: boolean;
  privacyAcknowledged?: boolean;
  preferredName?: string;
  /** Raw `/api/v1/devices` response items, in wire format. */
  devices?: Record<string, unknown>[];
}

/** Records what the stubbed backend was asked to do, for assertions. */
export interface BackendStub {
  requests: { method: string; path: string; body: unknown }[];
  state: Required<BackendState>;
  restore: () => void;
}

const STEP_FOR_STATUS: Record<OnboardingStatus, number> = {
  not_started: 0,
  authenticated: 1,
  setup_mode_selected: 2,
  basic_profile_complete: 3,
  preferences_complete: 4,
  consent_complete: 5,
  ready_for_pairing: 5,
  robot_connected: 5,
  onboarding_complete: 5,
};

/**
 * Installs a fetch stub for the Nura API.
 *
 * It mirrors the real endpoints closely enough for screen tests: PATCHes
 * update the in-memory state and the response reflects it, so a test can
 * assert that a screen actually persisted something.
 */
export function mockBackend(initial: BackendState = {}): BackendStub {
  const originalFetch = globalThis.fetch;

  const stub: BackendStub = {
    requests: [],
    state: {
      status: initial.status ?? 'authenticated',
      setupMode: initial.setupMode ?? null,
      termsAccepted: initial.termsAccepted ?? false,
      privacyAcknowledged: initial.privacyAcknowledged ?? false,
      preferredName: initial.preferredName ?? 'Ada',
      devices: initial.devices ?? [],
    },
    restore: () => {
      globalThis.fetch = originalFetch;
    },
  };

  const onboardingBody = () => ({
    status: stub.state.status,
    setup_mode: stub.state.setupMode,
    terms_accepted: stub.state.termsAccepted,
    privacy_acknowledged: stub.state.privacyAcknowledged,
    step: STEP_FOR_STATUS[stub.state.status],
    total_steps: 5,
    ready_for_pairing:
      stub.state.status === 'ready_for_pairing' ||
      stub.state.status === 'onboarding_complete',
  });

  const accountBody = () => ({
    id: 'account-1',
    email: 'person@example.test',
    phone: null,
    settings: {
      theme: 'system',
      language: 'en',
      larger_text: false,
      high_contrast: false,
      reduce_motion: false,
      voice_first_preference: false,
      simplified_interface: false,
    },
    profiles: [
      { id: 'profile-1', preferred_name: stub.state.preferredName, role: 'self' },
    ],
  });

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    // Strip the origin. `indexOf` returns -1 for non-API routes such as
    // /health, and slice(-1) would leave a single character.
    const apiIndex = url.indexOf('/api/v1');
    const path =
      apiIndex >= 0 ? url.slice(apiIndex) : url.replace(/^https?:\/\/[^/]+/, '');
    const method = init?.method ?? 'GET';
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    stub.requests.push({ method, path, body });

    if (path.startsWith('/api/v1/onboarding')) {
      if (method === 'PATCH' && body) {
        if (body.setup_mode !== undefined) stub.state.setupMode = body.setup_mode;
        if (body.accept_terms !== undefined) stub.state.termsAccepted = body.accept_terms;
        if (body.acknowledge_privacy !== undefined) {
          stub.state.privacyAcknowledged = body.acknowledge_privacy;
        }
        if (body.status !== undefined) stub.state.status = body.status;
      }
      return jsonResponse(onboardingBody());
    }

    if (path.startsWith('/api/v1/profiles')) {
      if (body?.preferred_name) stub.state.preferredName = body.preferred_name;
      return jsonResponse(
        { id: 'profile-1', preferred_name: stub.state.preferredName, role: 'self' },
        method === 'POST' ? 201 : 200
      );
    }

    if (path.startsWith('/api/v1/me')) {
      return jsonResponse(accountBody());
    }

    if (path === '/api/v1/devices') {
      return jsonResponse(stub.state.devices);
    }

    return jsonResponse({ status: 'ok', service: 'nura-api' });
  }) as typeof fetch;

  return stub;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}
