/**
 * Appointments and questions saved while offline (PRD 7, section 53).
 *
 * The rule under test: **nothing the user typed is silently lost.** A save that
 * cannot reach the backend is written to the device and reported as pending, and
 * every retry carries the same client id so the server answers a replay with the
 * row it already has.
 *
 * The other half is what is *not* queued: a report. PRD 7 section 53 says plainly
 * not to pretend generation succeeded offline, and there is nothing in this module
 * that could.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ApiError } from '../src/services/api/errors';
import {
  clearAllPendingAppointments,
  clearAllPendingQuestions,
  clearPendingAppointment,
  clearPendingQuestion,
  isRetryable,
  loadPendingAppointments,
  loadPendingQuestions,
  pendingForAppointment,
  queueAppointment,
  queueQuestion,
  submitOrQueueAppointment,
  submitOrQueueQuestion,
  syncPending,
} from '../src/features/appointments/pending';
import type {
  PendingAppointment,
  PendingQuestion,
} from '../src/features/appointments/types';
import * as pendingModule from '../src/features/appointments/pending';
import { appointmentFixture, mockBackend, signInAt } from './helpers';

const PROFILE = 'profile-1';

function pendingAppointment(
  overrides: Partial<PendingAppointment> = {}
): PendingAppointment {
  return {
    clientAppointmentId: 'appointment-abc',
    payload: {
      title: 'Cardiology follow-up',
      scheduled_at: '2026-10-02T14:30:00.000Z',
      timezone: 'Europe/London',
      appointment_type: 'specialist',
      clinician_id: null,
      location_name: null,
      address: null,
      phone: null,
      notes: null,
      reminders_enabled: true,
      client_appointment_id: 'appointment-abc',
    },
    savedAt: '2026-09-28T09:00:00.000Z',
    displayTitle: 'Cardiology follow-up',
    ...overrides,
  };
}

function pendingQuestion(overrides: Partial<PendingQuestion> = {}): PendingQuestion {
  return {
    clientQuestionId: 'question-abc',
    appointmentId: 'appointment-1',
    text: 'Do I need any follow-up tests?',
    savedAt: '2026-09-28T09:00:00.000Z',
    ...overrides,
  };
}

/** A fetch that always fails the way a phone with no signal does. */
function offlineFetch(): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new TypeError('Network request failed');
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
});

describe('which failures are worth keeping a record for', () => {
  it('keeps a record through anything that might succeed later', () => {
    for (const kind of [
      'offline',
      'unavailable',
      'timeout',
      'server',
      'unauthorized',
      'configuration',
      'unknown',
    ] as const) {
      expect(isRetryable(new ApiError(kind, 'nope'))).toBe(true);
    }
  });

  it('drops one that would fail the same way forever', () => {
    expect(isRetryable(new ApiError('validation', 'nope'))).toBe(false);
    expect(isRetryable(new ApiError('notFound', 'nope'))).toBe(false);
    expect(isRetryable(new Error('something else'))).toBe(false);
  });
});

describe('the appointment queue', () => {
  it('holds one record per save, keyed by client id', async () => {
    await queueAppointment(pendingAppointment());
    await queueAppointment(pendingAppointment({ displayTitle: 'Renamed' }));

    const records = await loadPendingAppointments();
    expect(records.length).toBe(1);
    expect(records[0]?.displayTitle).toBe('Renamed');
  });

  it('holds two different saves side by side', async () => {
    await queueAppointment(pendingAppointment());
    await queueAppointment(pendingAppointment({ clientAppointmentId: 'appointment-2' }));

    expect((await loadPendingAppointments()).length).toBe(2);
  });

  it('clears one, and all', async () => {
    await queueAppointment(pendingAppointment());
    await queueAppointment(pendingAppointment({ clientAppointmentId: 'appointment-2' }));

    await clearPendingAppointment('appointment-abc');
    expect((await loadPendingAppointments()).length).toBe(1);

    await clearAllPendingAppointments();
    expect(await loadPendingAppointments()).toEqual([]);
  });

  it('drops a corrupted record rather than crashing the screen', async () => {
    await AsyncStorage.setItem(
      'nura.appointments.pending',
      JSON.stringify([{ nonsense: true }, pendingAppointment()])
    );
    expect((await loadPendingAppointments()).length).toBe(1);
  });

  it('survives unparseable storage', async () => {
    await AsyncStorage.setItem('nura.appointments.pending', 'not json');
    expect(await loadPendingAppointments()).toEqual([]);
  });
});

describe('the question queue', () => {
  it('filters to one appointment, for its detail screen', async () => {
    const records = [
      pendingQuestion(),
      pendingQuestion({ clientQuestionId: 'question-2', appointmentId: 'appointment-2' }),
    ];
    expect(pendingForAppointment(records, 'appointment-1').length).toBe(1);
    expect(pendingForAppointment(records, 'appointment-9')).toEqual([]);
  });

  it('holds one record per question and clears them', async () => {
    await queueQuestion(pendingQuestion());
    await queueQuestion(pendingQuestion({ text: 'Reworded' }));
    expect((await loadPendingQuestions()).length).toBe(1);
    expect((await loadPendingQuestions())[0]?.text).toBe('Reworded');

    await clearPendingQuestion('question-abc');
    expect(await loadPendingQuestions()).toEqual([]);

    await queueQuestion(pendingQuestion());
    await clearAllPendingQuestions();
    expect(await loadPendingQuestions()).toEqual([]);
  });
});

describe('saving with a connection', () => {
  let backend: ReturnType<typeof mockBackend>;

  beforeEach(() => {
    backend = mockBackend({ appointments: [appointmentFixture()] });
  });

  afterEach(() => backend.restore());

  it('sends the appointment and keeps nothing on the phone', async () => {
    const outcome = await submitOrQueueAppointment(PROFILE, pendingAppointment());

    expect(outcome.status).toBe('synced');
    expect(outcome.record?.title).toBe('Cardiology follow-up');
    expect(await loadPendingAppointments()).toEqual([]);
  });

  it('sends the question with its client id', async () => {
    const outcome = await submitOrQueueQuestion(PROFILE, pendingQuestion());

    expect(outcome.status).toBe('synced');
    const body = (backend.requests[0]?.body ?? {}) as Record<string, unknown>;
    expect(body.client_question_id).toBe('question-abc');
    expect(await loadPendingQuestions()).toEqual([]);
  });
});

describe('saving with no connection', () => {
  let restore: () => void;

  beforeEach(() => {
    restore = offlineFetch();
  });

  afterEach(() => restore());

  it('keeps the appointment and reports it as pending rather than failing', async () => {
    const outcome = await submitOrQueueAppointment(PROFILE, pendingAppointment());

    expect(outcome.status).toBe('pending');
    expect(outcome.record).toBeNull();
    const kept = await loadPendingAppointments();
    expect(kept.length).toBe(1);
    // Everything needed to send it later, including the id that makes a retry
    // safe (PRD 7, section 53).
    expect(kept[0]?.payload.title).toBe('Cardiology follow-up');
    expect(kept[0]?.payload.client_appointment_id).toBe('appointment-abc');
  });

  it('keeps the question too', async () => {
    const outcome = await submitOrQueueQuestion(PROFILE, pendingQuestion());

    expect(outcome.status).toBe('pending');
    expect((await loadPendingQuestions())[0]?.text).toBe(
      'Do I need any follow-up tests?'
    );
  });
});

describe('a refusal the user has to hear about', () => {
  let backend: ReturnType<typeof mockBackend>;

  afterEach(() => backend.restore());

  it('rejects rather than queueing when the server refuses the appointment', async () => {
    backend = mockBackend();
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      ({
        ok: false,
        status: 422,
        json: async () => ({ detail: { code: 'unknown_timezone' } }),
      }) as Response) as typeof fetch;

    await expect(
      submitOrQueueAppointment(PROFILE, pendingAppointment())
    ).rejects.toThrow();
    expect(await loadPendingAppointments()).toEqual([]);

    globalThis.fetch = original;
  });
});

describe('draining the queues', () => {
  let backend: ReturnType<typeof mockBackend>;

  beforeEach(() => {
    backend = mockBackend({ appointments: [appointmentFixture()] });
  });

  afterEach(() => backend.restore());

  it('does nothing when both queues are empty', async () => {
    expect(await syncPending(PROFILE)).toEqual({ sent: 0, pending: 0, discarded: 0 });
    expect(backend.requests).toEqual([]);
  });

  it('sends appointments first, so a question can reach its appointment', async () => {
    await queueAppointment(pendingAppointment());
    await queueQuestion(pendingQuestion());

    const summary = await syncPending(PROFILE);

    expect(summary.sent).toBe(2);
    expect(await loadPendingAppointments()).toEqual([]);
    expect(await loadPendingQuestions()).toEqual([]);
    const paths = backend.requests.map((request) => request.path);
    expect(paths[0]).toMatch(/\/appointments$/);
    expect(paths[1]).toContain('/questions');
  });

  it('is safe to call twice: the client ids make a replay harmless', async () => {
    await queueAppointment(pendingAppointment());
    await syncPending(PROFILE);
    const second = await syncPending(PROFILE);

    expect(second).toEqual({ sent: 0, pending: 0, discarded: 0 });
  });

  it('keeps everything when the phone is still offline', async () => {
    await queueAppointment(pendingAppointment());
    await queueQuestion(pendingQuestion());
    const restore = offlineFetch();

    const summary = await syncPending(PROFILE);

    expect(summary).toEqual({ sent: 0, pending: 2, discarded: 0 });
    expect((await loadPendingAppointments()).length).toBe(1);
    expect((await loadPendingQuestions()).length).toBe(1);
    restore();
  });

  it('drops a record the server will never accept', async () => {
    await queueAppointment(pendingAppointment());
    const original = globalThis.fetch;
    globalThis.fetch = (async () =>
      ({
        ok: false,
        status: 422,
        json: async () => ({ detail: { code: 'unknown_timezone' } }),
      }) as Response) as typeof fetch;

    const summary = await syncPending(PROFILE);

    expect(summary.discarded).toBe(1);
    expect(await loadPendingAppointments()).toEqual([]);
    globalThis.fetch = original;
  });
});

describe('what is deliberately never queued', () => {
  it('has no way to queue a report', () => {
    // PRD 7 section 53: do not pretend generation succeeded while offline. A
    // PDF is built by the backend, so there is nothing useful to keep here.
    const names = Object.keys(pendingModule).join(' ').toLowerCase();
    expect(names).not.toContain('report');
  });
});
