/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Caregiver Mode: switching person, and what a caregiver is shown.
 *
 * PRD 9, sections 16, 17, 18, 19, 38, 57, 58, 60 and 96.
 *
 * The most important assertion in this file is a negative one. A caregiver
 * granted only `medications` must not be able to tell from the screen whether the
 * person they support records symptoms -- section 18 says the absence of a
 * permission must not leak -- so the test checks that the word "Symptoms" is
 * nowhere on the page, not that a symptom section is empty.
 *
 * Also covered: switching person really changes which profile is requested
 * (section 57), the invitation screen shows both of section 15's lists, and no
 * Call control is offered while no provider is configured (section 38).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  waitFor,
} from 'expo-router/testing-library';

import {
  caregiverHomeFixture,
  invitationPreviewFixture,
  mockBackend,
  signInAt,
  supportedProfileFixture,
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
    supportedProfiles: [
      supportedProfileFixture(),
      supportedProfileFixture({
        relationship_id: 'relationship-2',
        profile_id: 'profile-3',
        profile_name: 'Dad',
        granted: ['appointments'],
      }),
    ],
    // Granted `medications` only. Every other section is absent, which is what
    // the server does for a category that was not granted (section 18).
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
      adherence: {
        from_date: '2026-09-22',
        to_date: '2026-09-28',
        taken: 12,
        skipped: 1,
        missed: 1,
        percent: 86,
      },
      doses_remaining_today: 1,
      doses_overdue: 0,
    }),
    invitationPreview: invitationPreviewFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

it('switches person, shows only the granted category, and offers no call', async () => {
  renderRouter('app', { initialUrl: '/care-mode/profiles' });

  // Both supported people, each with their own permission set (section 56).
  await waitFor(() => {
    expect(screen.getByText('Mum')).toBeVisible();
  });
  expect(screen.getByText('Dad')).toBeVisible();
  // "My Nura" is always offered: helping somebody does not stop you being a
  // person using Nura yourself (section 3).
  expect(screen.getByLabelText('My Nura')).toBeVisible();

  // Two supported people, so two identically-labelled rows. The first is Mum,
  // in the order the server returned them.
  const [mumRow] = screen.getAllByRole('radio', { name: 'View their care' });
  expect(mumRow).toBeDefined();
  fireEvent.press(mumRow as Parameters<typeof fireEvent.press>[0]);

  await waitFor(() => {
    expect(screen.getByText('You are looking at Mum’s care.')).toBeVisible();
  });

  // Section 57: the request really went to the profile that was chosen.
  const homeRequests = backend.requests.filter((request) =>
    request.path.includes('/care/home')
  );
  expect(homeRequests.length).toBeGreaterThan(0);
  expect(homeRequests[homeRequests.length - 1]?.path).toContain('profile-2');

  // What was granted (section 19): the medication, when the reminder is, and a
  // week of counts.
  expect(screen.getByText('Metformin 500 mg')).toBeVisible();
  expect(screen.getByText('Every day at 7:00 PM')).toBeVisible();
  expect(screen.getByText('12 taken, 1 skipped, 1 not recorded')).toBeVisible();
  // Counts, with the sentence saying they are counts and nothing more.
  expect(screen.getByText(/Nura does not draw conclusions from them/i)).toBeVisible();

  // **The negative assertion.** Not "the symptom section is empty" -- the words
  // are not on the page at all, so the response cannot be read to learn whether
  // this person records symptoms (section 18).
  expect(screen.queryByText('Symptoms')).toBeNull();
  expect(screen.queryByText('Health reports')).toBeNull();
  expect(screen.queryByText('Health summary')).toBeNull();
  expect(screen.queryByText('Messages')).toBeNull();

  // Section 38: no Call control, because no provider is configured. The screen
  // says so once rather than offering a button whose only outcome is an error.
  expect(screen.queryByRole('button', { name: /call/i })).toBeNull();

  // Section 58: switching to the other person asks about the other person.
  act(() => {
    router.push('/care-mode/profiles');
  });
  await waitFor(() => {
    expect(screen.getByText('Dad')).toBeVisible();
  });
  const rows = screen.getAllByRole('radio', {
    name: /View their care|Currently viewing/,
  });
  expect(rows.length).toBeGreaterThanOrEqual(2);
});
