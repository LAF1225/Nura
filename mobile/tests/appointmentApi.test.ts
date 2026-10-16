/**
 * The appointment API layer (PRD 7, sections 48-52).
 *
 * Every response is *parsed*, not cast, so these tests are about what happens
 * when the server sends something unexpected as much as when it sends what is
 * expected. Two failure modes matter more than the rest:
 *
 *   - a missing `has_appointments` must not read as "has appointments";
 *   - a missing report `status` must not read as `ready`, because a ready report
 *     is one the app offers to export.
 *
 * It also asserts what is *absent*: no response carries a URL or a storage key
 * for a report's PDF, because there is no public or signed URL for one
 * (PRD 7, section 52).
 */
import {
  cancelAppointment,
  completeAppointment,
  createAppointment,
  createQuestion,
  deleteAppointment,
  deleteReport,
  fetchAppointment,
  fetchAppointments,
  fetchAppointmentSummary,
  fetchPreparation,
  fetchReports,
  generateReport,
  parseAppointment,
  parseReport,
  parseSelection,
  parseSnapshot,
  parseTodayAppointments,
  reorderQuestions,
  reportPdfPath,
  selectionPayload,
  updateAppointment,
} from '../src/features/appointments/api';
import { emptySelection } from '../src/features/appointments/selectionStore';
import {
  appointmentFixture,
  mockBackend,
  preparationFixture,
  reportFixture,
  reportSnapshotFixture,
  signInAt,
} from './helpers';

const PROFILE = 'profile-1';

/** The stub records a body as `unknown`; every read of one narrows it here. */
function sentBody(request: { body: unknown } | undefined): Record<string, any> {
  return (request?.body ?? {}) as Record<string, any>;
}

describe('parsing an appointment', () => {
  it('reads the labels the server rendered', () => {
    const appointment = parseAppointment(appointmentFixture(), '/appointments');

    expect(appointment.title).toBe('Cardiology follow-up');
    expect(appointment.dayLabel).toBe('2 October 2026');
    expect(appointment.timeLabel).toBe('3:30 PM');
    expect(appointment.whenLabel).toBe('2 October 2026 at 3:30 PM');
    expect(appointment.timezone).toBe('Europe/London');
    expect(appointment.clinician?.name).toBe('Dr Ahmed Khan');
  });

  it('falls back safely for an unknown type or status', () => {
    const appointment = parseAppointment(
      appointmentFixture({
        appointment_type: 'astrology',
        status: 'rescheduled',
        preparation_status: 'nearly',
      }),
      '/appointments'
    );

    expect(appointment.appointmentType).toBe('other');
    expect(appointment.status).toBe('scheduled');
    expect(appointment.preparationStatus).toBe('not_started');
  });

  it('treats a missing reminder flag as on rather than off', () => {
    // An appointment whose reminders silently vanished would be worse than one
    // that reminds when the user did not ask.
    const appointment = parseAppointment(
      appointmentFixture({ reminders_enabled: undefined }),
      '/appointments'
    );
    expect(appointment.remindersEnabled).toBe(true);
  });

  it('refuses a body with no id', () => {
    expect(() => parseAppointment({ title: 'Nameless' }, '/appointments')).toThrow();
  });
});

describe('parsing a report', () => {
  it('reads the metadata and the frozen content', () => {
    const report = parseReport(reportFixture(), '/reports');

    expect(report.version).toBe(1);
    expect(report.status).toBe('ready');
    expect(report.pageCount).toBe(1);
    expect(report.fileName).toBe('Nura_Health_Summary_2026-09-28.pdf');
    expect(report.snapshot?.summarySections[0]?.heading).toBe('Recent symptoms');
  });

  it('never reads a missing status as ready', () => {
    const report = parseReport(reportFixture({ status: undefined }), '/reports');
    expect(report.status).toBe('pending');
  });

  it('leaves the snapshot undefined when the server did not send one', () => {
    const report = parseReport(reportFixture({ snapshot: undefined }), '/reports');
    expect(report.snapshot).toBeUndefined();
  });

  it('keeps every line of the frozen content', () => {
    const snapshot = parseSnapshot(reportSnapshotFixture(), '/reports');

    expect(snapshot.title).toBe('Nura Health Summary');
    expect(snapshot.header.patient).toBe('Ada');
    expect(snapshot.footerLines.some((line) => line.includes('not a diagnosis'))).toBe(
      true
    );
    expect(snapshot.summaryCondensed).toBe(false);
  });
});

describe('parsing a selection', () => {
  it('fills every section key, defaulting an absent one to off', () => {
    const selection = parseSelection({ include: { questions: true } });

    expect(selection.include.questions).toBe(true);
    expect(selection.include.medications).toBe(false);
    expect(Object.keys(selection.include).length).toBe(9);
  });

  it('keeps null medication ids as null, meaning "the active ones"', () => {
    expect(parseSelection({ medication_ids: null }).medicationIds).toBeNull();
    expect(parseSelection({ medication_ids: [] }).medicationIds).toEqual([]);
  });
});

describe('parsing the Today block', () => {
  it('reads the next appointment', () => {
    const today = parseTodayAppointments({
      next: {
        appointment_id: 'appointment-1',
        title: 'Cardiology follow-up',
        appointment_type: 'specialist',
        scheduled_at: '2026-10-02T14:30:00Z',
        timezone: 'Europe/London',
        when_label: 'Tomorrow at 3:30 PM',
        relative_day: 'Tomorrow',
        clinician_name: 'Dr Ahmed Khan',
        clinician_specialty: 'Cardiology',
        location_name: 'City Hospital',
        preparation_status: 'in_progress',
        question_count: 3,
        report_count: 0,
      },
      upcoming_count: 2,
      has_appointments: true,
    });

    expect(today?.next?.whenLabel).toBe('Tomorrow at 3:30 PM');
    expect(today?.next?.questionCount).toBe(3);
    expect(today?.upcomingCount).toBe(2);
  });

  it('never reads a missing flag as "has appointments"', () => {
    const today = parseTodayAppointments({ next: null, upcoming_count: 0 });
    expect(today?.hasAppointments).toBe(false);
  });

  it('returns null for an account with no profile', () => {
    expect(parseTodayAppointments(null)).toBeNull();
  });
});

describe('the requests the app sends', () => {
  let backend: ReturnType<typeof mockBackend>;

  beforeEach(() => {
    signInAt('onboarding_complete');
    backend = mockBackend({
      appointments: [appointmentFixture()],
      appointmentReports: [reportFixture()],
    });
  });

  afterEach(() => backend.restore());

  it('nests every path under the profile', async () => {
    await fetchAppointments(PROFILE);
    await fetchAppointment(PROFILE, 'appointment-1');
    await fetchAppointmentSummary(PROFILE);
    await fetchPreparation(PROFILE, 'appointment-1');
    await fetchReports(PROFILE, 'appointment-1');

    for (const request of backend.requests) {
      expect(request.path.startsWith(`/api/v1/profiles/${PROFILE}/appointments`)).toBe(
        true
      );
    }
  });

  it('sends the scope as a query parameter', async () => {
    await fetchAppointments(PROFILE, 'past');
    expect(backend.requests[0]?.path).toContain('scope=past');
  });

  it('sends the period as query parameters', async () => {
    await fetchPreparation(PROFILE, 'appointment-1', {
      preset: 'custom',
      periodStart: '2026-09-01',
      periodEnd: '2026-09-28',
    });

    const path = backend.requests[0]?.path ?? '';
    expect(path).toContain('preset=custom');
    expect(path).toContain('period_start=2026-09-01');
    expect(path).toContain('period_end=2026-09-28');
  });

  it('creates an appointment with its client id', async () => {
    await createAppointment(PROFILE, {
      title: 'Blood test',
      scheduled_at: '2026-10-02T09:00:00.000Z',
      timezone: 'Europe/London',
      appointment_type: 'lab',
      clinician_id: null,
      location_name: null,
      address: null,
      phone: null,
      notes: null,
      reminders_enabled: true,
      client_appointment_id: 'appointment-abc',
    });

    const request = backend.requests[0];
    expect(request?.method).toBe('POST');
    expect(sentBody(request).client_appointment_id).toBe('appointment-abc');
    expect(sentBody(request).title).toBe('Blood test');
  });

  it('cancels and completes through their own routes, never a status patch', async () => {
    await cancelAppointment(PROFILE, 'appointment-1');
    await completeAppointment(PROFILE, 'appointment-1', {
      visit_notes: 'Continue at lower intensity.',
    });
    await updateAppointment(PROFILE, 'appointment-1', { title: 'Renamed' });

    const paths = backend.requests.map((request) => `${request.method} ${request.path}`);
    expect(paths[0]).toContain('POST');
    expect(paths[0]).toContain('/cancel');
    expect(paths[1]).toContain('/complete');
    // The PATCH carries no status at all.
    expect(sentBody(backend.requests[2])).not.toHaveProperty('status');
  });

  it('adds a question with its client id and reorders by the list shown', async () => {
    await createQuestion(PROFILE, 'appointment-1', {
      text: 'Do I need any tests?',
      client_question_id: 'question-abc',
    });
    await reorderQuestions(PROFILE, 'appointment-1', ['question-1']);

    expect(sentBody(backend.requests[0]).client_question_id).toBe('question-abc');
    expect(backend.requests[1]?.method).toBe('PUT');
    expect(sentBody(backend.requests[1]).question_ids).toEqual(['question-1']);
  });

  it('sends the whole selection when generating a report', async () => {
    const selection = {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1'],
      includeAppendix: true,
    };

    await generateReport(PROFILE, 'appointment-1', {
      period_preset: '30_days',
      selection: selectionPayload(selection),
      client_report_id: 'report-abc',
    });

    const body = sentBody(backend.requests[0]);
    expect(body.period_preset).toBe('30_days');
    expect(body.selection.symptom_episode_ids).toEqual(['episode-1']);
    expect(body.selection.include_appendix).toBe(true);
    expect(body.client_report_id).toBe('report-abc');
  });

  it('deletes an appointment and a report version', async () => {
    await deleteAppointment(PROFILE, 'appointment-1');
    await deleteReport(PROFILE, 'appointment-1', 'report-1');

    expect(backend.requests.map((request) => request.method)).toEqual([
      'DELETE',
      'DELETE',
    ]);
  });
});

describe('a report PDF has no public URL', () => {
  it('is fetched from an authenticated path under the profile', () => {
    const path = reportPdfPath(PROFILE, 'appointment-1', 'report-1');

    expect(path).toBe(
      `/api/v1/profiles/${PROFILE}/appointments/appointment-1/reports/report-1/pdf`
    );
    expect(path).not.toContain('http');
    expect(path).not.toContain('token');
    expect(path).not.toContain('signature');
  });

  it('never appears as a URL or a storage key in a parsed report', () => {
    const report = parseReport(reportFixture(), '/reports');
    const text = JSON.stringify(report);

    expect(text).not.toContain('http');
    expect(text).not.toContain('file_storage_key');
    expect(text).not.toContain('reports/');
  });
});

describe('parsing the preparation review', () => {
  it('keeps the counts, the uncertainty and the suggestions', () => {
    const review = parseSelection(preparationFixture().default_selection);
    expect(review.symptomEpisodeIds).toEqual(['episode-1', 'episode-2']);
    expect(review.include.medical_notes).toBe(false);
  });
});
