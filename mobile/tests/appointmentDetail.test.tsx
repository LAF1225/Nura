/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * One appointment (PRD 7, sections 7, 11 and 38).
 *
 * The shape PRD 7 section 11 lays out, and the actions underneath it. The rule
 * worth testing rather than reading is section 7's: **nothing infers what
 * happened.** Marking an appointment completed is something the user does, and
 * until they do, a past appointment is still `scheduled`.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  appointmentFixture,
  mockBackend,
  questionFixture,
  reportFixture,
  signInAt,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [appointmentFixture({ notes: 'Bring the previous scan.' })],
    appointmentQuestions: [questionFixture()],
    appointmentReports: [reportFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the visit, its questions and its summaries, and lets the user act', async () => {
  renderRouter('app', { initialUrl: '/appointments/appointment-1' });

  // Who, when and where (PRD 7, section 11).
  await waitFor(() => {
    expect(screen.getByText('Cardiology follow-up')).toBeVisible();
  });
  expect(screen.getByText('Dr Ahmed Khan · Cardiology')).toBeVisible();
  expect(screen.getByText('2 October 2026 at 3:30 PM')).toBeVisible();
  expect(screen.getByText('City Hospital')).toBeVisible();
  expect(screen.getByText('Bring the previous scan.')).toBeVisible();

  // The one prominent action.
  expect(screen.getByRole('button', { name: 'Prepare for appointment' })).toBeVisible();

  // The question the user wrote, word for word (PRD 7, section 23).
  expect(
    screen.getByText('Could this medication be contributing to my fatigue?')
  ).toBeVisible();
  expect(screen.getByText('1 question added')).toBeVisible();

  // And the summary that exists, named the way PRD 7 section 31 names it.
  expect(screen.getByText('1 summary generated')).toBeVisible();
  expect(screen.getByText('Report v1 · 28 September 2026, 9:15 AM')).toBeVisible();

  // Reminders can be turned off from here without opening the form (s36).
  fireEvent.press(screen.getByLabelText('Reminders are on'));
  await waitFor(() => {
    const patch = backend.requests.find((request) => request.method === 'PATCH');
    expect(patch).toBeDefined();
  });
  expect(
    (backend.requests.find((request) => request.method === 'PATCH')?.body ??
      {}) as Record<string, unknown>
  ).toEqual({ reminders_enabled: false });

  // Marking it completed is something the user does, never something Nura
  // concludes (PRD 7, section 7).
  fireEvent.press(screen.getByLabelText('Mark as completed'));
  await waitFor(() => {
    expect(backend.requests.some((request) => request.path.endsWith('/complete'))).toBe(
      true
    );
  });

  // Once completed, the offer is to record the follow-up -- which opens the
  // ordinary form, because nothing books anything (PRD 7, section 40).
  await waitFor(() => {
    expect(screen.getByLabelText('Add follow-up appointment')).toBeVisible();
  });
  expect(screen.queryByLabelText('Cancel appointment')).toBeNull();

  // And it can be put back, for the ordinary mistake of tapping the wrong thing.
  fireEvent.press(screen.getByLabelText('Move back to scheduled'));
  await waitFor(() => {
    expect(backend.requests.some((request) => request.path.endsWith('/reopen'))).toBe(
      true
    );
  });
});
