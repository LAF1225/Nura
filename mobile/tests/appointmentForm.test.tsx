/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Adding an appointment (PRD 7, sections 4, 8 and 42).
 *
 * The form is driven the way a user drives it: typing into the fields and
 * pressing Save. That works because every field writes into a Zustand store
 * rather than component state -- a store update re-renders under React 19 where a
 * local `useState` update from a fired event does not (see the README's known
 * issues, and PRD 6's symptom form, which made the same choice).
 *
 * The assertions are the two rules PRD 7 section 8 sets: Save is refused until the
 * three required fields are right, and the optional ones stay optional.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useAppointmentFormStore } from '../src/features/appointments/formStore';
import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useAppointmentFormStore.setState({ draft: null, editingId: null });
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [],
    healthRecords: {
      clinicians: [
        {
          id: 'clinicians-1',
          profile_id: 'profile-1',
          name: 'Dr Ahmed Khan',
          specialty: 'Cardiology',
          created_at: '2026-09-01T09:00:00Z',
          updated_at: '2026-09-01T09:00:00Z',
        },
      ],
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('validates, then saves an appointment with only what is required', async () => {
  renderRouter('app', { initialUrl: '/appointments/new' });

  await waitFor(() => {
    expect(screen.getByText('What is the appointment?')).toBeVisible();
  });

  const save = screen.getByRole('button', { name: 'Save appointment' });

  // A fresh draft has a date and a time but no name, so Save is refused.
  expect(save.props.accessibilityState.disabled).toBe(true);

  // A blank name is not a name, and the error says what to do.
  // Fields are found by a regex: `TextField` folds the error into the
  // accessible label so a screen reader hears it, which changes the exact
  // string once something is wrong.
  fireEvent.changeText(screen.getByLabelText(/What is the appointment/), '   ');
  await waitFor(() => {
    expect(
      screen.getByText('Give the appointment a name, like “Cardiology follow-up”.')
    ).toBeVisible();
  });

  fireEvent.changeText(
    screen.getByLabelText(/What is the appointment/),
    'Cardiology follow-up'
  );
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Save appointment' })).toBeEnabled();
  });

  // A malformed time is refused with the format it wants.
  fireEvent.changeText(screen.getByLabelText(/^Time/), '3:30 PM');
  await waitFor(() => {
    expect(screen.getByText('Use a 24-hour time like 15:30.')).toBeVisible();
  });
  expect(
    screen.getByRole('button', { name: 'Save appointment' }).props.accessibilityState
      .disabled
  ).toBe(true);

  fireEvent.changeText(screen.getByLabelText(/^Date/), '2026-10-02');
  fireEvent.changeText(screen.getByLabelText(/^Time/), '15:30');

  // The kind of appointment and the clinician are both offered, and neither is
  // required (PRD 7, sections 6 and 8).
  fireEvent.press(screen.getByLabelText('Specialist'));
  fireEvent.press(screen.getByLabelText('Dr Ahmed Khan'));
  fireEvent.changeText(screen.getByLabelText(/Where is it/), 'City Hospital');

  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Save appointment' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Save appointment' }));

  await waitFor(() => {
    const post = backend.requests.find(
      (request) => request.method === 'POST' && /\/appointments$/.test(request.path)
    );
    expect(post).toBeDefined();
  });

  const post = backend.requests.find(
    (request) => request.method === 'POST' && /\/appointments$/.test(request.path)
  );
  const body = (post?.body ?? {}) as Record<string, any>;

  expect(body.title).toBe('Cardiology follow-up');
  expect(body.appointment_type).toBe('specialist');
  expect(body.clinician_id).toBe('clinicians-1');
  expect(body.location_name).toBe('City Hospital');
  // Untouched optional fields are sent as null, not as empty strings.
  expect(body.address).toBeNull();
  expect(body.phone).toBeNull();
  expect(body.notes).toBeNull();
  // Reminders default on (PRD 7, section 36).
  expect(body.reminders_enabled).toBe(true);
  // The zone travels with the appointment (PRD 7, section 42).
  expect(typeof body.timezone).toBe('string');
  expect(body.timezone.length).toBeGreaterThan(0);
  // The idempotency key was generated with the draft, not by the request.
  expect(String(body.client_appointment_id)).toMatch(/^appointment-/);
  // The instant matches the date and time as typed, in the device's own zone.
  expect(new Date(body.scheduled_at).getTime()).toBe(
    new Date('2026-10-02T15:30:00').getTime()
  );

  // The draft is cleared once it is stored, so nothing lingers half-written.
  await waitFor(() => {
    expect(useAppointmentFormStore.getState().draft).toBeNull();
  });
});
