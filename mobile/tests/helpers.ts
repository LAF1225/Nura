/**
 * Shared test setup.
 *
 * Rendering any screen now goes through the auth gate, so tests have to say
 * whether the user is signed in and how far through onboarding they are.
 * These helpers make that a single line and keep the backend deterministic.
 */
import { useAppStore } from '../src/store/appStore';
import type { OnboardingStatus } from '../src/types/account';
import { localDateString } from '../src/utils/date';

/**
 * The date the app will ask for. Computed the same way the app computes it, so
 * a test never fails at a time-zone boundary just because the suite ran at
 * 11pm (PRD 3, section 39).
 */
const LOCAL_DATE_IN_TESTS = () => localDateString();

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

/** A card as `/api/v1/dashboard-preferences` returns it. */
export interface CardState {
  key: string;
  title: string;
  available: boolean;
  visible: boolean;
  position: number;
}

export const DEFAULT_CARDS: CardState[] = [
  {
    key: 'daily_checkin',
    title: 'Daily check-in',
    available: true,
    visible: true,
    position: 0,
  },
  {
    key: 'device_status',
    title: 'Nura status',
    available: true,
    visible: true,
    position: 1,
  },
  {
    key: 'quick_actions',
    title: 'Quick actions',
    available: true,
    visible: false,
    position: 2,
  },
  {
    key: 'medications',
    title: 'Medications',
    available: false,
    visible: false,
    position: 3,
  },
];

interface BackendState {
  status?: OnboardingStatus;
  setupMode?: 'self' | 'assisted' | null;
  termsAccepted?: boolean;
  privacyAcknowledged?: boolean;
  preferredName?: string;
  /** Raw `/api/v1/devices` response items, in wire format. */
  devices?: Record<string, unknown>[];
  /** The `device` block of `/api/v1/today`. Null means no robot linked. */
  todayDevice?: Record<string, unknown> | null;
  /** Today's check-in, or null for "not completed". */
  checkIn?: { wellbeing_level: string; note: string | null } | null;
  cards?: CardState[];
  /** Status code to answer `/api/v1/today` with, for error-state tests. */
  todayStatus?: number;
  /** Health records, keyed by the API path segment ("conditions", …). */
  healthRecords?: Record<string, Record<string, unknown>[]>;
  healthSetup?: { status: string; step: string | null; blood_type: string | null };
  /** Status code to answer the health endpoints with. */
  healthStatus?: number;
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
      todayDevice: initial.todayDevice ?? null,
      checkIn: initial.checkIn ?? null,
      cards: initial.cards ?? DEFAULT_CARDS.map((card) => ({ ...card })),
      todayStatus: initial.todayStatus ?? 200,
      healthRecords: initial.healthRecords ?? {},
      healthSetup: initial.healthSetup ?? {
        status: 'not_started',
        step: null,
        blood_type: null,
      },
      healthStatus: initial.healthStatus ?? 200,
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

  const checkInBody = () =>
    stub.state.checkIn === null
      ? null
      : {
          id: 'checkin-1',
          profile_id: 'profile-1',
          checkin_date: LOCAL_DATE_IN_TESTS(),
          wellbeing_level: stub.state.checkIn.wellbeing_level,
          note: stub.state.checkIn.note,
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        };

  const todayBody = () => ({
    local_date: LOCAL_DATE_IN_TESTS(),
    profile: { id: 'profile-1', preferred_name: stub.state.preferredName },
    daily_checkin: {
      status: stub.state.checkIn === null ? 'not_completed' : 'completed',
      checkin: checkInBody(),
      recent_completed_count: stub.state.checkIn === null ? 0 : 1,
      recent_window_days: 7,
    },
    device: stub.state.todayDevice,
    cards: stub.state.cards,
    important: [],
  });

  /** Section key -> API path segment. Only notes differ. */
  const HEALTH_SECTIONS: { key: string; path: string; title: string }[] = [
    { key: 'conditions', path: 'conditions', title: 'Conditions' },
    { key: 'medications', path: 'medications', title: 'Medications' },
    { key: 'allergies', path: 'allergies', title: 'Allergies' },
    { key: 'clinicians', path: 'clinicians', title: 'Doctors' },
    { key: 'procedures', path: 'procedures', title: 'Surgeries & procedures' },
    { key: 'blood_type', path: '', title: 'Blood type' },
    { key: 'medical_notes', path: 'medical-notes', title: 'Medical notes' },
  ];

  const recordsFor = (segment: string) => stub.state.healthRecords[segment] ?? [];

  /** Built the same way the backend builds it: counts, and nothing else. */
  const healthSummaryBody = () => {
    const sections = HEALTH_SECTIONS.map((section) => {
      if (section.key === 'blood_type') {
        const set = stub.state.healthSetup.blood_type !== null;
        return { ...section, count: set ? 1 : 0, complete: set, updated_at: null };
      }
      const count = recordsFor(section.path).length;
      return {
        key: section.key,
        title: section.title,
        count,
        complete: count > 0,
        updated_at: count > 0 ? '2026-09-21T08:00:00Z' : null,
      };
    });
    const completed = sections.filter((section) => section.complete).length;
    return {
      profile_id: 'profile-1',
      status: stub.state.healthSetup.status,
      step: stub.state.healthSetup.step,
      blood_type: stub.state.healthSetup.blood_type,
      sections: sections.map(({ key, title, count, complete, updated_at }) => ({
        key,
        title,
        count,
        complete,
        updated_at,
      })),
      completed_sections: completed,
      total_sections: sections.length,
      percent: Math.floor((completed * 100) / sections.length),
      active_conditions: recordsFor('conditions').filter(
        (item) => item.status === 'active'
      ).length,
      active_medications: recordsFor('medications').filter(
        (item) => item.is_active !== false
      ).length,
    };
  };

  const healthSetupBody = () => ({
    profile_id: 'profile-1',
    ...stub.state.healthSetup,
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

    const healthMatch =
      /^\/api\/v1\/profiles\/[^/]+\/(health-summary|health-setup|conditions|medications|allergies|clinicians|procedures|medical-notes)(\/([^/?]+))?/.exec(
        path
      );
    if (healthMatch) {
      if (stub.state.healthStatus !== 200) {
        return jsonResponse({ detail: { code: 'unavailable' } }, stub.state.healthStatus);
      }

      const resource = healthMatch[1] ?? '';
      const recordId = healthMatch[3];

      if (resource === 'health-summary') {
        return jsonResponse(healthSummaryBody());
      }

      if (resource === 'health-setup') {
        if (method === 'PATCH' && body) {
          if (body.status !== undefined) stub.state.healthSetup.status = body.status;
          if ('step' in body) stub.state.healthSetup.step = body.step;
          if ('blood_type' in body) {
            stub.state.healthSetup.blood_type = body.blood_type;
          }
        }
        return jsonResponse(healthSetupBody());
      }

      const existing = recordsFor(resource);

      if (method === 'POST') {
        const created = {
          ...body,
          id: `${resource}-${existing.length + 1}`,
          profile_id: 'profile-1',
          source: 'user',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        };
        stub.state.healthRecords[resource] = [created, ...existing];
        return jsonResponse(created, 201);
      }

      if (method === 'PATCH' && recordId) {
        stub.state.healthRecords[resource] = existing.map(
          (item: Record<string, unknown>) =>
            item.id === recordId ? { ...item, ...body } : item
        );
        const updated = (stub.state.healthRecords[resource] ?? []).find(
          (item: Record<string, unknown>) => item.id === recordId
        );
        return jsonResponse(updated ?? {});
      }

      if (method === 'DELETE' && recordId) {
        stub.state.healthRecords[resource] = existing.filter(
          (item: Record<string, unknown>) => item.id !== recordId
        );
        return jsonResponse(null, 204);
      }

      return jsonResponse(existing);
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

    if (path.startsWith('/api/v1/today')) {
      if (stub.state.todayStatus !== 200) {
        return jsonResponse({ detail: { code: 'unavailable' } }, stub.state.todayStatus);
      }
      return jsonResponse(todayBody());
    }

    if (path.startsWith('/api/v1/daily-checkins/today')) {
      if (method === 'PUT' && body) {
        stub.state.checkIn = {
          wellbeing_level: body.wellbeing_level,
          note: body.note ?? null,
        };
      }
      return jsonResponse({ checkin: checkInBody(), applied: true });
    }

    if (path.startsWith('/api/v1/dashboard-preferences')) {
      if (method === 'PUT' && body) {
        const sent: { card_key: string; visible: boolean }[] = body.cards;
        stub.state.cards = stub.state.cards
          .map((card) => {
            const index = sent.findIndex((entry) => entry.card_key === card.key);
            return index === -1
              ? card
              : { ...card, visible: sent[index]!.visible, position: index };
          })
          .sort((a, b) => a.position - b.position);
      }
      return jsonResponse({ profile_id: 'profile-1', cards: stub.state.cards });
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
