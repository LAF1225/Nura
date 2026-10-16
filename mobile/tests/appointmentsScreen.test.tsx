/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The appointments list (PRD 7, sections 41 and 61).
 *
 * Mounted at `/appointments` through the real router, so this is the screen a
 * user gets: the three lists PRD 7 section 41 divides them into, with the
 * clinician, the time and how far preparation has got on each row.
 *
 * One `renderRouter` per file (see navigation.test.tsx), so this is one long
 * test that walks the screen rather than several short ones.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useAppointmentListStore } from '../src/features/appointments/listStore';
import { appointmentFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useAppointmentListStore.setState({ scope: 'upcoming' });
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [
      appointmentFixture(),
      appointmentFixture({
        id: 'appointment-2',
        title: 'Annual review',
        status: 'completed',
        completed_at: '2026-09-07T09:00:00Z',
        when_label: '7 September 2026 at 10:00 AM',
        clinician: null,
        appointment_type: 'primary_care',
      }),
      appointmentFixture({
        id: 'appointment-3',
        title: 'Dental check-up',
        status: 'cancelled',
        cancelled_at: '2026-09-20T09:00:00Z',
        when_label: '9 October 2026 at 9:00 AM',
        clinician: null,
        appointment_type: 'dentist',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('opens on what is coming, and moves between the three lists', async () => {
  renderRouter('app', { initialUrl: '/appointments' });

  // Upcoming is what somebody opened the screen for, so it is the first list.
  await waitFor(() => {
    expect(screen.getByText('Cardiology follow-up')).toBeVisible();
  });
  expect(screen.queryByText('Annual review')).toBeNull();
  expect(screen.queryByText('Dental check-up')).toBeNull();

  // The clinician and the time are on the row, so the list answers "who and
  // when" without a tap.
  expect(screen.getByText('Dr Ahmed Khan · Cardiology')).toBeVisible();
  expect(screen.getByText('2 October 2026 at 3:30 PM')).toBeVisible();
  // And how far preparation has got (PRD 7, section 11).
  expect(screen.getByText('Not prepared yet')).toBeVisible();

  // Pressed by role: the words also appear as a row's status, and a tab is a
  // button while a status is not.
  fireEvent.press(screen.getByRole('button', { name: 'Past' }));
  await waitFor(() => {
    expect(screen.getByText('Annual review')).toBeVisible();
  });
  expect(screen.queryByText('Cardiology follow-up')).toBeNull();
  // A past appointment says what happened in a word, not only a colour
  // (PRD 7, section 58).
  expect(screen.getByText('Completed')).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Cancelled' }));
  await waitFor(() => {
    expect(screen.getByText('Dental check-up')).toBeVisible();
  });
  expect(screen.queryByText('Annual review')).toBeNull();

  // Each list asks the server for its own scope rather than filtering locally.
  const scopes = backend.requests
    .map((request) => request.path)
    .filter((path) => path.includes('scope='));
  expect(scopes.some((path) => path.includes('scope=upcoming'))).toBe(true);
  expect(scopes.some((path) => path.includes('scope=past'))).toBe(true);
  expect(scopes.some((path) => path.includes('scope=cancelled'))).toBe(true);

  // Back to Upcoming, and into one appointment.
  fireEvent.press(screen.getByRole('button', { name: 'Upcoming' }));
  await waitFor(() => {
    expect(screen.getByText('Cardiology follow-up')).toBeVisible();
  });

  fireEvent.press(screen.getByText('Cardiology follow-up'));
  await waitFor(() => {
    // The detail screen's own action, which the list does not have.
    expect(screen.getByText('Prepare for appointment')).toBeVisible();
  });
});
