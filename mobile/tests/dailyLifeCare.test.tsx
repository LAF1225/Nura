/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Routines on a caregiver's screen (PRD 12, sections 16, 20, 42 and 68).
 *
 * Two things are under test, and the second is the important one.
 *
 * **A caregiver granted `routines` sees routines.** That is new: through
 * PRD 11 the permission could be granted and unlocked nothing, and the screen
 * said so. It now shows what the routine is, when it runs and how today is
 * going -- and nothing else, because a tick-by-tick log of somebody's morning
 * is the surveillance experience PRD 9 section 2 rules out.
 *
 * **Section 42 is on the screen.** The note says tasks, alarms and personal
 * reminders stay private, so a caregiver can see where the edge is rather
 * than wondering why the list looks short. And the screen has no control that
 * could change a routine: a caregiver's only route to a change is a
 * suggestion the person approves.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent } from '@testing-library/react-native';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  caregiverHomeFixture,
  caregiverRoutineFixture,
  mockBackend,
  signInAt,
  supportedProfileFixture,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    supportedProfiles: [supportedProfileFixture({ granted: ['routines'] })],
    caregiverHome: caregiverHomeFixture({
      granted: ['routines'],
      granted_without_data: [],
      routines: [
        caregiverRoutineFixture(),
        caregiverRoutineFixture({
          routine_id: 'routine-2',
          title: 'Evening stretch',
          schedule_label: 'Every day at 7:30 PM',
          paused: true,
          today_status: null,
          today_done: null,
          today_total: null,
          today_progress_label: null,
        }),
      ],
    }),
    careRoutines: [caregiverRoutineFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows a caregiver the routines, their progress, and where the edge is', async () => {
  // Care Mode is reached by choosing whose care to look at, which is also how
  // the profile every request is about gets decided (PRD 9, section 56).
  renderRouter('app', { initialUrl: '/care-mode/profiles' });

  await waitFor(
    () => {
      expect(screen.getByText('Mum')).toBeTruthy();
    },
    { timeout: 30_000 }
  );
  const [row] = screen.getAllByRole('radio', { name: 'View their care' });
  fireEvent.press(row as Parameters<typeof fireEvent.press>[0]);

  await waitFor(
    () => {
      expect(screen.getByText('Routines')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // --- what a caregiver sees ------------------------------------------------
  expect(screen.getByText('Morning routine')).toBeTruthy();
  expect(screen.getByText('Every day at 7:30 AM')).toBeTruthy();
  expect(screen.getByText('0 of 3 complete')).toBeTruthy();

  // A paused routine says so, and a routine that does not run today has no
  // progress line rather than a misleading "0 of 3".
  expect(screen.getByText('Every day at 7:30 PM · paused')).toBeTruthy();

  // --- **section 42, on the screen** ----------------------------------------
  expect(
    screen.getByText('Routines only. Tasks, alarms and personal reminders stay private.')
  ).toBeTruthy();

  // --- and what a caregiver cannot do ---------------------------------------
  //
  // No control here changes anything: a caregiver's route to a change is a
  // suggestion the primary user approves (PRD 9, sections 21 and 64).
  for (const control of [
    'Pause',
    'Resume',
    'Edit routine',
    'Add routine',
    'Skip today',
  ]) {
    expect(screen.queryByText(control)).toBeNull();
  }
  // Nor is a step list shown: what the steps *are* is not what "view
  // permitted routines" means.
  expect(screen.queryByText('Drink water')).toBeNull();

  // --- the sections that were not granted are absent, not empty -------------
  //
  // Section 18: the absence of a permission must not leak. A caregiver with
  // only `routines` cannot tell from this screen whether this person takes any
  // medication.
  expect(screen.queryByText('Medications')).toBeNull();
  expect(screen.queryByText('Symptoms')).toBeNull();
  expect(screen.queryByText('Health reports')).toBeNull();

  // And nothing anywhere reads the owner's own daily-life routes.
  expect(
    backend.requests.filter(
      (request) =>
        /\/(tasks|alarms|reminders)(\?|$)/.test(request.path) ||
        request.path.includes('daily-life')
    )
  ).toHaveLength(0);
});
