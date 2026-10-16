/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Draining the offline queue on the appointments screen (PRD 7, section 53).
 *
 * An appointment and a question typed with no signal are kept on the phone. This
 * is the other half of that promise: opening the screen sends them, and the queue
 * empties.
 *
 * Both records carry a client id, so the send is idempotent -- a retry after a
 * dropped response converges on one row rather than two.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useAppointmentListStore } from '../src/features/appointments/listStore';
import {
  loadPendingAppointments,
  loadPendingQuestions,
} from '../src/features/appointments/pending';
import { appointmentFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useAppointmentListStore.setState({ scope: 'upcoming' });

  await AsyncStorage.setItem(
    'nura.appointments.pending',
    JSON.stringify([
      {
        clientAppointmentId: 'appointment-abc',
        payload: {
          title: 'Blood test',
          scheduled_at: '2026-10-05T09:00:00.000Z',
          timezone: 'Europe/London',
          appointment_type: 'lab',
          clinician_id: null,
          location_name: null,
          address: null,
          phone: null,
          notes: null,
          reminders_enabled: true,
          client_appointment_id: 'appointment-abc',
        },
        savedAt: '2026-09-28T09:00:00.000Z',
        displayTitle: 'Blood test',
      },
    ])
  );
  await AsyncStorage.setItem(
    'nura.appointments.pendingQuestions',
    JSON.stringify([
      {
        clientQuestionId: 'question-abc',
        appointmentId: 'appointment-1',
        text: 'Do I need any follow-up tests?',
        savedAt: '2026-09-28T09:00:00.000Z',
      },
    ])
  );

  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [appointmentFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('sends what was saved offline as soon as the screen opens', async () => {
  renderRouter('app', { initialUrl: '/appointments' });

  await waitFor(() => {
    expect(screen.getByText('Blood test')).toBeVisible();
  });

  // It is a real appointment now, not a pending row.
  expect(
    screen.queryByText('Saved on this phone · This will sync when you are back online.')
  ).toBeNull();

  // Both queues are empty.
  await waitFor(async () => {
    expect(await loadPendingAppointments()).toEqual([]);
  });
  expect(await loadPendingQuestions()).toEqual([]);

  // Each was sent with the id it was queued under, which is what makes a retry
  // safe (PRD 7, section 53).
  const posts = backend.requests.filter((request) => request.method === 'POST');
  const bodies = posts.map((request) => (request.body ?? {}) as Record<string, unknown>);
  expect(bodies.some((body) => body.client_appointment_id === 'appointment-abc')).toBe(
    true
  );
  expect(bodies.some((body) => body.client_question_id === 'question-abc')).toBe(true);

  // The appointment goes first, so the question has something to attach to.
  const appointmentIndex = posts.findIndex((request) =>
    /\/appointments$/.test(request.path)
  );
  const questionIndex = posts.findIndex((request) => request.path.includes('/questions'));
  expect(appointmentIndex).toBeLessThan(questionIndex);
});
