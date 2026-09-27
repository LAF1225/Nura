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

/**
 * The registry's defaults, mirroring `CARD_REGISTRY` in
 * `backend/app/services/dashboard.py`. `medications` became available and
 * visible in PRD 5 and `symptoms` in PRD 6; `appointments` stands in for the
 * keys that are still reserved but have no feature behind them.
 */
export const DEFAULT_CARDS: CardState[] = [
  {
    key: 'daily_checkin',
    title: 'Daily check-in',
    available: true,
    visible: true,
    position: 0,
  },
  {
    key: 'medications',
    title: 'Medications',
    available: true,
    visible: true,
    position: 1,
  },
  {
    key: 'device_status',
    title: 'Nura status',
    available: true,
    visible: true,
    position: 2,
  },
  {
    key: 'quick_actions',
    title: 'Quick actions',
    available: true,
    visible: false,
    position: 3,
  },
  {
    key: 'symptoms',
    title: 'Symptoms',
    available: true,
    visible: true,
    position: 4,
  },
  {
    key: 'appointments',
    title: 'Appointments',
    available: false,
    visible: false,
    position: 5,
  },
];

/**
 * A profile with no schedules -- the state most accounts are in, and the one
 * where the Today medication card draws nothing at all.
 */
export const NO_MEDICATIONS: Record<string, unknown> = {
  next_due: null,
  due_today_count: 0,
  overdue_count: 0,
  remaining_today_count: 0,
  low_supply: [],
  has_schedules: false,
};

/** A dose as `/api/v1/profiles/{id}/medication-doses` returns it. */
export function doseFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'dose-1',
    profile_id: 'profile-1',
    medication_id: 'medication-1',
    medication_name: 'Metformin',
    medication_dose: '500 mg',
    schedule_id: 'schedule-1',
    scheduled_for: '2026-09-13T08:00:00Z',
    local_date: '2026-09-13',
    status: 'scheduled',
    window: 'due',
    action_at: null,
    source: null,
    skip_reason_code: null,
    skip_reason_text: null,
    snoozed_until: null,
    snooze_count: 0,
    late: false,
    can_snooze: true,
    ...overrides,
  };
}

/**
 * A PRD 4 medication record, as `/api/v1/profiles/{id}/medications` returns
 * it. The four fields every health record carries are required by the parser,
 * so a fixture that leaves them out produces an empty list rather than an
 * error anybody would notice.
 */
export function medicationRecordFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'medication-1',
    profile_id: 'profile-1',
    name: 'Metformin',
    dose: '500',
    dose_unit: 'mg',
    form: 'tablet',
    is_active: true,
    source: 'user',
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T08:00:00Z',
    ...overrides,
  };
}

/** A schedule as `/api/v1/profiles/{id}/medication-schedules` returns it. */
export function scheduleFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'schedule-1',
    profile_id: 'profile-1',
    medication_id: 'medication-1',
    medication_name: 'Metformin',
    medication_dose: '500 mg',
    schedule_type: 'daily',
    timezone: 'Europe/London',
    start_date: '2026-09-13',
    end_date: null,
    is_active: true,
    paused_at: null,
    times: [{ id: 'time-1', time_of_day: '08:00:00', weekday: null }],
    created_at: '2026-09-13T07:00:00Z',
    updated_at: '2026-09-13T07:00:00Z',
    ...overrides,
  };
}

/**
 * A profile that has never logged a symptom -- the state most accounts are in,
 * and the one where the Today symptom card draws nothing at all.
 */
export const NO_SYMPTOMS: Record<string, unknown> = {
  active_count: 0,
  worsening_count: 0,
  most_recent: null,
  has_episodes: false,
};

/** The safety block as the server sends it when there is nothing to say. */
export const QUIET_SAFETY: Record<string, unknown> = {
  worsening: false,
  reasons: [],
  notice: null,
  urgent: false,
};

/** An entry as `/api/v1/profiles/{id}/symptoms/{id}/entries` returns it. */
export function symptomEntryFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'entry-1',
    profile_id: 'profile-1',
    symptom_episode_id: 'episode-1',
    recorded_at: '2026-09-27T09:00:00Z',
    main_symptom: 'headache',
    site: 'behind both eyes',
    onset_text: 'this morning',
    onset_at: null,
    onset_date: '2026-09-27',
    character: 'throbbing',
    radiation: null,
    timing: null,
    severity: 5,
    change_state: 'worsening',
    free_text_note: null,
    associated_symptoms: ['nausea'],
    exacerbating_factors: [],
    relieving_factors: [],
    negated_items: [],
    uncertain_items: [],
    context_dependent_items: [],
    source: 'manual_app',
    photos: [],
    created_at: '2026-09-27T09:00:00Z',
    updated_at: '2026-09-27T09:00:00Z',
    ...overrides,
  };
}

/** An episode as `/api/v1/profiles/{id}/symptoms` returns it. */
export function symptomEpisodeFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const entry =
    (overrides.latest_entry as Record<string, unknown>) ?? symptomEntryFixture();
  return {
    id: 'episode-1',
    profile_id: 'profile-1',
    name: 'Headache',
    body_site: 'behind both eyes',
    status: 'active',
    first_noticed_at: null,
    first_noticed_date: '2026-09-27',
    first_noticed_year: null,
    first_noticed_text: 'this morning',
    resolved_at: null,
    previous_episode_id: null,
    source: 'manual_app',
    entry_count: 1,
    latest_entry: entry,
    entries: [entry],
    safety: QUIET_SAFETY,
    created_at: '2026-09-27T09:00:00Z',
    updated_at: '2026-09-27T09:00:00Z',
    ...overrides,
  };
}

/** A photo as the upload and read routes describe one. Never a storage key. */
export function symptomPhotoFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'photo-1',
    symptom_entry_id: 'entry-1',
    content_type: 'image/jpeg',
    byte_size: 1024,
    created_at: '2026-09-27T09:00:00Z',
    ...overrides,
  };
}

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
  /** Raw `/medication-schedules` items, in wire format. */
  schedules?: Record<string, unknown>[];
  /** Raw `/medication-doses` items, in wire format. */
  doses?: Record<string, unknown>[];
  /** Raw `/medication-supply` items, in wire format. */
  supply?: Record<string, unknown>[];
  /** The `medications` block of `/api/v1/today`. Null for no profile. */
  todayMedications?: Record<string, unknown> | null;
  /** Raw `/symptoms` items, in wire format. */
  symptoms?: Record<string, unknown>[];
  /** The `symptoms` block of `/api/v1/today`. Null for no profile. */
  todaySymptoms?: Record<string, unknown> | null;
  /** How many entries have been created, for generating ids. */
  symptomEntries?: number;
  /** Items for the Important Today section. */
  important?: Record<string, unknown>[];
  healthSetup?: { status: string; step: string | null; blood_type: string | null };
  /** Status code to answer the health endpoints with. */
  healthStatus?: number;
}

/** Records what the stubbed backend was asked to do, for assertions. */
export interface BackendStub {
  requests: {
    method: string;
    path: string;
    body: unknown;
    /** True for a multipart upload, whose body is not JSON. */
    multipart?: boolean;
  }[];
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
      schedules: initial.schedules ?? [],
      doses: initial.doses ?? [],
      supply: initial.supply ?? [],
      todayMedications: initial.todayMedications ?? NO_MEDICATIONS,
      symptoms: initial.symptoms ?? [],
      todaySymptoms: initial.todaySymptoms ?? NO_SYMPTOMS,
      symptomEntries: initial.symptomEntries ?? 0,
      important: initial.important ?? [],
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
    medications: stub.state.todayMedications,
    symptoms: stub.state.todaySymptoms,
    important: stub.state.important,
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
      // Counted separately from conditions, as the server does
      // (PRD 6, section 48).
      active_symptoms: stub.state.symptoms.filter((entry) =>
        ['active', 'recurring'].includes(String(entry.status))
      ).length,
      symptom_updates_this_week: stub.state.symptoms.length,
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
    // A photo upload sends FormData, which is not JSON. Recorded as multipart
    // rather than parsed, so a stray `JSON.parse` cannot make an upload look
    // like a refusal (PRD 6, section 34).
    const isMultipart =
      init?.body !== undefined && init?.body !== null && typeof init.body !== 'string';
    // `any`, as `JSON.parse` gives, so the handlers below can read fields off
    // a request body without casting at every use.
    let body: ReturnType<typeof JSON.parse> | undefined;
    if (init?.body !== undefined && init?.body !== null && !isMultipart) {
      try {
        body = JSON.parse(String(init.body));
      } catch {
        body = undefined;
      }
    }
    stub.requests.push({ method, path, body, multipart: isMultipart });

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

    const medicationMatch =
      /^\/api\/v1\/profiles\/[^/]+\/(medication-schedules|medication-doses|medication-supply|medication-adherence)(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (medicationMatch) {
      const resource = medicationMatch[1] ?? '';
      const first = medicationMatch[3];
      const second = medicationMatch[5];

      if (resource === 'medication-schedules') {
        if (method === 'POST') {
          const created = scheduleFixture({
            id: `schedule-${stub.state.schedules.length + 1}`,
            ...(body as Record<string, unknown>),
          });
          stub.state.schedules = [...stub.state.schedules, created];
          return jsonResponse(created, 201);
        }
        if (method === 'PATCH' && first) {
          stub.state.schedules = stub.state.schedules.map((entry) =>
            entry.id === first
              ? { ...entry, ...(body as Record<string, unknown>) }
              : entry
          );
          return jsonResponse(
            stub.state.schedules.find((entry) => entry.id === first) ?? {}
          );
        }
        if (method === 'POST' && second === 'pause') {
          return jsonResponse(stub.state.schedules[0] ?? {});
        }
        if (method === 'DELETE' && first) {
          stub.state.schedules = stub.state.schedules.filter(
            (entry) => entry.id !== first
          );
          return jsonResponse(null, 204);
        }
        if (first) {
          return jsonResponse(
            stub.state.schedules.find((entry) => entry.id === first) ?? {}
          );
        }
        return jsonResponse(stub.state.schedules);
      }

      if (resource === 'medication-doses') {
        // `.../{id}/taken|snooze|skip` -- the action is the last segment.
        if (method === 'POST' && first && second) {
          const status =
            second === 'taken' ? 'taken' : second === 'skip' ? 'skipped' : 'snoozed';
          stub.state.doses = stub.state.doses.map((entry) =>
            entry.id === first
              ? { ...entry, status, window: second === 'snooze' ? 'due' : 'completed' }
              : entry
          );
          const dose = stub.state.doses.find((entry) => entry.id === first);
          return jsonResponse({
            dose: dose ?? doseFixture({ id: first, status }),
            applied: true,
            supply_remaining: null,
            low_supply: false,
          });
        }
        return jsonResponse(stub.state.doses);
      }

      if (resource === 'medication-supply') {
        if (method === 'POST' || method === 'PATCH') {
          const medicationId = first ?? '';
          const existing = stub.state.supply.find(
            (entry) => entry.medication_id === medicationId
          );
          const updated = {
            profile_id: 'profile-1',
            medication_id: medicationId,
            medication_name: 'Metformin',
            tracking_enabled: true,
            refill_threshold_doses: null,
            last_refill_date: null,
            low: false,
            ...existing,
            ...(body as Record<string, unknown>),
          };
          stub.state.supply = [
            ...stub.state.supply.filter((entry) => entry.medication_id !== medicationId),
            updated,
          ];
          return jsonResponse(updated);
        }
        return jsonResponse(stub.state.supply);
      }

      // medication-adherence
      const counted = stub.state.doses.filter((entry) =>
        ['taken', 'skipped', 'missed'].includes(String(entry.status))
      );
      const taken = counted.filter((entry) => entry.status === 'taken').length;
      return jsonResponse({
        profile_id: 'profile-1',
        from_date: '2026-09-07',
        to_date: '2026-09-13',
        taken,
        skipped: counted.filter((entry) => entry.status === 'skipped').length,
        missed: counted.filter((entry) => entry.status === 'missed').length,
        total: counted.length,
        percent: counted.length === 0 ? null : Math.floor((taken * 100) / counted.length),
      });
    }

    const symptomMatch =
      /^\/api\/v1\/profiles\/[^/]+\/symptoms(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (symptomMatch) {
      const first = symptomMatch[2];
      const second = symptomMatch[4];
      const third = symptomMatch[6];
      const fourth = symptomMatch[8];

      if (first === 'summary') {
        const active = stub.state.symptoms.filter((entry) =>
          ['active', 'recurring'].includes(String(entry.status))
        );
        return jsonResponse({
          profile_id: 'profile-1',
          active_count: active.length,
          worsening_count: active.filter(
            (entry) =>
              (entry.latest_entry as Record<string, unknown> | null)?.change_state ===
              'worsening'
          ).length,
          recent_updates_count: active.length,
          has_episodes: stub.state.symptoms.length > 0,
        });
      }

      // A photo upload is also a POST under `entries`, so it is matched
      // first -- otherwise the entry branch below would swallow it.
      // `.../{episodeId}/entries/{entryId}/photos`
      if (fourth === 'photos' && method === 'POST') {
        return jsonResponse(symptomPhotoFixture({ symptom_entry_id: third }), 201);
      }

      if (second === 'entries' && method === 'POST') {
        const entry = symptomEntryFixture({
          id: `entry-${stub.state.symptomEntries + 1}`,
          symptom_episode_id: first,
          ...(body as Record<string, unknown>),
        });
        stub.state.symptomEntries += 1;
        stub.state.symptoms = stub.state.symptoms.map((episode) =>
          episode.id === first
            ? {
                ...episode,
                latest_entry: entry,
                entries: [entry, ...((episode.entries as unknown[]) ?? [])],
                entry_count: Number(episode.entry_count ?? 0) + 1,
              }
            : episode
        );
        return jsonResponse(
          {
            entry,
            created: true,
            safety:
              (body as Record<string, unknown>)?.change_state === 'worsening'
                ? {
                    worsening: true,
                    reasons: ['reported_worsening'],
                    notice: 'You have recorded this as worsening.',
                    urgent: false,
                  }
                : QUIET_SAFETY,
          },
          201
        );
      }

      if (second === 'resolve' && method === 'POST') {
        stub.state.symptoms = stub.state.symptoms.map((episode) =>
          episode.id === first
            ? { ...episode, status: 'resolved', resolved_at: '2026-09-27T12:00:00Z' }
            : episode
        );
        return jsonResponse(
          stub.state.symptoms.find((episode) => episode.id === first) ?? {}
        );
      }

      if (second === 'recur' && method === 'POST') {
        const created = symptomEpisodeFixture({
          id: `episode-${stub.state.symptoms.length + 1}`,
          status: 'recurring',
          previous_episode_id: first,
          entry_count: 0,
          latest_entry: null,
          entries: [],
        });
        stub.state.symptoms = [...stub.state.symptoms, created];
        return jsonResponse({ episode: created, created: true }, 201);
      }

      if (method === 'POST' && first === undefined) {
        const sent = body as Record<string, unknown>;
        const entry = symptomEntryFixture({
          id: `entry-${stub.state.symptomEntries + 1}`,
          symptom_episode_id: `episode-${stub.state.symptoms.length + 1}`,
          ...((sent?.first_entry as Record<string, unknown>) ?? {}),
        });
        stub.state.symptomEntries += 1;
        const created = symptomEpisodeFixture({
          id: `episode-${stub.state.symptoms.length + 1}`,
          name: String(sent?.name ?? 'Symptom'),
          body_site: sent?.body_site ?? null,
          first_noticed_date: sent?.first_noticed_date ?? null,
          first_noticed_text: sent?.first_noticed_text ?? null,
          source: sent?.source ?? 'manual_app',
          latest_entry: entry,
          entries: [entry],
        });
        stub.state.symptoms = [...stub.state.symptoms, created];
        return jsonResponse({ episode: created, created: true }, 201);
      }

      if (method === 'PATCH' && first) {
        stub.state.symptoms = stub.state.symptoms.map((episode) =>
          episode.id === first
            ? { ...episode, ...(body as Record<string, unknown>) }
            : episode
        );
        return jsonResponse(
          stub.state.symptoms.find((episode) => episode.id === first) ?? {}
        );
      }

      if (method === 'DELETE') {
        if (fourth === 'photos') {
          return jsonResponse(null, 204);
        }
        stub.state.symptoms = stub.state.symptoms.filter(
          (episode) => episode.id !== first
        );
        return jsonResponse(null, 204);
      }

      if (first) {
        return jsonResponse(
          stub.state.symptoms.find((episode) => episode.id === first) ?? {}
        );
      }

      // The list, with the filters the screens actually send.
      const query = url.slice(url.indexOf('?') + 1);
      let rows = stub.state.symptoms;
      if (url.includes('?') && query.includes('active=true')) {
        rows = rows.filter((entry) =>
          ['active', 'recurring'].includes(String(entry.status))
        );
      } else if (url.includes('?') && query.includes('status=resolved')) {
        rows = rows.filter((entry) => entry.status === 'resolved');
      }
      return jsonResponse(rows);
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
