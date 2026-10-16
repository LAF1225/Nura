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
 * visible in PRD 5, `symptoms` in PRD 6, `appointments` in PRD 7 and
 * `routines` -- retitled "Tasks & routines" -- in PRD 12. `hydration` stands
 * in for the keys that are still reserved and have no feature behind them.
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
    key: 'appointments',
    title: 'Appointments',
    available: true,
    visible: true,
    position: 2,
  },
  {
    key: 'device_status',
    title: 'Nura status',
    available: true,
    visible: true,
    position: 3,
  },
  {
    key: 'quick_actions',
    title: 'Quick actions',
    available: true,
    visible: false,
    position: 4,
  },
  {
    key: 'symptoms',
    title: 'Symptoms',
    available: true,
    visible: true,
    position: 5,
  },
  {
    key: 'routines',
    title: 'Tasks & routines',
    available: true,
    visible: true,
    position: 6,
  },
  {
    key: 'hydration',
    title: 'Hydration',
    available: false,
    visible: false,
    position: 7,
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

/**
 * A profile with no appointments -- which, unlike medications and symptoms, still
 * draws a card: PRD 7 section 9 gives the empty state its own wording.
 */
export const NO_APPOINTMENTS: Record<string, unknown> = {
  next: null,
  upcoming_count: 0,
  has_appointments: false,
};

export function appointmentFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'appointment-1',
    profile_id: 'profile-1',
    title: 'Cardiology follow-up',
    appointment_type: 'specialist',
    status: 'scheduled',
    preparation_status: 'not_started',
    scheduled_at: '2026-10-02T14:30:00Z',
    timezone: 'Europe/London',
    local_date: '2026-10-02',
    day_label: '2 October 2026',
    time_label: '3:30 PM',
    when_label: '2 October 2026 at 3:30 PM',
    relative_day: null,
    clinician: { id: 'clinicians-1', name: 'Dr Ahmed Khan', specialty: 'Cardiology' },
    location_name: 'City Hospital',
    address: null,
    phone: null,
    notes: null,
    visit_notes: null,
    follow_up_date: null,
    reminders_enabled: true,
    cancelled_at: null,
    completed_at: null,
    question_count: 0,
    report_count: 0,
    created_at: '2026-09-28T09:00:00Z',
    updated_at: '2026-09-28T09:00:00Z',
    questions: [],
    reports: [],
    ...overrides,
  };
}

export function questionFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'question-1',
    appointment_id: 'appointment-1',
    text: 'Could this medication be contributing to my fatigue?',
    position: 0,
    is_answered: false,
    answer_note: null,
    created_at: '2026-09-28T09:00:00Z',
    updated_at: '2026-09-28T09:00:00Z',
    ...overrides,
  };
}

/** A report's frozen content, in the shape the backend stores it. */
export function reportSnapshotFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    schema_version: 1,
    title: 'Nura Health Summary',
    generated_at: '2026-09-28T09:15:00Z',
    header: {
      patient: 'Ada',
      lines: [
        'Report period: 30 August to 28 September 2026',
        'Appointment: Cardiology follow-up — 2 October 2026, 3:30 PM (Europe/London)',
      ],
      period_label: '30 August to 28 September 2026',
    },
    period: {
      start: '2026-08-30',
      end: '2026-09-28',
      label: '30 August to 28 September 2026',
      preset: '30_days',
      requested_preset: 'since_last_visit',
      fallback_reason: 'no_linked_clinician',
      note: null,
    },
    summary_sections: [
      {
        key: 'symptoms',
        heading: 'Recent symptoms',
        items: [
          {
            title: 'Headache',
            lines: [
              'Logged 2 times during this period.',
              'Severity ranged from 3/10 to 6/10.',
            ],
          },
        ],
      },
      {
        key: 'questions',
        heading: 'Questions for the clinician',
        items: [
          {
            title: null,
            lines: ['Could this medication be contributing to my fatigue?'],
          },
        ],
      },
    ],
    appendix_sections: [],
    include_appendix: false,
    summary_condensed: false,
    footer_lines: [
      'This is a summary of information recorded in the Nura app. It is not a diagnosis, an assessment or medical advice.',
      'Generated 28 September 2026, 9:15 AM.',
    ],
    ...overrides,
  };
}

export function reportFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'report-1',
    appointment_id: 'appointment-1',
    version: 1,
    status: 'ready',
    period_start: '2026-08-30',
    period_end: '2026-09-28',
    period_preset: '30_days',
    period_label: '30 August to 28 September 2026',
    include_appendix: false,
    generated_at: '2026-09-28T09:15:00Z',
    generated_label: '28 September 2026, 9:15 AM',
    byte_size: 2048,
    page_count: 1,
    file_name: 'Nura_Health_Summary_2026-09-28.pdf',
    selection: {
      include: {
        conditions: true,
        allergies: true,
        procedures: true,
        blood_type: true,
        medications: true,
        adherence: true,
        daily_checkins: true,
        medical_notes: false,
        questions: true,
      },
      symptom_episode_ids: ['episode-1'],
      symptom_note_entry_ids: [],
      medication_ids: null,
      checkin_note_dates: [],
      medical_note_ids: [],
      focus: null,
      include_appendix: false,
      include_skip_reason_notes: false,
    },
    snapshot: reportSnapshotFixture(),
    ...overrides,
  };
}

/** The `/prepare` response, with something in every section worth reviewing. */
export function preparationFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    appointment: appointmentFixture(),
    period: {
      start: '2026-08-30',
      end: '2026-09-28',
      label: '30 August to 28 September 2026',
      preset: '30_days',
      requested_preset: 'since_last_visit',
      note: 'This appointment isn’t linked to a clinician, so Nura can’t tell when you last saw them. Showing the last 30 days.',
      since_label: null,
      days: 30,
    },
    symptoms: [
      {
        episode_id: 'episode-1',
        name: 'Headache',
        body_site: 'behind both eyes',
        status: 'active',
        is_ongoing: true,
        entry_count: 2,
        first_noticed_label: '20 September 2026',
        latest_severity: 6,
        severity_min: 3,
        severity_max: 6,
        latest_change_state: 'worsening',
        associated_symptoms: ['nausea'],
        exacerbating_factors: ['walking'],
        relieving_factors: ['rest'],
        negated_items: [],
        uncertain_items: ['dizziness'],
        context_dependent_items: [],
        notes: [
          {
            entry_id: 'entry-1',
            recorded_at: '2026-09-20T09:00:00Z',
            text: 'worse in the mornings',
          },
        ],
        photo_count: 1,
      },
      {
        episode_id: 'episode-2',
        name: 'Dizziness',
        body_site: null,
        status: 'active',
        is_ongoing: true,
        entry_count: 1,
        first_noticed_label: null,
        latest_severity: 3,
        severity_min: 3,
        severity_max: 3,
        latest_change_state: null,
        associated_symptoms: [],
        exacerbating_factors: [],
        relieving_factors: [],
        negated_items: [],
        uncertain_items: [],
        context_dependent_items: [],
        notes: [],
        photo_count: 0,
      },
    ],
    medications: [
      {
        medication_id: 'medications-1',
        name: 'Metformin',
        display_name: 'Metformin 500 mg',
        dose: '500',
        dose_unit: 'mg',
        frequency: 'Twice daily',
        reason: null,
        is_active: true,
      },
    ],
    adherence: {
      from_date: '2026-08-30',
      to_date: '2026-09-28',
      taken: 13,
      skipped: 1,
      missed: 0,
      total: 14,
      percent: 92,
      skip_notes: [
        {
          dose_id: 'dose-1',
          local_date: '2026-09-20',
          medication_name: 'Metformin',
          reason_code: 'ran_out',
          reason_text: 'pharmacy was shut',
        },
      ],
    },
    daily_checkins: {
      good: 8,
      okay: 11,
      not_great: 4,
      total: 23,
      days_in_period: 30,
      notes: [
        {
          checkin_date: '2026-09-25',
          wellbeing_level: 'not_great',
          note: 'tired all day',
        },
      ],
    },
    baseline: {
      conditions: [
        {
          condition_id: 'conditions-1',
          name: 'Asthma',
          status: 'active',
          diagnosed_label: '2015',
        },
      ],
      allergies: [
        {
          allergy_id: 'allergies-1',
          allergen: 'Penicillin',
          reaction: 'rash',
          severity: 'moderate',
        },
      ],
      procedures: [],
      blood_type: 'O+',
    },
    medical_notes: [
      {
        note_id: 'medical-notes-1',
        title: 'Hospital parking',
        body: 'Use the west entrance.',
        category: 'general',
      },
    ],
    questions: [],
    suggestions: [
      {
        key: 'worsening:episode-1',
        prompt: 'Would you like to ask about your worsening headache?',
        question_text: 'My headache has been getting worse — what should I do?',
        reason: 'symptom_worsening',
      },
      {
        key: 'follow_up_tests',
        prompt: 'Would you like to ask whether you need any follow-up tests?',
        question_text: 'Do I need any follow-up tests?',
        reason: 'generic',
      },
    ],
    has_health_data: true,
    default_selection: {
      include: {
        conditions: true,
        allergies: true,
        procedures: true,
        blood_type: true,
        medications: true,
        adherence: true,
        daily_checkins: true,
        medical_notes: false,
        questions: true,
      },
      symptom_episode_ids: ['episode-1', 'episode-2'],
      symptom_note_entry_ids: [],
      medication_ids: null,
      checkin_note_dates: [],
      medical_note_ids: [],
      focus: null,
      include_appendix: false,
      include_skip_reason_notes: false,
    },
    ...overrides,
  };
}

// --- the Nura assistant (PRD 8) --------------------------------------------

/** Preferences as `/assistant/preferences` returns them. Defaults are Gentle. */
export function assistantPreferencesFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    personality_preset: 'gentle',
    warmth: 'high',
    humour: 'low',
    talkativeness: 'medium',
    proactivity: 'low',
    reminder_firmness: 'low',
    verbosity: 'balanced',
    voice_id: 'calm',
    speaking_speed: 'normal',
    assistant_language: 'en',
    custom_instructions: null,
    mode: 'normal',
    matches_preset: true,
    voice_playback_available: false,
    ...overrides,
  };
}

/** A thread as `/assistant/conversations` returns one. */
export function conversationFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'conversation-1',
    title: 'What does inflammation mean?',
    created_at: '2026-09-28T09:00:00Z',
    updated_at: '2026-09-28T09:01:00Z',
    last_message_at: '2026-09-28T09:01:00Z',
    archived_at: null,
    message_count: 2,
    ...overrides,
  };
}

/** One line of a thread. Only the two roles the API ever returns. */
export function messageFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'message-1',
    conversation_id: 'conversation-1',
    role: 'assistant',
    message_type: 'text',
    content: 'Inflammation is the body\u2019s response to injury or infection.',
    created_at: '2026-09-28T09:01:00Z',
    safety_mode: 'normal',
    meta: {
      model: 'scripted',
      latency_ms: 900,
      tools: [],
      safety_mode: 'normal',
      prompt_version: 1,
      truncated: false,
    },
    pending_action: null,
    ...overrides,
  };
}

/** A remembered preference. Never a health record (PRD 8, section 40). */
export function memoryFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'memory-1',
    category: 'communication',
    content: 'Prefers to be called Baba.',
    source: 'user',
    is_active: true,
    confirmed_at: '2026-09-28T09:00:00Z',
    created_at: '2026-09-28T09:00:00Z',
    updated_at: '2026-09-28T09:00:00Z',
    ...overrides,
  };
}

/** A proactive prompt, built from app data only (PRD 8, section 35). */
export function proactivePromptFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    kind: 'daily_checkin',
    subject_key: '2026-09-28',
    text: 'You haven\u2019t completed today\u2019s check-in yet.',
    route: '/',
    action_label: 'Check in',
    ...overrides,
  };
}

/**
 * What the stub answers a `POST .../messages` with.
 *
 * `replyContent: null` is the section 56 case: the message was recorded, no
 * reply exists, and a failure code says why.
 */
export interface AssistantSendResult {
  replyContent?: string | null;
  failure?: string | null;
  failureMessage?: string | null;
  memorySuggestion?: Record<string, unknown> | null;
  suggestSymptomLog?: boolean;
  safetyMode?: string;
  pendingAction?: Record<string, unknown> | null;
}

// --- PRD 9: caregivers, family messaging and emergency contacts -------------

/** The eight permission rows, in the server's order, with the server's words. */
export function permissionRowsFixture(
  granted: Record<string, boolean> = {}
): Record<string, unknown>[] {
  const rows: [string, string, string, boolean][] = [
    [
      'medications',
      'Medication reminders',
      'Which medications, when the reminders are.',
      true,
    ],
    [
      'appointments',
      'Appointments',
      'Upcoming appointments, and the questions for them.',
      true,
    ],
    ['symptoms', 'Symptoms', 'Symptoms being tracked, and what was recorded.', true],
    ['reports', 'Health reports', 'Health summaries prepared for an appointment.', true],
    [
      'safety_alerts',
      'Safety alerts',
      'Safety alerts raised about them, and whether each has been acknowledged.',
      true,
    ],
    ['communication', 'Family messages', 'Sending and receiving family messages.', true],
    [
      'routines',
      'Routines',
      'Daily routines and whether they are being done. Tasks, alarms and ' +
        'personal reminders stay private.',
      true,
    ],
    [
      'general_health_summary',
      'Health summary',
      'How many conditions, medications and symptoms are recorded.',
      true,
    ],
  ];
  return rows.map(([key, label, description, hasData]) => ({
    key,
    allowed: granted[key] === true,
    label,
    description,
    has_data: hasData,
  }));
}

export function caregiverFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const granted = (overrides.granted as Record<string, boolean>) ?? {
    medications: true,
    appointments: true,
    communication: true,
  };
  const permissions = permissionRowsFixture(granted);
  const base = {
    id: 'relationship-1',
    invited_name: 'Ayesha',
    role: 'family',
    role_label: 'Family',
    status: 'active',
    invite_email: 'ayesha@example.test',
    invite_phone: null,
    invite_expires_at: null,
    accepted_at: '2026-09-20T10:00:00Z',
    revoked_at: null,
    created_at: '2026-09-19T10:00:00Z',
    permissions,
    granted_count: permissions.filter((row) => row.allowed).length,
  };
  const { granted: _granted, ...rest } = overrides;
  return { ...base, ...rest };
}

export function supportedProfileFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    relationship_id: 'relationship-1',
    profile_id: 'profile-2',
    profile_name: 'Mum',
    role: 'family',
    role_label: 'Family',
    granted: ['medications', 'appointments', 'communication'],
    notifications: {
      messages: true,
      appointment_updates: true,
      suggestion_outcomes: true,
      safety_alerts: false,
    },
    accepted_at: '2026-09-20T10:00:00Z',
    ...overrides,
  };
}

export function careSuggestionFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const diff = {
    subject: 'Metformin',
    current: '7:00 PM',
    proposed: '8:00 PM',
    target_missing: false,
    ...((overrides.diff as Record<string, unknown>) ?? {}),
  };
  const { diff: _diff, ...rest } = overrides;
  return {
    id: 'suggestion-1',
    action_type: 'change_medication_reminder_time',
    action_label: 'Change a medication reminder time',
    category: 'medications',
    status: 'pending',
    diff,
    caregiver_name: 'Ayesha',
    created_at: '2026-09-28T09:00:00Z',
    reviewed_at: null,
    decline_note: null,
    ...rest,
  };
}

export function familyMessageFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'message-1',
    message_type: 'text',
    side: 'caregiver',
    text: 'How did you sleep?',
    check_in_code: null,
    created_at: '2026-09-28T08:00:00Z',
    read_at: null,
    client_message_id: null,
    ...overrides,
  };
}

export function familyThreadFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'thread-1',
    relationship_id: 'relationship-1',
    with_name: 'Ayesha',
    unread: 0,
    last_message: null,
    last_message_at: null,
    ...overrides,
  };
}

export function emergencyContactFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'contact-1',
    name: 'Bilal',
    phone: '+447700900111',
    relationship_label: 'Son',
    priority: 1,
    is_active: true,
    has_account: false,
    ...overrides,
  };
}

/**
 * The caregiver's home.
 *
 * Every section defaults to **null**, which is what PRD 9 section 18 means: the
 * server omits a category the caregiver was not granted, and a test that wants
 * one present has to say so. A fixture that defaulted them to `[]` would make
 * every leak test pass for the wrong reason.
 */
export function caregiverHomeFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-2',
    profile_name: 'Mum',
    role: 'family',
    role_label: 'Family',
    granted: ['medications'],
    granted_without_data: [],
    medications: null,
    adherence: null,
    doses_remaining_today: null,
    doses_overdue: null,
    appointments: null,
    symptoms: null,
    reports: null,
    // Null, not `[]`: a caregiver who was not granted `routines` must not be
    // able to tell from the response whether this person has any
    // (PRD 9, section 18; PRD 12, section 16).
    routines: null,
    health_counts: null,
    unread_messages: null,
    pending_suggestions: 0,
    calling_available: false,
    ...overrides,
  };
}

export function careSummaryFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    caregiver_count: 0,
    pending_invitation_count: 0,
    pending_suggestion_count: 0,
    unread_message_count: 0,
    emergency_contact_count: 0,
    ...overrides,
  };
}

export function invitationPreviewFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const granted = (overrides.granted as Record<string, boolean>) ?? {
    medications: true,
    appointments: true,
  };
  const permissions = permissionRowsFixture(granted);
  const { granted: _granted, ...rest } = overrides;
  return {
    invited_name: 'Ayesha',
    profile_name: 'Ada',
    role: 'family',
    role_label: 'Family',
    permissions,
    will_access: permissions
      .filter((row) => row.allowed)
      .map((row) => row.label as string),
    will_not_access: permissions
      .filter((row) => !row.allowed)
      .map((row) => row.label as string),
    expires_at: '2026-10-05T10:00:00Z',
    ...rest,
  };
}

// --- PRD 10: safety monitoring, SOS and escalation --------------------------

/**
 * The seven capabilities, with the states every deployment today reports.
 *
 * Written out rather than generated, because what a test is usually checking
 * is that the screen says "not set up in this build" -- and a generator that
 * defaulted everything to `available` would make those tests pass for the
 * wrong reason (PRD 10, sections 64 and 106).
 */
export function capabilityRowsFixture(
  overrides: Partial<Record<string, string>> = {}
): Record<string, unknown>[] {
  const states: Record<string, string> = {
    manual_sos: 'available',
    in_app_safety_checks: 'available',
    caregiver_in_app_alerts: 'available',
    push_delivery: 'not_configured',
    sms_delivery: 'not_configured',
    audio_calling: 'not_configured',
    robot_detection: 'not_connected',
    ...overrides,
  };
  const labels: Record<string, string> = {
    manual_sos: 'Emergency request',
    in_app_safety_checks: 'Safety check-in prompts',
    caregiver_in_app_alerts: 'In-app alerts for caregivers',
    push_delivery: 'Push notifications',
    sms_delivery: 'Text messages',
    audio_calling: 'Audio calling',
    robot_detection: 'Automatic detection by the robot',
  };
  const stateLabels: Record<string, string> = {
    available: 'Available',
    not_configured: 'Not set up in this build',
    not_connected: 'Not connected yet',
    unavailable: 'Not available',
  };
  return Object.keys(labels).map((key) => ({
    key,
    state: states[key],
    label: labels[key],
    state_label: stateLabels[states[key] as string],
  }));
}

export function monitoringSessionFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'session-1',
    status: 'active',
    started_at: '2026-10-02T18:00:00Z',
    ends_at: '2026-10-02T19:00:00Z',
    duration_mode: '1_hour',
    timezone: 'Europe/London',
    response_timeout_seconds: 45,
    second_prompt_enabled: false,
    second_prompt_timeout_seconds: 20,
    ended_at: null,
    end_reason: null,
    ...overrides,
  };
}

export function escalationAttemptFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'attempt-1',
    recipient_label: 'Ayesha',
    is_caregiver: true,
    priority: 0,
    channel: 'in_app',
    status: 'attempted',
    failure_code: null,
    attempted_at: '2026-10-02T18:42:00Z',
    line: 'In-app alert created for Ayesha.',
    ...overrides,
  };
}

export function safetyEventFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'event-1',
    event_type: 'manual_sos',
    event_label: 'Emergency request',
    triggered_at: '2026-10-02T18:42:00Z',
    status: 'escalated',
    resolution: null,
    resolution_label: null,
    escalation_outcome: 'partial',
    escalation_outcome_label: 'Some steps were taken and some are not available',
    user_response: null,
    false_positive: null,
    description: 'You asked Nura for help.',
    no_response_seconds: null,
    no_response_label: null,
    response_deadline_at: null,
    second_prompt_deadline_at: null,
    escalation_started_at: '2026-10-02T18:42:00Z',
    resolved_at: null,
    false_positive_reason: null,
    attempts: [
      escalationAttemptFixture(),
      escalationAttemptFixture({
        id: 'attempt-2',
        recipient_label: 'Spouse',
        is_caregiver: false,
        priority: 1,
        channel: 'voice_call_future',
        status: 'not_configured',
        failure_code: 'calling_not_configured',
        line: 'Phone call for Spouse: not set up in this build.',
      }),
    ],
    alert_count: 1,
    ...overrides,
  };
}

/** A check-in waiting for an answer (PRD 10, section 23). */
export function safetyCheckFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return safetyEventFixture({
    id: 'event-check',
    event_type: 'possible_fall',
    event_label: 'Possible fall',
    status: 'checking_user',
    escalation_outcome: null,
    escalation_outcome_label: null,
    escalation_started_at: null,
    description: 'Something was observed that may have been a fall.',
    response_deadline_at: '2026-10-02T18:42:45Z',
    attempts: [],
    alert_count: 0,
    ...overrides,
  });
}

export function safetyStatusFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    monitoring: null,
    monitoring_sentence: 'Safety Monitoring is off.',
    active_event: null,
    emergency_mode: false,
    capabilities: capabilityRowsFixture(),
    emergency_contact_count: 0,
    no_contacts_warning:
      'No emergency contacts are set up. Nura can still check on you and record what happened, but it has nobody to reach.',
    no_providers_warning:
      'External notifications and calling are not set up in this build. Nura can record what happened and show it in the app, but it cannot reach anybody for you.',
    detection_notice: null,
    check_prompt: 'Nura noticed something unusual. Ada, are you okay?',
    ...overrides,
  };
}

export function safetyAlertFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'alert-1',
    safety_event_id: 'event-1',
    event_type: 'manual_sos',
    event_label: 'Emergency request',
    triggered_at: '2026-10-02T18:42:00Z',
    created_at: '2026-10-02T18:42:00Z',
    read_at: null,
    acknowledged_at: null,
    event_status: 'escalated',
    event_resolution: null,
    escalation_outcome: 'partial',
    sentence: 'Nura recorded emergency request at 2 Oct, 6:42 PM. Please check on them.',
    ...overrides,
  };
}

// --- PRD 11: the robot's display and companion behaviour ---------------------

/** A claimed robot, as `/api/v1/devices` sends one. */
export function robotDeviceFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'device-1',
    hardware_id: 'NURA-DEADBEEF0001',
    display_name: 'Nura',
    device_type: 'xiao-esp32-s3',
    firmware_version: '0.1.0',
    provisioning_status: 'claimed',
    connection_status: 'online',
    last_seen_at: new Date().toISOString(),
    claimed_at: new Date(Date.now() - 86_400_000).toISOString(),
    setup_completed_at: new Date(Date.now() - 86_400_000).toISOString(),
    introduced_at: null,
    owner_profile_id: 'profile-1',
    created_at: new Date(Date.now() - 86_400_000).toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

/**
 * The twelve capability rows, with a working screen and nothing else.
 *
 * The most optimistic thing this project has any right to simulate (PRD 11,
 * section 12): a panel that answered, and no speaker, microphone, camera or
 * button anywhere.
 */
export function robotCapabilityRowsFixture(
  states: Record<string, string> = {}
): Record<string, unknown>[] {
  const defaults: Record<string, string> = {
    display: 'available',
    display_text: 'available',
    display_animation: 'available',
    speaker: 'not_connected',
    tts: 'not_connected',
    audio_playback: 'not_connected',
    microphone: 'not_connected',
    wake_word: 'unavailable',
    camera: 'not_connected',
    camera_detection: 'unavailable',
    buttons: 'not_connected',
    touch: 'not_connected',
  };
  const labels: Record<string, string> = {
    display: 'Screen',
    display_text: 'Text on screen',
    display_animation: 'Animation',
    speaker: 'Speaker',
    tts: 'Spoken words',
    audio_playback: 'Sounds and chimes',
    microphone: 'Microphone',
    wake_word: 'Listening for its name',
    camera: 'Camera',
    camera_detection: 'Camera detection',
    buttons: 'Buttons',
    touch: 'Touch screen',
  };
  const stateLabels: Record<string, string> = {
    available: 'Working',
    unavailable: 'Not fitted',
    not_verified: 'Not tested yet',
    not_connected: 'Not reported',
  };
  const resolved = { ...defaults, ...states };
  return Object.keys(defaults).map((key) => ({
    key,
    state: resolved[key],
    reported_state: resolved[key],
    label: labels[key],
    state_label: stateLabels[resolved[key] as string],
    source: resolved[key] === 'not_connected' ? 'default' : 'device_report',
    reported_at: resolved[key] === 'not_connected' ? null : new Date().toISOString(),
    firmware_version: resolved[key] === 'not_connected' ? null : '0.1.0',
    stale: false,
  }));
}

/** The `/capabilities` body, with the derived booleans the screens read. */
export function robotCapabilitiesFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const rows =
    (overrides.capabilities as Record<string, unknown>[] | undefined) ??
    robotCapabilityRowsFixture();
  const state = (key: string): string =>
    (rows.find((row) => row.key === key)?.state as string) ?? 'not_connected';
  const available = (key: string): boolean => state(key) === 'available';
  return {
    device_id: 'device-1',
    capabilities: rows,
    display_available: available('display'),
    text_available: available('display') && available('display_text'),
    animation_available: available('display_animation'),
    audio_available:
      available('speaker') || available('audio_playback') || available('tts'),
    speech_available: available('speaker') && available('tts'),
    input_available: available('buttons') || available('touch'),
    hardware_note:
      'The Nura robot has not been built. Everything here is ready for it, and nothing here has run on a screen or a speaker.',
    ...overrides,
  };
}

/** The `/presentation-preferences` body, at section 104's defaults. */
export function presentationPreferencesFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    device_id: 'device-1',
    brightness: 70,
    volume: 40,
    // Null means "follow my accessibility setting" (sections 30 and 105).
    reduced_motion: null,
    effective_reduced_motion: false,
    medication_privacy_level: 'private',
    read_medications_aloud: false,
    read_messages_aloud: false,
    read_assistant_aloud: false,
    sleep_screen_mode: 'dim',
    face_animation_enabled: true,
    family_message_display_enabled: true,
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

/** One presentation-history row (section 96). */
export function presentationFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  const type =
    (overrides.presentation_type as string | undefined) ?? 'medication_reminder';
  const status = (overrides.status as string | undefined) ?? 'sent';
  const kinds: Record<string, string> = {
    face_state: 'Companion face',
    info_card: 'Information',
    medication_reminder: 'Medication reminder',
    appointment_reminder: 'Appointment reminder',
    family_message: 'Family message',
    assistant_response: 'Nura reply',
    safety_check: 'Safety check',
    safety_status: 'Safety status',
    emergency_status: 'Emergency status',
    system_status: 'System status',
    setup_code: 'Pairing code',
  };
  const statuses: Record<string, string> = {
    queued: 'waiting',
    sent: 'sent to Nura',
    acknowledged: 'received by Nura',
    displayed: 'on screen',
    completed: 'shown',
    expired: 'expired',
    failed: 'could not be shown',
    cancelled: 'withdrawn',
    not_supported: 'not supported on this Nura',
  };
  return {
    id: 'presentation-1',
    presentation_type: type,
    status,
    layout: 'REMINDER',
    source: 'medication',
    priority: 40,
    title: 'Medication',
    // The privacy-filtered summary: a private reminder reads as this
    // everywhere, including here (section 22).
    summary: 'Reminder due',
    sensitive: false,
    created_at: new Date().toISOString(),
    available_at: new Date().toISOString(),
    expires_at: null,
    sent_at: new Date().toISOString(),
    displayed_at: null,
    completed_at: null,
    ack_state: null,
    failure_code: null,
    cancel_reason: null,
    line: `${kinds[type]} — ${statuses[status]}`,
    ...overrides,
  };
}

/** The `/robot-status` body (sections 46 and 65). */
export function robotStatusFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    device_id: 'device-1',
    display_name: 'Nura',
    connection_status: 'online',
    last_seen_at: new Date().toISOString(),
    mode: 'companion',
    mode_label: 'Companion',
    face: 'idle',
    queue_depth: 1,
    // Null in every deployment: no physical robot has acknowledged anything.
    current: null,
    setup_complete: true,
    offline_note: null,
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
  /** Raw `/appointments` items, in wire format. */
  appointments?: Record<string, unknown>[];
  /** The `appointments` block of `/api/v1/today`. Null for no profile. */
  todayAppointments?: Record<string, unknown> | null;
  /** Raw question rows, across every appointment. */
  appointmentQuestions?: Record<string, unknown>[];
  /** Raw report rows, across every appointment. */
  appointmentReports?: Record<string, unknown>[];
  /** The `/prepare` response. */
  preparation?: Record<string, unknown>;
  /** Items for the Important Today section. */
  important?: Record<string, unknown>[];
  /** Raw `/assistant/conversations` items, in wire format. */
  conversations?: Record<string, unknown>[];
  /** Raw message rows, across every conversation. */
  conversationMessages?: Record<string, unknown>[];
  /** The `/assistant/preferences` body. */
  assistantPreferences?: Record<string, unknown>;
  /** Raw `/assistant/memories` items. */
  memories?: Record<string, unknown>[];
  /** Prompts the Nura tab should show. */
  assistantPrompts?: Record<string, unknown>[];
  /** False for a deployment with no model provider configured. */
  assistantAvailable?: boolean;
  /** What a sent message comes back as. */
  assistantSend?: AssistantSendResult;
  /** Raw `/caregivers` items, in wire format. */
  caregivers?: Record<string, unknown>[];
  /** Raw `/caregiver-suggestions` items. */
  careSuggestions?: Record<string, unknown>[];
  /** Raw `/family/threads` items. */
  familyThreads?: Record<string, unknown>[];
  /** Raw message rows, across every thread. */
  familyMessages?: Record<string, unknown>[];
  /** Raw `/emergency-contacts` items, in priority order. */
  emergencyContacts?: Record<string, unknown>[];
  /** The `/care/home` body, for Caregiver Mode. */
  caregiverHome?: Record<string, unknown>;
  /** The `/care-summary` body. */
  careSummary?: Record<string, unknown>;
  /** The `/caregiver/profiles` items -- the people this account supports. */
  supportedProfiles?: Record<string, unknown>[];
  /** The invitation an `/caregiver-invitations/{token}` lookup returns. */
  invitationPreview?: Record<string, unknown> | null;
  /** The `/safety/status` body (PRD 10, sections 59 and 60). */
  safetyStatus?: Record<string, unknown>;
  /** Raw `/safety/events` items, newest first. */
  safetyEvents?: Record<string, unknown>[];
  /** Raw `/care/safety-alerts` items, for a caregiver. */
  safetyAlerts?: Record<string, unknown>[];
  /** The `/devices/{id}/capabilities` body (PRD 11, sections 10 and 122). */
  robotCapabilities?: Record<string, unknown>;
  /** The `/devices/{id}/presentation-preferences` body (section 48). */
  robotPreferences?: Record<string, unknown>;
  /** Raw `/devices/{id}/presentation-history` items, newest first (section 96). */
  robotPresentations?: Record<string, unknown>[];
  /** The `/devices/{id}/robot-status` body (section 46). */
  robotStatus?: Record<string, unknown>;
  /** Raw `/tasks` items, in wire format (PRD 12, section 52). */
  tasks?: Record<string, unknown>[];
  /** Raw `/reminders` items. */
  reminders?: Record<string, unknown>[];
  /** Raw `/reminder-occurrences` items. */
  occurrences?: Record<string, unknown>[];
  /** Raw `/alarms` items. */
  alarms?: Record<string, unknown>[];
  /** Raw `/routines` items. */
  routines?: Record<string, unknown>[];
  /** The `/daily-life/summary` body, and the `daily_life` block of Today. */
  dailyLife?: Record<string, unknown>;
  /** The `/assistant/external-capabilities` body (section 57). */
  externalCapabilities?: Record<string, unknown>;
  /** Raw `/care/routines` items, for Caregiver Mode (section 56). */
  careRoutines?: Record<string, unknown>[];
  /** The `/privacy/summary` body (PRD 13, section 4). */
  privacySummary?: Record<string, unknown>;
  /** Raw `/privacy/export` items, newest first (PRD 13, section 43). */
  exports?: Record<string, unknown>[];
  /** The `/privacy/delete-request` body (PRD 13, section 44). */
  deletionInventory?: Record<string, unknown>;
  /** The `/privacy/delete-confirm` body. */
  deletionResult?: Record<string, unknown>;
  healthSetup?: { status: string; step: string | null; blood_type: string | null };
  /** Status code to answer the health endpoints with. */
  healthStatus?: number;
}

// --- PRD 13: privacy, export and deletion ------------------------------------

/**
 * One capability row, in wire format.
 *
 * The privacy hub shows rows from three different maps -- PRD 10's safety,
 * PRD 11's robot, PRD 12's external -- and all three arrive in this shape, so
 * one fixture covers them.
 */
export function capabilityLineFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    key: 'display',
    label: 'Screen',
    state: 'not_verified',
    state_label: 'Not tested yet',
    ...overrides,
  };
}

export function dataExportFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'export-1',
    status: 'ready',
    status_label: 'Ready to download',
    requested_at: '2026-10-12T12:00:00Z',
    generated_at: '2026-10-12T12:00:01Z',
    expires_at: '2026-10-13T12:00:01Z',
    byte_size: 48_210,
    file_count: 11,
    schema_version: 1,
    included_categories: [
      'account',
      'health',
      'assistant',
      'caregiver',
      'safety',
      'productivity',
      'device',
      'media',
    ],
    excluded_categories: ['audit'],
    failure_reason: null,
    downloadable: true,
    ...overrides,
  };
}

/**
 * The hub's body.
 *
 * Every sentence here is one the real server sends, copied verbatim, because
 * the screens render the server's prose rather than their own (PRD 13,
 * sections 5, 9, 10 and 36) -- and a fixture with invented wording would let a
 * test pass against copy the product does not have.
 */
export function privacySummaryFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    assistant_mode: 'normal',
    privacy_mode: false,
    privacy_mode_note:
      'Privacy Mode is off. Nura may start a conversation or suggest something to remember.',
    privacy_mode_limit:
      'Privacy Mode changes how Nura behaves in the app. It is not a hardware switch, and it does not claim to turn off a microphone or a camera.',
    microphone_note:
      'Nura does not listen. There is no voice input anywhere in the app, so it has never asked for microphone access.',
    camera_note:
      'Nura does not watch. The only camera use is choosing or taking a photo for a symptom, which happens in your phone-s own picker.',
    photo_permission_note:
      'Choosing a symptom photo asks your phone for permission at the moment you choose it, and Nura keeps the photo in private storage.',
    robot_input_capabilities: [],
    memory_count: 2,
    active_memory_count: 2,
    conversation_count: 3,
    caregivers: [],
    safety_monitoring_active: false,
    safety_capabilities: [
      capabilityLineFixture({
        key: 'manual_sos',
        label: 'Emergency request',
        state: 'available',
        state_label: 'Available',
      }),
      capabilityLineFixture({
        key: 'push_delivery',
        label: 'Push notifications',
        state: 'not_configured',
        state_label: 'Not set up in this build',
      }),
    ],
    robot_linked: false,
    robot_capabilities: [],
    robot_previews: [],
    external_capabilities: [
      capabilityLineFixture({
        key: 'weather',
        label: 'Weather',
        state: 'not_configured',
        state_label: 'Live weather is not configured in this build.',
      }),
      capabilityLineFixture({
        key: 'news',
        label: 'News',
        state: 'not_configured',
        state_label: 'Live news access is not configured in this build.',
      }),
      capabilityLineFixture({
        key: 'external_calendar',
        label: 'External calendar',
        state: 'not_configured',
        state_label: 'I can add that to Nura, but an external calendar is not connected.',
      }),
    ],
    latest_export: null,
    export_note:
      'A single private file holding everything recorded on this profile, plus your symptom photos and report documents.',
    export_privacy_note:
      'The file stays private to you and is not emailed anywhere. Nura keeps it for a day so you can download it, then deletes it.',
    deletion_warning:
      'This cannot be undone. Everything recorded on this profile is removed from Nura.',
    deletion_keeps:
      'Your sign-in stays, so you can still open Nura. Any other profile on this account is untouched.',
    deletion_reauth_limitation:
      'Nura cannot ask you for your password again: it never receives one.',
    data_categories: [
      'account',
      'health',
      'assistant',
      'caregiver',
      'safety',
      'productivity',
      'device',
      'media',
      'audit',
    ],
    security_statements: [
      'Your sign-in is verified on Nura-s server, never trusted from the app.',
      'Photos and documents are served only through an authenticated request.',
    ],
    build_honesty_note:
      'Nura has not yet been tested on a physical phone or a physical robot.',
    ...overrides,
  };
}

export function deletionInventoryFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    profile_name: 'Ayesha',
    rows: { medical_conditions: 2, tasks: 4, daily_checkins: 9 },
    row_total: 15,
    file_count: 2,
    caregiver_count: 1,
    device_count: 0,
    other_profile_count: 0,
    title: 'Delete this profile-s data',
    warning:
      'This cannot be undone. Everything recorded on this profile is removed from Nura.',
    keeps: 'Your sign-in stays, so you can still open Nura.',
    reauth_limitation:
      'Nura cannot ask you for your password again: it never receives one.',
    confirm_prompt: 'Type the phrase below to confirm.',
    confirmation_phrase: 'DELETE MY NURA DATA',
    ...overrides,
  };
}

export function deletionResultFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    rows_deleted: 15,
    files_deleted: 2,
    files_missing: 0,
    caregivers_revoked: 1,
    devices_unlinked: 0,
    completed_at: '2026-10-12T12:05:00Z',
    other_profiles_remaining: 0,
    ...overrides,
  };
}

export function exportListBody(
  exports: Record<string, unknown>[]
): Record<string, unknown> {
  return {
    exports,
    note: 'A single private file holding everything recorded on this profile.',
    privacy_note:
      'The file stays private to you and is not emailed anywhere. Nura keeps it for a day.',
    secrets_note:
      'It contains no passwords, sign-in tokens, invitation links or device secrets.',
    sections: [
      'profile',
      'health',
      'medications',
      'symptoms',
      'appointments',
      'assistant',
      'caregivers',
      'safety',
      'daily-life',
      'devices',
    ],
  };
}

/** Records what the stubbed backend was asked to do, for assertions. */
// --- PRD 12: tasks, reminders, alarms and routines ---------------------------

export function taskFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'task-1',
    profile_id: 'profile-1',
    title: 'Call the physiotherapist',
    notes: null,
    status: 'open',
    status_label: 'To do',
    priority: 'normal',
    priority_label: 'Normal',
    due_at: '2026-09-13T16:00:00Z',
    due_local_date: '2026-09-13',
    timezone: 'UTC',
    due_label: 'Today, 4:00 PM',
    overdue: false,
    source: 'user',
    source_label: 'Added by you',
    completed_at: null,
    archived_at: null,
    cancelled_at: null,
    content_updated_at: '2026-09-13T12:00:00Z',
    status_changed_at: '2026-09-13T12:00:00Z',
    created_at: '2026-09-13T12:00:00Z',
    updated_at: '2026-09-13T12:00:00Z',
    ...overrides,
  };
}

export function occurrenceFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'occurrence-1',
    reminder_id: 'reminder-1',
    profile_id: 'profile-1',
    title: 'Ring the bank',
    body: null,
    scheduled_for: '2026-09-13T18:00:00Z',
    local_date: '2026-09-13',
    status: 'scheduled',
    status_label: 'Coming up',
    window: 'upcoming',
    action_at: null,
    snoozed_until: null,
    snooze_count: 0,
    can_snooze: true,
    created_at: '2026-09-13T12:00:00Z',
    updated_at: '2026-09-13T12:00:00Z',
    ...overrides,
  };
}

export function reminderFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'reminder-1',
    profile_id: 'profile-1',
    title: 'Ring the bank',
    body: null,
    recurrence: 'daily',
    recurrence_label: 'Every day',
    schedule_label: 'Every day at 6:00 PM',
    timezone: 'UTC',
    start_date: '2026-09-13',
    end_date: null,
    time_of_day: '18:00:00',
    weekdays: null,
    day_of_month: null,
    status: 'active',
    status_label: 'On',
    notification_enabled: true,
    notification_note: null,
    source: 'user',
    source_label: 'Added by you',
    paused_at: null,
    next_occurrence_at: '2026-09-13T18:00:00Z',
    created_at: '2026-09-13T12:00:00Z',
    updated_at: '2026-09-13T12:00:00Z',
    occurrences: [occurrenceFixture()],
    ...overrides,
  };
}

export function alarmFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'alarm-1',
    profile_id: 'profile-1',
    label: 'Wake up',
    time_of_day: '07:00:00',
    timezone: 'UTC',
    recurrence: 'daily',
    recurrence_label: 'Every day',
    schedule_label: 'Every day at 7:00 AM',
    weekdays: null,
    on_date: null,
    enabled: true,
    sound_key: 'default',
    sound_label: 'Default',
    vibration: true,
    next_fire_at: '2026-09-14T07:00:00Z',
    source: 'user',
    created_at: '2026-09-13T12:00:00Z',
    updated_at: '2026-09-13T12:00:00Z',
    ...overrides,
  };
}

/**
 * Section 11's sentence, as the server sends it.
 *
 * Part of every alarm list response, which is what stops a client shipping an
 * alarm screen without it. **No alarm has ever fired on a physical phone.**
 */
export const ALARM_LIMITATION =
  'Alarms are scheduled as phone notifications. Nura has never been run on a ' +
  'physical phone, so whether one actually wakes you has not been tested.';

export function runFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'run-1',
    routine_id: 'routine-1',
    profile_id: 'profile-1',
    routine_title: 'Morning routine',
    scheduled_for: '2026-09-13T07:30:00Z',
    local_date: '2026-09-13',
    status: 'scheduled',
    status_label: 'Coming up',
    started_at: null,
    completed_at: null,
    total_steps: 3,
    completed_steps: 0,
    skipped_steps: 0,
    progress_label: '0 of 3 complete. Next: Drink water',
    next_step_id: 'step-1',
    next_step_title: 'Drink water',
    completions: [],
    ...overrides,
  };
}

export function routineFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    id: 'routine-1',
    profile_id: 'profile-1',
    title: 'Morning routine',
    description: null,
    schedule_type: 'daily',
    schedule_label: 'Every day at 7:30 AM',
    timezone: 'UTC',
    time_of_day: '07:30:00',
    weekdays: null,
    start_date: '2026-09-13',
    end_date: null,
    status: 'active',
    status_label: 'On',
    paused_at: null,
    source: 'user',
    source_label: 'Added by you',
    steps: [
      {
        id: 'step-1',
        routine_id: 'routine-1',
        title: 'Drink water',
        position: 0,
        optional: false,
      },
      {
        id: 'step-2',
        routine_id: 'routine-1',
        title: 'Stretch for 5 minutes',
        position: 1,
        optional: false,
      },
      {
        id: 'step-3',
        routine_id: 'routine-1',
        title: 'Review Today',
        position: 2,
        optional: true,
      },
    ],
    today_run: runFixture(),
    created_at: '2026-09-13T12:00:00Z',
    updated_at: '2026-09-13T12:00:00Z',
    ...overrides,
  };
}

export function dailyLifeFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    local_date: '2026-09-13',
    tasks: { due_today: 0, overdue: 0, open_total: 0 },
    reminders: { due_today: 0, due_now: 0 },
    routines: { due_today: 0, in_progress: 0, completed_today: 0 },
    next_alarm_at: null,
    alarm_count: 0,
    summary_label: 'Nothing due today.',
    has_anything: false,
    ...overrides,
  };
}

/** Section 29's map, with every external key `not_configured`. */
export function externalCapabilitiesFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    profile_id: 'profile-1',
    capabilities: [
      { key: 'tasks', state: 'available', label: 'Tasks', sentence: 'Tasks: available' },
      {
        key: 'reminders',
        state: 'available',
        label: 'Reminders',
        sentence: 'Reminders: available',
      },
      {
        key: 'alarms',
        state: 'available',
        label: 'Alarms',
        sentence: 'Alarms: available',
      },
      {
        key: 'routines',
        state: 'available',
        label: 'Routines',
        sentence: 'Routines: available',
      },
      {
        key: 'weather',
        state: 'not_configured',
        label: 'Weather',
        sentence: 'Live weather is not configured in this build.',
      },
      {
        key: 'news',
        state: 'not_configured',
        label: 'News',
        sentence: 'Live news access is not configured in this build.',
      },
      {
        key: 'external_calendar',
        state: 'not_configured',
        label: 'External calendar',
        sentence: 'I can add that to Nura, but an external calendar is not connected.',
      },
    ],
    external: {
      weather: 'not_configured',
      news: 'not_configured',
      external_calendar: 'not_configured',
    },
    any_external_configured: false,
    ...overrides,
  };
}

export function caregiverRoutineFixture(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    routine_id: 'routine-1',
    title: 'Morning routine',
    schedule_label: 'Every day at 7:30 AM',
    step_count: 3,
    paused: false,
    today_status: 'scheduled',
    today_done: 0,
    today_total: 3,
    today_progress_label: '0 of 3 complete',
    ...overrides,
  };
}

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
      appointments: initial.appointments ?? [],
      todayAppointments: initial.todayAppointments ?? NO_APPOINTMENTS,
      appointmentQuestions: initial.appointmentQuestions ?? [],
      appointmentReports: initial.appointmentReports ?? [],
      preparation: initial.preparation ?? preparationFixture(),
      important: initial.important ?? [],
      conversations: initial.conversations ?? [],
      conversationMessages: initial.conversationMessages ?? [],
      assistantPreferences: initial.assistantPreferences ?? assistantPreferencesFixture(),
      memories: initial.memories ?? [],
      assistantPrompts: initial.assistantPrompts ?? [],
      assistantAvailable: initial.assistantAvailable ?? true,
      assistantSend: initial.assistantSend ?? {},
      caregivers: initial.caregivers ?? [],
      safetyStatus: initial.safetyStatus ?? safetyStatusFixture(),
      safetyEvents: initial.safetyEvents ?? [],
      safetyAlerts: initial.safetyAlerts ?? [],
      robotCapabilities: initial.robotCapabilities ?? robotCapabilitiesFixture(),
      robotPreferences: initial.robotPreferences ?? presentationPreferencesFixture(),
      robotPresentations: initial.robotPresentations ?? [],
      robotStatus: initial.robotStatus ?? robotStatusFixture(),
      careSuggestions: initial.careSuggestions ?? [],
      familyThreads: initial.familyThreads ?? [],
      familyMessages: initial.familyMessages ?? [],
      emergencyContacts: initial.emergencyContacts ?? [],
      caregiverHome: initial.caregiverHome ?? caregiverHomeFixture(),
      careSummary: initial.careSummary ?? careSummaryFixture(),
      supportedProfiles: initial.supportedProfiles ?? [],
      invitationPreview:
        initial.invitationPreview === undefined ? null : initial.invitationPreview,
      tasks: initial.tasks ?? [],
      reminders: initial.reminders ?? [],
      occurrences: initial.occurrences ?? [],
      alarms: initial.alarms ?? [],
      routines: initial.routines ?? [],
      dailyLife: initial.dailyLife ?? dailyLifeFixture(),
      externalCapabilities: initial.externalCapabilities ?? externalCapabilitiesFixture(),
      privacySummary: initial.privacySummary ?? privacySummaryFixture(),
      exports: initial.exports ?? [],
      deletionInventory: initial.deletionInventory ?? deletionInventoryFixture(),
      deletionResult: initial.deletionResult ?? deletionResultFixture(),
      careRoutines: initial.careRoutines ?? [],
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
      notify_caregiver_messages: true,
      notify_suggestion_requests: true,
      notify_appointment_suggestions: true,
      notify_routine_suggestions: true,
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
    appointments: stub.state.todayAppointments,
    daily_life: stub.state.dailyLife,
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

    // --- PRD 10: safety monitoring, SOS and escalation --------------------

    const safetyMatch =
      /^\/api\/v1\/profiles\/[^/]+\/safety\/([^/?]+)(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (safetyMatch) {
      const resource = safetyMatch[1] ?? '';
      const first = safetyMatch[3];
      const second = safetyMatch[5];

      if (resource === 'status') return jsonResponse(stub.state.safetyStatus);

      if (resource === 'capabilities') {
        const rows =
          (stub.state.safetyStatus.capabilities as
            Record<string, unknown>[] | undefined) ?? capabilityRowsFixture();
        const available = rows.some(
          (row) =>
            ['push_delivery', 'sms_delivery', 'audio_calling'].includes(
              row.key as string
            ) && row.state === 'available'
        );
        return jsonResponse({
          capabilities: rows,
          external_delivery_available: available,
          warning: available ? null : stub.state.safetyStatus.no_providers_warning,
        });
      }

      if (resource === 'monitoring' && first === 'start') {
        const session = monitoringSessionFixture({
          duration_mode: (body?.duration_mode as string) ?? '1_hour',
          response_timeout_seconds: (body?.response_timeout_seconds as number) ?? 45,
          second_prompt_enabled: body?.second_prompt_enabled === true,
        });
        stub.state.safetyStatus = {
          ...stub.state.safetyStatus,
          monitoring: session,
          monitoring_sentence: 'Safety Monitoring is on until 7:00 PM.',
          detection_notice:
            'Safety Monitoring is on. Automatic detection by the robot is not connected yet, so Nura will not notice anything by itself. You can still ask for help at any time.',
        };
        return jsonResponse(session, 201);
      }

      if (resource === 'monitoring' && first === 'stop') {
        stub.state.safetyStatus = {
          ...stub.state.safetyStatus,
          monitoring: null,
          monitoring_sentence: 'Safety Monitoring is off.',
          detection_notice: null,
        };
        return jsonResponse(stub.state.safetyStatus);
      }

      if (resource === 'sos') {
        const event = safetyEventFixture();
        stub.state.safetyEvents = [event, ...stub.state.safetyEvents];
        stub.state.safetyStatus = {
          ...stub.state.safetyStatus,
          active_event: event,
          emergency_mode: true,
        };
        return jsonResponse(event, 201);
      }

      if (resource === 'events' && first !== undefined && second !== undefined) {
        const existing =
          stub.state.safetyEvents.find((row) => row.id === first) ??
          (stub.state.safetyStatus.active_event as Record<string, unknown> | null) ??
          safetyEventFixture({ id: first });
        if (second === 'respond') {
          const response = (body?.response as string) ?? 'im_okay';
          const updated: Record<string, unknown> =
            response === 'need_help'
              ? { ...existing, status: 'escalated', user_response: response }
              : {
                  ...existing,
                  status: 'resolved',
                  user_response: response,
                  resolution:
                    response === 'false_alarm' ? 'false_alarm' : 'user_confirmed_ok',
                  resolution_label:
                    response === 'false_alarm'
                      ? 'Marked as a false alarm'
                      : 'You said you were okay',
                  false_positive: response === 'false_alarm' ? true : null,
                };
          stub.state.safetyEvents = stub.state.safetyEvents.map((row) =>
            row.id === updated.id ? updated : row
          );
          stub.state.safetyStatus = {
            ...stub.state.safetyStatus,
            active_event: response === 'need_help' ? updated : null,
            emergency_mode: response === 'need_help',
          };
          return jsonResponse(updated);
        }
        if (second === 'cancel') {
          const updated: Record<string, unknown> = {
            ...existing,
            status: 'cancelled',
            resolution: 'cancelled_by_user',
            resolution_label: 'Cancelled',
          };
          stub.state.safetyEvents = stub.state.safetyEvents.map((row) =>
            row.id === updated.id ? updated : row
          );
          stub.state.safetyStatus = {
            ...stub.state.safetyStatus,
            active_event: null,
            emergency_mode: false,
          };
          return jsonResponse(updated);
        }
        if (second === 'false-alarm') {
          const falsePositive = body?.false_positive === true;
          const updated: Record<string, unknown> = {
            ...existing,
            false_positive: falsePositive,
            false_positive_reason: falsePositive
              ? ((body?.reason as string | null) ?? null)
              : null,
          };
          stub.state.safetyEvents = stub.state.safetyEvents.map((row) =>
            row.id === updated.id ? updated : row
          );
          return jsonResponse(updated);
        }
      }

      if (resource === 'events' && first !== undefined) {
        const found = stub.state.safetyEvents.find((row) => row.id === first);
        if (found === undefined) {
          return jsonResponse(
            { detail: { code: 'safety_event_not_found', message: 'Not found.' } },
            404
          );
        }
        return jsonResponse(found);
      }

      if (resource === 'events') {
        return jsonResponse({ events: stub.state.safetyEvents });
      }
    }

    // --- PRD 9: caregivers, family messaging and emergency contacts -------

    if (path.startsWith('/api/v1/caregiver-permissions')) {
      return jsonResponse(permissionRowsFixture());
    }

    if (path.startsWith('/api/v1/caregiver/profiles')) {
      return jsonResponse({ profiles: stub.state.supportedProfiles });
    }

    const invitationMatch =
      /^\/api\/v1\/caregiver-invitations\/([^/?]+)(\/([^/?]+))?/.exec(path);
    if (invitationMatch) {
      const action = invitationMatch[3];
      if (stub.state.invitationPreview === null) {
        return jsonResponse(
          { detail: { code: 'invitation_not_found', message: 'Not found.' } },
          404
        );
      }
      if (action === 'accept') {
        const accepted = supportedProfileFixture();
        stub.state.supportedProfiles = [...stub.state.supportedProfiles, accepted];
        // Single-use: the same token does not work twice (PRD 9, section 13).
        stub.state.invitationPreview = null;
        return jsonResponse(accepted);
      }
      if (action === 'decline') {
        stub.state.invitationPreview = null;
        return jsonResponse(null, 204);
      }
      return jsonResponse(stub.state.invitationPreview);
    }

    const careMatch =
      /^\/api\/v1\/profiles\/[^/]+\/(caregivers|caregiver-suggestions|care-summary|care|family|emergency-contacts)(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (careMatch) {
      const resource = careMatch[1] ?? '';
      const first = careMatch[3];
      const second = careMatch[5];
      const third = careMatch[7];

      if (resource === 'care-summary') {
        return jsonResponse(stub.state.careSummary);
      }

      if (resource === 'care' && first === 'home') {
        return jsonResponse(stub.state.caregiverHome);
      }

      // PRD 10, sections 83 and 97. Listing is what marks an alert read, so
      // the stub does it too -- a test of the unread badge has to be able to
      // see the difference.
      if (resource === 'care' && first === 'safety-alerts' && second === undefined) {
        const unread = stub.state.safetyAlerts.filter(
          (row) => row.read_at === null
        ).length;
        const body = {
          alerts: stub.state.safetyAlerts,
          unread_count: unread,
        };
        stub.state.safetyAlerts = stub.state.safetyAlerts.map((row) => ({
          ...row,
          read_at: row.read_at ?? '2026-10-02T18:50:00Z',
        }));
        return jsonResponse(body);
      }

      if (resource === 'care' && first === 'safety-alerts' && third === 'acknowledge') {
        const updated = stub.state.safetyAlerts.map((row) =>
          row.id === second
            ? {
                ...row,
                acknowledged_at: '2026-10-02T18:55:00Z',
                read_at: row.read_at ?? '2026-10-02T18:55:00Z',
              }
            : row
        );
        stub.state.safetyAlerts = updated;
        return jsonResponse(updated.find((row) => row.id === second) ?? updated[0]);
      }

      if (resource === 'care' && first === 'notifications') {
        const [existing] = stub.state.supportedProfiles;
        const updated = {
          ...(existing ?? supportedProfileFixture()),
          notifications: {
            ...(((existing ?? supportedProfileFixture()).notifications as Record<
              string,
              boolean
            >) ?? {}),
            ...((body?.notifications as Record<string, boolean>) ?? {}),
          },
        };
        stub.state.supportedProfiles = [updated];
        return jsonResponse(updated);
      }

      if (resource === 'caregivers') {
        if (first === 'invitations' && method === 'POST') {
          const granted = (body?.permissions as Record<string, boolean>) ?? {};
          const created = caregiverFixture({
            id: `relationship-${stub.state.caregivers.length + 1}`,
            invited_name: (body?.invited_name as string) ?? 'Someone',
            role: (body?.role as string) ?? 'family',
            status: 'pending',
            accepted_at: null,
            invite_expires_at: '2026-10-05T10:00:00Z',
            granted,
          });
          stub.state.caregivers = [...stub.state.caregivers, created];
          return jsonResponse(
            {
              caregiver: created,
              // The only copy, returned once -- Nura cannot send it
              // (PRD 9, sections 12 and 13).
              token: 'nci_test-token',
              expires_at: '2026-10-05T10:00:00Z',
              delivery: 'share_manually',
            },
            201
          );
        }

        if (first !== undefined && second === 'permissions') {
          if (method === 'PATCH') {
            stub.state.caregivers = stub.state.caregivers.map((row) => {
              if (row.id !== first) return row;
              const sent = (body?.permissions as Record<string, boolean>) ?? {};
              const permissions = (row.permissions as Record<string, unknown>[]).map(
                (permission) =>
                  permission.key !== undefined &&
                  Object.prototype.hasOwnProperty.call(sent, permission.key as string)
                    ? { ...permission, allowed: sent[permission.key as string] }
                    : permission
              );
              return {
                ...row,
                permissions,
                granted_count: permissions.filter((p) => p.allowed).length,
              };
            });
            const updated = stub.state.caregivers.find((row) => row.id === first);
            return jsonResponse(updated ?? caregiverFixture());
          }
          const row = stub.state.caregivers.find((item) => item.id === first);
          return jsonResponse(row?.permissions ?? permissionRowsFixture());
        }

        if (first !== undefined && method === 'PATCH') {
          stub.state.caregivers = stub.state.caregivers.map((row) =>
            row.id === first
              ? { ...row, role: body?.role, role_label: 'Primary caregiver' }
              : row
          );
          const updated = stub.state.caregivers.find((row) => row.id === first);
          return jsonResponse(updated ?? caregiverFixture());
        }

        if (first !== undefined && method === 'DELETE') {
          stub.state.caregivers = stub.state.caregivers.filter((row) => row.id !== first);
          return jsonResponse(null, 204);
        }

        return jsonResponse({
          caregivers: stub.state.caregivers,
          has_any: stub.state.caregivers.length > 0,
        });
      }

      if (resource === 'caregiver-suggestions') {
        if (first !== undefined && second === 'approve') {
          stub.state.careSuggestions = stub.state.careSuggestions.map((row) =>
            row.id === first ? { ...row, status: 'approved' } : row
          );
          const row = stub.state.careSuggestions.find((item) => item.id === first);
          return jsonResponse(row ?? careSuggestionFixture({ status: 'approved' }));
        }
        if (first !== undefined && second === 'decline') {
          stub.state.careSuggestions = stub.state.careSuggestions.map((row) =>
            row.id === first
              ? { ...row, status: 'declined', decline_note: body?.note ?? null }
              : row
          );
          const row = stub.state.careSuggestions.find((item) => item.id === first);
          return jsonResponse(row ?? careSuggestionFixture({ status: 'declined' }));
        }
        if (first !== undefined && second === 'cancel') {
          stub.state.careSuggestions = stub.state.careSuggestions.map((row) =>
            row.id === first ? { ...row, status: 'cancelled' } : row
          );
          const row = stub.state.careSuggestions.find((item) => item.id === first);
          return jsonResponse(row ?? careSuggestionFixture({ status: 'cancelled' }));
        }
        if (method === 'POST') {
          const created = careSuggestionFixture({
            id: `suggestion-${stub.state.careSuggestions.length + 1}`,
            action_type: body?.action_type ?? 'change_medication_reminder_time',
          });
          stub.state.careSuggestions = [...stub.state.careSuggestions, created];
          return jsonResponse(created, 201);
        }
        return jsonResponse({
          suggestions: stub.state.careSuggestions,
          pending_count: stub.state.careSuggestions.filter(
            (row) => row.status === 'pending'
          ).length,
        });
      }

      if (resource === 'family' && first === 'threads') {
        if (second !== undefined && third === 'messages') {
          if (method === 'POST') {
            const created = familyMessageFixture({
              id: `message-${stub.state.familyMessages.length + 1}`,
              side: 'primary_user',
              message_type: (body?.message_type as string) ?? 'text',
              text:
                body?.message_type === 'check_in'
                  ? 'I’m okay.'
                  : ((body?.text as string) ?? null),
              check_in_code: (body?.check_in_code as string) ?? null,
              client_message_id: (body?.client_message_id as string) ?? null,
            });
            // Idempotent on the client id, like the real endpoint
            // (PRD 9, sections 72 and 74).
            const already = stub.state.familyMessages.find(
              (row) =>
                row.client_message_id !== null &&
                row.client_message_id === created.client_message_id
            );
            if (already !== undefined) return jsonResponse(already, 201);
            stub.state.familyMessages = [...stub.state.familyMessages, created];
            return jsonResponse(created, 201);
          }
          const thread =
            stub.state.familyThreads.find((row) => row.id === second) ??
            familyThreadFixture();
          return jsonResponse({
            thread,
            messages: stub.state.familyMessages,
          });
        }
        if (method === 'POST') {
          const created = familyThreadFixture({
            id: `thread-${stub.state.familyThreads.length + 1}`,
            relationship_id: (body?.relationship_id as string) ?? 'relationship-1',
          });
          stub.state.familyThreads = [...stub.state.familyThreads, created];
          return jsonResponse(created, 201);
        }
        return jsonResponse({ threads: stub.state.familyThreads });
      }

      if (resource === 'family' && first === 'calls') {
        // Section 38: never a successful call. Every deployment refuses.
        return jsonResponse(
          {
            detail: {
              code: 'calling_not_configured',
              message: 'Audio calling is not set up on this server yet.',
            },
          },
          503
        );
      }

      if (resource === 'emergency-contacts') {
        if (first === 'reorder' && method === 'POST') {
          const order = (body?.order as string[]) ?? [];
          const byId = new Map(
            stub.state.emergencyContacts.map((row) => [row.id as string, row])
          );
          const reordered = order
            .map((id) => byId.get(id))
            .filter((row): row is Record<string, unknown> => row !== undefined);
          const rest = stub.state.emergencyContacts.filter(
            (row) => !order.includes(row.id as string)
          );
          // The server renumbers, so the stub does too (PRD 9, section 45).
          stub.state.emergencyContacts = [...reordered, ...rest].map((row, index) => ({
            ...row,
            priority: index + 1,
          }));
          return jsonResponse({ contacts: stub.state.emergencyContacts });
        }
        if (first !== undefined && method === 'PATCH') {
          stub.state.emergencyContacts = stub.state.emergencyContacts.map((row) =>
            row.id === first ? { ...row, ...(body ?? {}) } : row
          );
          const updated = stub.state.emergencyContacts.find((row) => row.id === first);
          return jsonResponse(updated ?? emergencyContactFixture());
        }
        if (first !== undefined && method === 'DELETE') {
          stub.state.emergencyContacts = stub.state.emergencyContacts
            .filter((row) => row.id !== first)
            .map((row, index) => ({ ...row, priority: index + 1 }));
          return jsonResponse(null, 204);
        }
        if (method === 'POST') {
          const created = emergencyContactFixture({
            id: `contact-${stub.state.emergencyContacts.length + 1}`,
            name: (body?.name as string) ?? 'Someone',
            phone: (body?.phone as string) ?? null,
            relationship_label: (body?.relationship_label as string) ?? null,
            priority: stub.state.emergencyContacts.length + 1,
            is_active: body?.is_active !== false,
          });
          stub.state.emergencyContacts = [...stub.state.emergencyContacts, created];
          return jsonResponse(created, 201);
        }
        return jsonResponse({ contacts: stub.state.emergencyContacts });
      }
    }

    const assistantMatch =
      /^\/api\/v1\/profiles\/[^/]+\/assistant\/([^/?]+)(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (assistantMatch) {
      const resource = assistantMatch[1] ?? '';
      const first = assistantMatch[3];
      const second = assistantMatch[5];
      const third = assistantMatch[7];

      if (resource === 'home') {
        return jsonResponse({
          profile_id: 'profile-1',
          assistant_available: stub.state.assistantAvailable,
          preferences: stub.state.assistantPreferences,
          recent_conversations: stub.state.conversations.slice(0, 5),
          prompts: stub.state.assistantPrompts,
          memory_count: stub.state.memories.filter((m) => m.is_active !== false).length,
        });
      }

      if (resource === 'prompts' && first === 'dismiss') {
        stub.state.assistantPrompts = stub.state.assistantPrompts.filter(
          (prompt) =>
            !(prompt.kind === body?.kind && prompt.subject_key === body?.subject_key)
        );
        return jsonResponse(null, 204);
      }

      if (resource === 'preferences') {
        if (method === 'PATCH' && body) {
          // Mirrors the server: a preset writes the five dials, and anything
          // sent alongside it wins (PRD 8, section 62).
          const presets: Record<string, Record<string, string>> = {
            gentle: {
              warmth: 'high',
              humour: 'low',
              talkativeness: 'medium',
              proactivity: 'low',
              reminder_firmness: 'low',
              verbosity: 'balanced',
            },
            friendly: {
              warmth: 'high',
              humour: 'medium',
              talkativeness: 'high',
              proactivity: 'medium',
              reminder_firmness: 'medium',
              verbosity: 'balanced',
            },
            focused: {
              warmth: 'low',
              humour: 'low',
              talkativeness: 'low',
              proactivity: 'low',
              reminder_firmness: 'high',
              verbosity: 'concise',
            },
            professional: {
              warmth: 'medium',
              humour: 'low',
              talkativeness: 'low',
              proactivity: 'medium',
              reminder_firmness: 'high',
              verbosity: 'balanced',
            },
          };
          const instructions = body.custom_instructions;
          // The one refusal the screens branch on (PRD 8, section 26).
          if (
            typeof instructions === 'string' &&
            /diagnose|system prompt|ignore previous|other users/i.test(instructions)
          ) {
            return jsonResponse(
              { detail: { code: 'unsafe_instruction', message: 'Refused.' } },
              400
            );
          }
          const preset =
            typeof body.personality_preset === 'string'
              ? presets[body.personality_preset]
              : undefined;
          stub.state.assistantPreferences = {
            ...stub.state.assistantPreferences,
            ...(preset ?? {}),
            ...(body as Record<string, unknown>),
          };
          const chosen = String(stub.state.assistantPreferences.personality_preset);
          const values = presets[chosen] ?? {};
          stub.state.assistantPreferences.matches_preset = Object.entries(values).every(
            ([key, value]) => stub.state.assistantPreferences[key] === value
          );
        }
        return jsonResponse(stub.state.assistantPreferences);
      }

      if (resource === 'memories') {
        if (method === 'POST') {
          const content = String(body?.content ?? '');
          if (/diagnose|system prompt|ignore previous|other users/i.test(content)) {
            return jsonResponse(
              { detail: { code: 'unsafe_instruction', message: 'Refused.' } },
              400
            );
          }
          const created = memoryFixture({
            id: `memory-${stub.state.memories.length + 1}`,
            ...(body as Record<string, unknown>),
          });
          stub.state.memories = [created, ...stub.state.memories];
          return jsonResponse(created, 201);
        }
        if (method === 'PATCH' && first) {
          stub.state.memories = stub.state.memories.map((entry) =>
            entry.id === first
              ? { ...entry, ...(body as Record<string, unknown>) }
              : entry
          );
          return jsonResponse(
            stub.state.memories.find((entry) => entry.id === first) ?? {}
          );
        }
        if (method === 'DELETE' && first) {
          stub.state.memories = stub.state.memories.filter((entry) => entry.id !== first);
          return jsonResponse(null, 204);
        }
        return jsonResponse({
          profile_id: 'profile-1',
          memories: stub.state.memories,
          max_memories: 50,
        });
      }

      if (resource === 'conversations') {
        const conversation = stub.state.conversations.find((entry) => entry.id === first);

        if (method === 'POST' && first === undefined) {
          const created = conversationFixture({
            id: `conversation-${stub.state.conversations.length + 1}`,
            title: 'New conversation',
            message_count: 0,
            last_message_at: null,
          });
          stub.state.conversations = [created, ...stub.state.conversations];
          return jsonResponse(created, 201);
        }

        // `.../{id}/messages/{messageId}/confirm`
        if (second === 'messages' && third !== undefined && method === 'POST') {
          const confirmed = body?.confirmed === true;
          stub.state.conversationMessages = stub.state.conversationMessages.map(
            (entry) =>
              entry.id === third
                ? {
                    ...entry,
                    pending_action: {
                      ...(entry.pending_action as Record<string, unknown>),
                      state: confirmed ? 'confirmed' : 'cancelled',
                    },
                  }
                : entry
          );
          const outcome = messageFixture({
            id: `message-outcome-${stub.state.conversationMessages.length + 1}`,
            conversation_id: first,
            message_type: 'notice',
            content: confirmed
              ? 'Added \u201cAsk about dizziness\u201d to your questions.'
              : 'No problem \u2014 nothing was changed.',
          });
          stub.state.conversationMessages = [...stub.state.conversationMessages, outcome];
          return jsonResponse({
            message: stub.state.conversationMessages.find((entry) => entry.id === third),
            outcome,
          });
        }

        if (second === 'messages' && method === 'POST') {
          const send = stub.state.assistantSend;
          const index = stub.state.conversationMessages.length;
          const userMessage = messageFixture({
            id: `message-user-${index + 1}`,
            conversation_id: first,
            role: 'user',
            content: String(body?.content ?? ''),
            meta: { model: null, tools: [], safety_mode: 'normal' },
          });
          const replyContent =
            send.replyContent === undefined ? 'All right.' : send.replyContent;
          const reply =
            replyContent === null
              ? null
              : messageFixture({
                  id: `message-reply-${index + 2}`,
                  conversation_id: first,
                  role: 'assistant',
                  content: replyContent,
                  safety_mode: send.safetyMode ?? 'normal',
                  pending_action: send.pendingAction ?? null,
                });
          stub.state.conversationMessages = [
            ...stub.state.conversationMessages,
            userMessage,
            ...(reply === null ? [] : [reply]),
          ];
          return jsonResponse(
            {
              conversation: conversation ?? conversationFixture({ id: first }),
              user_message: userMessage,
              reply,
              failure: send.failure ?? null,
              failure_message: send.failureMessage ?? null,
              memory_suggestion: send.memorySuggestion ?? null,
              suggest_symptom_log: send.suggestSymptomLog === true,
            },
            201
          );
        }

        if (first !== undefined && method === 'PATCH') {
          stub.state.conversations = stub.state.conversations.map((entry) =>
            entry.id === first
              ? { ...entry, ...(body as Record<string, unknown>) }
              : entry
          );
          const updated = stub.state.conversations.find((entry) => entry.id === first);
          return jsonResponse({
            ...updated,
            archived_at: body?.archived === true ? '2026-09-28T10:00:00Z' : null,
          });
        }

        if (first !== undefined && method === 'DELETE') {
          stub.state.conversations = stub.state.conversations.filter(
            (entry) => entry.id !== first
          );
          stub.state.conversationMessages = stub.state.conversationMessages.filter(
            (entry) => entry.conversation_id !== first
          );
          return jsonResponse(null, 204);
        }

        if (first !== undefined) {
          return jsonResponse({
            conversation: conversation ?? conversationFixture({ id: first }),
            messages: stub.state.conversationMessages.filter(
              (entry) => entry.conversation_id === first
            ),
          });
        }

        const archived = path.includes('include_archived=true');
        return jsonResponse({
          profile_id: 'profile-1',
          conversations: archived
            ? stub.state.conversations
            : stub.state.conversations.filter((entry) => entry.archived_at === null),
          assistant_available: stub.state.assistantAvailable,
        });
      }
    }

    const appointmentMatch =
      /^\/api\/v1\/profiles\/[^/]+\/appointments(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?(\/([^/?]+))?/.exec(
        path
      );
    if (appointmentMatch) {
      const first = appointmentMatch[2];
      const second = appointmentMatch[4];
      const third = appointmentMatch[6];

      const find = (id: string | undefined) =>
        stub.state.appointments.find((entry) => entry.id === id);

      const withChildren = (entry: Record<string, unknown> | undefined) =>
        entry === undefined
          ? {}
          : {
              ...entry,
              questions: stub.state.appointmentQuestions.filter(
                (question) => question.appointment_id === entry.id
              ),
              reports: stub.state.appointmentReports
                .filter((report) => report.appointment_id === entry.id)
                .map(({ snapshot: _snapshot, ...rest }) => rest),
              question_count: stub.state.appointmentQuestions.filter(
                (question) => question.appointment_id === entry.id
              ).length,
              report_count: stub.state.appointmentReports.filter(
                (report) => report.appointment_id === entry.id
              ).length,
            };

      if (first === 'summary') {
        const upcoming = stub.state.appointments.filter(
          (entry) => entry.status === 'scheduled'
        );
        return jsonResponse({
          profile_id: 'profile-1',
          upcoming_count: upcoming.length,
          past_count: stub.state.appointments.filter(
            (entry) => entry.status === 'completed'
          ).length,
          cancelled_count: stub.state.appointments.filter(
            (entry) => entry.status === 'cancelled'
          ).length,
          has_appointments: stub.state.appointments.length > 0,
          next: stub.state.todayAppointments?.next ?? null,
        });
      }

      if (second === 'prepare') {
        return jsonResponse({
          ...stub.state.preparation,
          appointment: withChildren(find(first)),
          questions: stub.state.appointmentQuestions.filter(
            (question) => question.appointment_id === first
          ),
        });
      }

      // `.../{id}/questions/order` is a PUT; `.../{id}/questions/{qid}` a PATCH
      // or DELETE. Matched before the plain questions branch below.
      if (second === 'questions' && third === 'order' && method === 'PUT') {
        const order: string[] = (body?.question_ids as string[]) ?? [];
        stub.state.appointmentQuestions = [
          ...order
            .map((id) => stub.state.appointmentQuestions.find((q) => q.id === id))
            .filter((q): q is Record<string, unknown> => q !== undefined),
          ...stub.state.appointmentQuestions.filter((q) => !order.includes(String(q.id))),
        ].map((question, index) => ({ ...question, position: index }));
        return jsonResponse(stub.state.appointmentQuestions);
      }

      if (second === 'questions' && third !== undefined) {
        if (method === 'DELETE') {
          stub.state.appointmentQuestions = stub.state.appointmentQuestions.filter(
            (question) => question.id !== third
          );
          return jsonResponse(null, 204);
        }
        stub.state.appointmentQuestions = stub.state.appointmentQuestions.map(
          (question) =>
            question.id === third
              ? { ...question, ...(body as Record<string, unknown>) }
              : question
        );
        return jsonResponse(
          stub.state.appointmentQuestions.find((question) => question.id === third) ?? {}
        );
      }

      if (second === 'questions') {
        if (method === 'POST') {
          const created = questionFixture({
            id: `question-${stub.state.appointmentQuestions.length + 1}`,
            appointment_id: first,
            position: stub.state.appointmentQuestions.length,
            ...(body as Record<string, unknown>),
          });
          stub.state.appointmentQuestions = [...stub.state.appointmentQuestions, created];
          return jsonResponse({ question: created, created: true }, 201);
        }
        return jsonResponse(
          stub.state.appointmentQuestions.filter(
            (question) => question.appointment_id === first
          )
        );
      }

      if (second === 'reports' && third === undefined) {
        if (method === 'POST') {
          const sent = (body ?? {}) as Record<string, unknown>;
          const created = reportFixture({
            id: `report-${stub.state.appointmentReports.length + 1}`,
            appointment_id: first,
            version: stub.state.appointmentReports.length + 1,
            include_appendix:
              (sent.selection as Record<string, unknown> | undefined)
                ?.include_appendix === true,
          });
          stub.state.appointmentReports = [...stub.state.appointmentReports, created];
          return jsonResponse({ report: created, created: true }, 201);
        }
        return jsonResponse(
          stub.state.appointmentReports
            .filter((report) => report.appointment_id === first)
            .map(({ snapshot: _snapshot, ...rest }) => rest)
            .reverse()
        );
      }

      if (second === 'reports' && third !== undefined) {
        if (method === 'DELETE') {
          stub.state.appointmentReports = stub.state.appointmentReports.filter(
            (report) => report.id !== third
          );
          return jsonResponse(null, 204);
        }
        return jsonResponse(
          stub.state.appointmentReports.find((report) => report.id === third) ?? {}
        );
      }

      if (second === 'cancel' && method === 'POST') {
        stub.state.appointments = stub.state.appointments.map((entry) =>
          entry.id === first
            ? { ...entry, status: 'cancelled', cancelled_at: '2026-09-28T10:00:00Z' }
            : entry
        );
        return jsonResponse(withChildren(find(first)));
      }

      if (second === 'complete' && method === 'POST') {
        stub.state.appointments = stub.state.appointments.map((entry) =>
          entry.id === first
            ? {
                ...entry,
                status: 'completed',
                completed_at: '2026-09-28T10:00:00Z',
                ...(body as Record<string, unknown>),
              }
            : entry
        );
        return jsonResponse(withChildren(find(first)));
      }

      if (second === 'reopen' && method === 'POST') {
        stub.state.appointments = stub.state.appointments.map((entry) =>
          entry.id === first ? { ...entry, status: 'scheduled' } : entry
        );
        return jsonResponse(withChildren(find(first)));
      }

      if (method === 'POST' && first === undefined) {
        const sent = (body ?? {}) as Record<string, unknown>;
        const created = appointmentFixture({
          id: `appointment-${stub.state.appointments.length + 1}`,
          title: String(sent.title ?? 'Appointment'),
          appointment_type: sent.appointment_type ?? 'other',
          scheduled_at: sent.scheduled_at ?? '2026-10-02T14:30:00Z',
          timezone: sent.timezone ?? 'UTC',
          location_name: sent.location_name ?? null,
          address: sent.address ?? null,
          phone: sent.phone ?? null,
          notes: sent.notes ?? null,
          reminders_enabled: sent.reminders_enabled !== false,
          clinician: null,
        });
        stub.state.appointments = [...stub.state.appointments, created];
        return jsonResponse({ appointment: created, created: true }, 201);
      }

      if (method === 'PATCH' && first !== undefined) {
        stub.state.appointments = stub.state.appointments.map((entry) =>
          entry.id === first ? { ...entry, ...(body as Record<string, unknown>) } : entry
        );
        return jsonResponse(withChildren(find(first)));
      }

      if (method === 'DELETE' && first !== undefined) {
        stub.state.appointments = stub.state.appointments.filter(
          (entry) => entry.id !== first
        );
        return jsonResponse(null, 204);
      }

      if (first !== undefined) {
        return jsonResponse(withChildren(find(first)));
      }

      // The list, with the scope the screens actually send.
      const query = url.slice(url.indexOf('?') + 1);
      let rows = stub.state.appointments;
      if (url.includes('?') && query.includes('scope=upcoming')) {
        rows = rows.filter((entry) => entry.status === 'scheduled');
      } else if (url.includes('?') && query.includes('scope=past')) {
        rows = rows.filter((entry) => entry.status === 'completed');
      } else if (url.includes('?') && query.includes('scope=cancelled')) {
        rows = rows.filter((entry) => entry.status === 'cancelled');
      }
      return jsonResponse(rows.map((entry) => withChildren(entry)));
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

    // --- PRD 12: tasks, reminders, alarms and routines -------------------
    //
    // Matched on the resource after the profile id, like the robot block
    // below: every one of these is already scoped to a profile the signed-in
    // account owns, and a stub that re-checked the id would be testing the
    // stub.
    const dailyMatch =
      /^\/api\/v1\/profiles\/[^/]+\/(tasks|reminders|reminder-occurrences|alarms|routines|routine-runs|daily-life|care\/routines)(\/[^?]*)?/.exec(
        path
      );
    if (dailyMatch) {
      const resource = dailyMatch[1] ?? '';
      const rest = (dailyMatch[2] ?? '').replace(/^\//, '');

      if (resource === 'tasks') {
        // The create branch is guarded on there being no trailing path, so a
        // POST to `tasks/{id}/complete` is not mistaken for a new task.
        if (method === 'POST' && rest.length === 0) {
          const created = taskFixture({
            id: `task-${stub.state.tasks.length + 1}`,
            ...(body ?? {}),
          });
          stub.state.tasks = [...stub.state.tasks, created];
          return jsonResponse({ task: created, applied: true, created: true }, 201);
        }
        if (rest.endsWith('/complete') || rest.endsWith('/reopen')) {
          const taskId = rest.split('/')[0];
          const done = rest.endsWith('/complete');
          stub.state.tasks = stub.state.tasks.map((task) =>
            task.id === taskId
              ? {
                  ...task,
                  status: done ? 'completed' : 'open',
                  status_label: done ? 'Done' : 'To do',
                  completed_at: done ? '2026-09-13T12:30:00Z' : null,
                }
              : task
          );
          const task = stub.state.tasks.find((row) => row.id === taskId) ?? taskFixture();
          return jsonResponse({ task, applied: true, created: false });
        }
        if (method === 'PATCH') {
          const taskId = rest.split('/')[0];
          stub.state.tasks = stub.state.tasks.map((task) =>
            task.id === taskId ? { ...task, ...(body ?? {}) } : task
          );
          const task = stub.state.tasks.find((row) => row.id === taskId) ?? taskFixture();
          return jsonResponse({ task, applied: true, created: false });
        }
        if (method === 'DELETE') {
          const taskId = rest.split('/')[0];
          stub.state.tasks = stub.state.tasks.filter((task) => task.id !== taskId);
          return jsonResponse(null, 204);
        }
        const open = stub.state.tasks.filter((task) => task.status === 'open');
        return jsonResponse({
          tasks: stub.state.tasks,
          open_count: open.length,
          overdue_count: open.filter((task) => task.overdue === true).length,
        });
      }

      if (resource === 'reminders') {
        if (method === 'POST' && rest.length === 0) {
          const created = reminderFixture({
            id: `reminder-${stub.state.reminders.length + 1}`,
          });
          stub.state.reminders = [...stub.state.reminders, created];
          return jsonResponse({ reminder: created, created: true }, 201);
        }
        if (rest.endsWith('/pause') || rest.endsWith('/resume')) {
          const paused = rest.endsWith('/pause');
          const reminderId = rest.split('/')[0];
          stub.state.reminders = stub.state.reminders.map((reminder) =>
            reminder.id === reminderId
              ? {
                  ...reminder,
                  status: paused ? 'paused' : 'active',
                  status_label: paused ? 'Paused' : 'On',
                }
              : reminder
          );
          return jsonResponse(
            stub.state.reminders.find((row) => row.id === reminderId) ?? reminderFixture()
          );
        }
        if (rest.length > 0) {
          return jsonResponse(
            stub.state.reminders.find((row) => row.id === rest.split('/')[0]) ??
              reminderFixture()
          );
        }
        return jsonResponse({
          reminders: stub.state.reminders,
          due_count: stub.state.occurrences.filter(
            (row) => row.window === 'due' || row.window === 'overdue'
          ).length,
        });
      }

      if (resource === 'reminder-occurrences') {
        if (method === 'POST') {
          const occurrenceId = rest.split('/')[0];
          const action = rest.split('/')[1] ?? '';
          const status =
            action === 'complete'
              ? 'completed'
              : action === 'dismiss'
                ? 'dismissed'
                : 'snoozed';
          stub.state.occurrences = stub.state.occurrences.map((row) =>
            row.id === occurrenceId
              ? { ...row, status, status_label: status, window: 'completed' }
              : row
          );
          const occurrence =
            stub.state.occurrences.find((row) => row.id === occurrenceId) ??
            occurrenceFixture();
          return jsonResponse({ occurrence, applied: true });
        }
        return jsonResponse(stub.state.occurrences);
      }

      if (resource === 'alarms') {
        if (method === 'POST') {
          const created = alarmFixture({ id: `alarm-${stub.state.alarms.length + 1}` });
          stub.state.alarms = [...stub.state.alarms, created];
          return jsonResponse({ alarm: created, created: true }, 201);
        }
        if (method === 'PATCH') {
          const alarmId = rest.split('/')[0];
          stub.state.alarms = stub.state.alarms.map((alarm) =>
            alarm.id === alarmId ? { ...alarm, ...(body ?? {}) } : alarm
          );
          return jsonResponse(
            stub.state.alarms.find((row) => row.id === alarmId) ?? alarmFixture()
          );
        }
        if (method === 'DELETE') {
          const alarmId = rest.split('/')[0];
          stub.state.alarms = stub.state.alarms.filter((alarm) => alarm.id !== alarmId);
          return jsonResponse(null, 204);
        }
        return jsonResponse({
          alarms: stub.state.alarms,
          enabled_count: stub.state.alarms.filter((alarm) => alarm.enabled === true)
            .length,
          // Section 11: the sentence is part of the contract, so the stub
          // sends it exactly as the server does.
          limitation: ALARM_LIMITATION,
        });
      }

      if (resource === 'routines') {
        if (method === 'POST' && rest.length === 0) {
          const created = routineFixture({
            id: `routine-${stub.state.routines.length + 1}`,
          });
          stub.state.routines = [...stub.state.routines, created];
          return jsonResponse({ routine: created, created: true }, 201);
        }
        if (rest.endsWith('/pause') || rest.endsWith('/resume')) {
          const paused = rest.endsWith('/pause');
          const routineId = rest.split('/')[0];
          stub.state.routines = stub.state.routines.map((routine) =>
            routine.id === routineId
              ? {
                  ...routine,
                  status: paused ? 'paused' : 'active',
                  status_label: paused ? 'Paused' : 'On',
                }
              : routine
          );
          return jsonResponse(
            stub.state.routines.find((row) => row.id === routineId) ?? routineFixture()
          );
        }
        if (rest.length > 0) {
          return jsonResponse(
            stub.state.routines.find((row) => row.id === rest.split('/')[0]) ??
              routineFixture()
          );
        }
        return jsonResponse({
          routines: stub.state.routines,
          active_count: stub.state.routines.filter((row) => row.status === 'active')
            .length,
        });
      }

      if (resource === 'routine-runs') {
        if (rest === 'today') {
          const runs = stub.state.routines
            .map((routine) => routine.today_run)
            .filter((run): run is Record<string, unknown> => Boolean(run));
          return jsonResponse({ runs });
        }
        if (method === 'POST' || method === 'DELETE') {
          const runId = rest.split('/')[0];
          const routine = stub.state.routines.find(
            (row) => (row.today_run as Record<string, unknown> | null)?.id === runId
          );
          const run =
            (routine?.today_run as Record<string, unknown> | undefined) ?? runFixture();
          if (rest.endsWith('/complete') && !rest.includes('/steps/')) {
            return jsonResponse({
              run: { ...run, status: 'completed', status_label: 'Done' },
              applied: true,
            });
          }
          if (rest.endsWith('/skip')) {
            return jsonResponse({
              run: { ...run, status: 'skipped', status_label: 'Skipped' },
              applied: true,
            });
          }
          const completed = method === 'POST';
          const next = {
            ...run,
            status: completed ? 'in_progress' : 'scheduled',
            status_label: completed ? 'Started' : 'Coming up',
            completed_steps: completed ? 1 : 0,
            progress_label: completed
              ? '1 of 3 complete. Next: Stretch for 5 minutes'
              : '0 of 3 complete. Next: Drink water',
            completions: completed
              ? [
                  {
                    id: 'completion-1',
                    step_id: 'step-1',
                    state: 'completed',
                    state_label: 'Done',
                    completed_at: '2026-09-13T07:35:00Z',
                  },
                ]
              : [],
          };
          stub.state.routines = stub.state.routines.map((row) =>
            row.id === routine?.id ? { ...row, today_run: next } : row
          );
          return jsonResponse(next);
        }
        const runId = rest.split('/')[0];
        const routine = stub.state.routines.find(
          (row) => (row.today_run as Record<string, unknown> | null)?.id === runId
        );
        return jsonResponse(
          (routine?.today_run as Record<string, unknown> | undefined) ?? runFixture()
        );
      }

      if (resource === 'daily-life') {
        return jsonResponse(stub.state.dailyLife);
      }

      if (resource === 'care/routines') {
        return jsonResponse({
          routines: stub.state.careRoutines,
          scope_note: 'Routines only. Tasks, alarms and personal reminders stay private.',
        });
      }
    }

    if (/^\/api\/v1\/profiles\/[^/]+\/assistant\/external-capabilities/.test(path)) {
      return jsonResponse(stub.state.externalCapabilities);
    }

    // --- PRD 13: privacy, export and deletion ---------------------------
    //
    // Before the `/api/v1/profiles` catch-all below, for the reason PRD 12's
    // block is: the catch-all answers a profile body for anything under
    // `/profiles`, so a block placed after it never runs.
    const privacyMatch = /^\/api\/v1\/profiles\/[^/]+\/privacy\/([^/?]+)(\/[^?]*)?/.exec(
      path
    );
    if (privacyMatch) {
      const resource = privacyMatch[1] ?? '';
      const rest = (privacyMatch[2] ?? '').replace(/^\//, '');

      if (resource === 'summary') {
        return jsonResponse(stub.state.privacySummary);
      }

      if (resource === 'export') {
        const existing = stub.state.exports ?? [];
        if (method === 'POST' && rest.length === 0) {
          const created = dataExportFixture({ id: `export-${existing.length + 1}` });
          stub.state.exports = [created, ...existing];
          return jsonResponse(created, 201);
        }
        if (method === 'DELETE' && rest.length > 0) {
          stub.state.exports = existing.filter(
            (entry: Record<string, unknown>) => entry.id !== rest
          );
          return jsonResponse(null, 204);
        }
        if (rest.endsWith('/content')) {
          return new Response('zip bytes', {
            status: 200,
            headers: { 'content-type': 'application/zip' },
          });
        }
        if (rest.length > 0) {
          const found = existing.find(
            (entry: Record<string, unknown>) => entry.id === rest
          );
          return found
            ? jsonResponse(found)
            : jsonResponse({ detail: { code: 'data_export_not_found' } }, 404);
        }
        return jsonResponse(exportListBody(existing));
      }

      if (resource === 'delete-request') {
        return jsonResponse(stub.state.deletionInventory);
      }

      if (resource === 'delete-confirm') {
        // The phrase is checked, because a stub that accepted anything would
        // let a screen ship that never sent it (PRD 13, section 44).
        if (body?.confirmation_phrase !== 'DELETE MY NURA DATA') {
          return jsonResponse({ detail: { code: 'deletion_not_confirmed' } }, 422);
        }
        return jsonResponse(stub.state.deletionResult);
      }

      if (resource === 'conversations') {
        return jsonResponse({
          deleted: 3,
          note: 'Deleting conversations does not touch your health record or what Nura remembers.',
        });
      }
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

    // --- PRD 11: the robot's display and companion behaviour -------------
    //
    // Matched before the plain `/api/v1/devices` list below, and keyed on the
    // trailing segment rather than on the device id: every one of these
    // endpoints is already scoped to a device the signed-in account claimed,
    // and a stub that checked the id would be testing the stub.
    const robotMatch = /^\/api\/v1\/devices\/[^/]+\/([^/?]+)/.exec(path);
    if (robotMatch) {
      const resource = robotMatch[1] ?? '';

      if (resource === 'capabilities') {
        return jsonResponse(stub.state.robotCapabilities);
      }

      if (resource === 'presentation-preferences') {
        if (method === 'PATCH' && body) {
          // Merged rather than replaced, so a PATCH of one switch does not
          // silently reset the others -- and `reduced_motion: null` is kept
          // as null, because null is a value here (sections 30 and 105).
          const merged: Record<string, unknown> = {
            ...stub.state.robotPreferences,
            ...body,
          };
          if ('reduced_motion' in body) {
            merged.effective_reduced_motion = body.reduced_motion === true;
          }
          merged.updated_at = new Date().toISOString();
          stub.state.robotPreferences = merged;
        }
        return jsonResponse(stub.state.robotPreferences);
      }

      if (resource === 'presentation-history') {
        return jsonResponse({ presentations: stub.state.robotPresentations });
      }

      if (resource === 'robot-status') {
        return jsonResponse(stub.state.robotStatus);
      }
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
