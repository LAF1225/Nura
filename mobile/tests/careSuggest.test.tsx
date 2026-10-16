/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * A caregiver proposing a reminder change (PRD 9, sections 20, 21, 73, 85, 96).
 *
 * Section 20's worked example, driven through the app: the evening reminder moved
 * from 7:00 PM to 8:00 PM, as a suggestion rather than a change.
 *
 * The negative assertions carry the weight here. The screen offers a time and a
 * pause, and **nothing that could change a dose** -- section 85 forbids
 * `change_medication_dose`, and the way that holds is that no control, no action
 * type and no payload field exists for one, on either side.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  caregiverHomeFixture,
  mockBackend,
  signInAt,
  supportedProfileFixture,
} from './helpers';
import { useCareModeStore } from '../src/features/caregivers/modeStore';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  // Already in Caregiver Mode for Mum: proposing is a caregiver's action, and the
  // owner has no route to it (section 21).
  useCareModeStore.setState({
    context: {
      kind: 'caregiver',
      profileId: 'profile-2',
      relationshipId: 'relationship-1',
    },
    hydrated: true,
  });
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    supportedProfiles: [supportedProfileFixture()],
    caregiverHome: caregiverHomeFixture({
      granted: ['medications'],
      medications: [
        {
          medication_id: 'med-1',
          name: 'Metformin',
          dose: '500 mg',
          schedule_label: 'Every day at 7:00 PM',
          reminders_paused: false,
          supply_low: false,
          remaining_doses: null,
          schedule_id: 'schedule-1',
        },
      ],
    }),
  });
});

afterEach(() => {
  backend.restore();
  useCareModeStore.setState({ context: { kind: 'self' }, hydrated: true });
});

it('suggests a new reminder time and offers nothing that could change a dose', async () => {
  renderRouter('app', {
    initialUrl:
      '/care-mode/suggest?scheduleId=schedule-1&name=Metformin&current=Every%20day%20at%207%3A00%20PM',
  });

  await waitFor(() => {
    expect(screen.getByText('Metformin')).toBeVisible();
  });

  // Section 21: they are told the change is a proposal before they make it.
  expect(
    screen.getByText('They will be asked to approve it. Nothing changes until they do.')
  ).toBeVisible();
  // The current value, so a caregiver knows what they are changing.
  expect(screen.getByText('Every day at 7:00 PM')).toBeVisible();

  // Section 85, by absence: no dose control anywhere on the screen.
  expect(screen.queryByText(/dose/i)).toBeNull();
  expect(screen.queryByText(/diagnosis/i)).toBeNull();
  expect(screen.queryByText(/condition/i)).toBeNull();

  fireEvent.press(screen.getByLabelText('8:00 PM'));

  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send suggestion' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send suggestion' }));

  await waitFor(() => {
    expect(
      backend.requests.filter(
        (request) =>
          request.method === 'POST' && request.path.includes('/caregiver-suggestions')
      )
    ).toHaveLength(1);
  });

  const created = backend.requests.find(
    (request) =>
      request.method === 'POST' && request.path.includes('/caregiver-suggestions')
  );
  const body = created?.body as Record<string, unknown>;
  expect(body.action_type).toBe('change_medication_reminder_time');
  expect(body.target_resource_id).toBe('schedule-1');
  expect(body.payload).toEqual({ times: [{ time_of_day: '20:00' }] });
  // Section 74: a client id, so a retry is answered rather than recorded twice.
  expect(typeof body.client_suggestion_id).toBe('string');
  // It went to the person being supported, not to the caregiver's own profile
  // (section 57).
  expect(created?.path).toContain('profile-2');

  // And it says what happens next, rather than implying the change is made.
  await waitFor(() => {
    expect(screen.getByText('Sent. They will see it in Nura.')).toBeVisible();
  });
});
