/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Today appointments card and its Important Today row (PRD 7, ss9 and 10).
 *
 * Two things worth asserting rather than reading:
 *
 * **The card answers "when is the next one" without a tap.** The title, who it is
 * with and when, plus the one action -- Prepare, or View summary once there is one
 * (PRD 7, section 9).
 *
 * **Nothing is an emergency.** PRD 7 section 10 says so outright, so the row's
 * wording is checked for alarm language as well as for what it does say.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { appointmentFixture, mockBackend, signInAt } from './helpers';

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
    appointments: [appointmentFixture()],
    todayAppointments: {
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
        preparation_status: 'not_started',
        question_count: 0,
        report_count: 0,
      },
      upcoming_count: 2,
      has_appointments: true,
    },
    important: [
      {
        id: 'appointment:appointment-1',
        type: 'appointment',
        title: 'Cardiology follow-up',
        subtitle: 'Tomorrow at 3:30 PM · Not prepared yet',
        priority: 'normal',
        action_route: '/appointments/appointment-1',
      },
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the next appointment on Today and opens the preparation flow', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(() => {
    expect(screen.getByText('Next appointment')).toBeVisible();
  });

  // Who, and when, in the appointment's own zone (PRD 7, sections 9 and 42).
  expect(screen.getAllByText('Cardiology follow-up').length).toBeGreaterThan(0);
  expect(screen.getByText('Dr Ahmed Khan · Cardiology')).toBeVisible();
  expect(screen.getAllByText('Tomorrow at 3:30 PM').length).toBeGreaterThan(0);
  expect(screen.getByText('Not prepared yet')).toBeVisible();
  expect(screen.getByText('2 upcoming appointments')).toBeVisible();

  // The Important Today row is present and is not an alert (PRD 7, s10).
  expect(screen.getByText('Tomorrow at 3:30 PM · Not prepared yet')).toBeVisible();
  for (const alarm of ['Urgent', 'Emergency', 'Warning', 'Immediately']) {
    expect(screen.queryByText(alarm)).toBeNull();
  }

  // One action, and it goes to the preparation flow.
  fireEvent.press(screen.getByRole('button', { name: 'Prepare for appointment' }));
  await waitFor(() => {
    expect(
      screen.getByText(
        'Nura will show you what you have recorded so you can choose what to bring. Nothing is shared until you export it.'
      )
    ).toBeVisible();
  });
});
