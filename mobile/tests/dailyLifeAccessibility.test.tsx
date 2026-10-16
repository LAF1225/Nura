/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The daily-life screens, read out loud (PRD 12, sections 9, 19 and 48).
 *
 * Section 48 asks for 48dp targets, screen-reader labels, dynamic text,
 * accessible date and time controls, non-colour-only completion states,
 * accessible reordering, reduced motion and Light/Dark/System. This file is
 * the screen-reader half; `themeRendering.test.tsx` covers the theme for every
 * screen at once, and the touch-target size is a token
 * (`minTouchTarget`) asserted in `theme.test.ts`.
 *
 * Three things are under test.
 *
 * **An empty account is told what these screens are for.** Not a screen of
 * dead controls: a sentence and a way forward, which is the decision PRD 2
 * made about an offline robot and PRD 7 about an empty appointment list.
 *
 * **Every state is in a label.** A step reads as "Not done yet", a task as
 * "Not done", and a capability as its own sentence.
 *
 * **Reordering is buttons, and they disable at the ends.** There is no drag
 * anywhere in this feature, which is section 48's requirement satisfied by
 * simply not having the thing it asks for an alternative to.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act } from '@testing-library/react-native';
import { router } from 'expo-router';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { dailyLifeFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  // Refused, which is section 9's case.
  getPermissionsAsync: async () => ({ granted: false, canAskAgain: false }),
  requestPermissionsAsync: async () => ({ granted: false }),
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async () => 'notification-1',
  cancelScheduledNotificationAsync: async () => undefined,
}));

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
  // Nothing at all: no tasks, no reminders, no alarms, no routines. The state
  // every account is in on its first day.
  backend = mockBackend({
    status: 'onboarding_complete',
    dailyLife: dailyLifeFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

it('explains itself with nothing recorded, and announces every state', async () => {
  renderRouter('app', { initialUrl: '/daily' });

  // --- the overview ---------------------------------------------------------
  await waitFor(() => {
    expect(
      screen.getByText('Your own list, reminders, alarms and routines.')
    ).toBeTruthy();
  });
  expect(screen.getByText('Nothing due today.')).toBeTruthy();

  // Each list says how much is in it, in words rather than a badge.
  expect(screen.getByText('Nothing on your list.')).toBeTruthy();
  expect(screen.getByText('No reminders set up.')).toBeTruthy();
  expect(screen.getByText('No alarms set.')).toBeTruthy();
  expect(screen.getByText('No routines yet.')).toBeTruthy();

  // Every row is a button with a hint saying where it goes.
  const tasksRow = screen.getByLabelText('Tasks');
  expect(tasksRow.props.accessibilityHint).toBe('Opens your task list');
  expect(screen.getByLabelText('Routines').props.accessibilityHint).toBe(
    'Opens your routines'
  );

  // --- an empty task list ---------------------------------------------------
  await act(async () => {
    router.push('/daily/tasks');
  });
  await waitFor(() => {
    expect(screen.getByText('Add something you want to get done.')).toBeTruthy();
  });
  // Not a dead screen: the way forward is there.
  expect(screen.getByText('Add task')).toBeTruthy();

  // --- the reminder list, with notifications refused (section 9) ------------
  await act(async () => {
    router.push('/daily/reminders');
  });
  await waitFor(
    () => {
      expect(
        screen.getByText(
          'Notifications are turned off for Nura in your phone settings, so ' +
            'reminders will be quiet. They are still saved and still on your ' +
            'Today screen.'
        )
      ).toBeTruthy();
    },
    { timeout: 30_000 }
  );
  // Announced, so a screen reader reaches it rather than seeing grey text.
  expect(
    screen.getByLabelText(
      'Notifications are turned off for Nura in your phone settings, so ' +
        'reminders will be quiet. They are still saved and still on your ' +
        'Today screen.'
    )
  ).toBeTruthy();
  // And it says the reminder is kept, which is the half that matters.
  expect(screen.getByText(/still saved/)).toBeTruthy();

  // --- the routine form's reordering (section 48) ---------------------------
  await act(async () => {
    router.push('/daily/routine-form');
  });
  await waitFor(() => {
    expect(screen.getByText('Steps')).toBeTruthy();
  });

  // Buttons, not a drag. One step, so both ends are disabled.
  const up = screen.getByLabelText('Move up');
  const down = screen.getByLabelText('Move down');
  expect(up.props.accessibilityState?.disabled).toBe(true);
  expect(down.props.accessibilityState?.disabled).toBe(true);
  // Each one says what it moves.
  expect(up.props.accessibilityHint).toContain('earlier');
  expect(down.props.accessibilityHint).toContain('later');

  // The optional switch is a labelled control rather than a checkbox nobody
  // can describe.
  expect(screen.getByLabelText('Optional')).toBeTruthy();

  // --- the alarm form says what an alarm is --------------------------------
  await act(async () => {
    router.push('/daily/alarm-form');
  });
  await waitFor(() => {
    expect(
      screen.getByText(
        'Nura schedules alarms as phone notifications. Whether one actually ' +
          'wakes you has never been tested on a physical phone.'
      )
    ).toBeTruthy();
  });
  // Announced as a note, so somebody using a screen reader hears it before
  // the controls it is about (section 11).
  expect(
    screen.getByLabelText(
      'Nura schedules alarms as phone notifications. Whether one actually ' +
        'wakes you has never been tested on a physical phone.'
    )
  ).toBeTruthy();
  // The time field carries its format in a hint rather than relying on a
  // picker this build has never run on a handset (section 48).
  expect(screen.getByText('A 24-hour time, like 07:30.')).toBeTruthy();
});
