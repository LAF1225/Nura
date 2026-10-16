/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The alarm screens (PRD 12, sections 10, 11, 54, 60 and 71).
 *
 * **The whole point of this file is the sentence at the top of the list.**
 * Section 11 asks for honest labelling and section 71 for the gap to be stated
 * plainly: the app has never been run on a physical phone, so no alarm has
 * fired, no notification has fired and no vibration has been felt. The
 * sentence arrives from the server with every list, and the first assertion
 * here is that it is on the screen -- including when the list is empty, which
 * is exactly when somebody is deciding whether to rely on one.
 *
 * The switch is the other thing under test, because it is what people actually
 * do with an alarm: one tap, straight to the server.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent } from '@testing-library/react-native';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { ALARM_LIMITATION, alarmFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  getPermissionsAsync: async () => ({ granted: true, canAskAgain: true }),
  requestPermissionsAsync: async () => ({ granted: true }),
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async () => 'notification-1',
  cancelScheduledNotificationAsync: async () => undefined,
}));

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
  backend = mockBackend({
    status: 'onboarding_complete',
    alarms: [
      alarmFixture(),
      alarmFixture({
        id: 'alarm-2',
        label: 'Take the bins out',
        recurrence: 'selected_days',
        weekdays: [1],
        schedule_label: 'Tuesdays at 7:00 AM',
        enabled: false,
        next_fire_at: null,
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('says what an alarm is in this build, and turns one off through the server', async () => {
  renderRouter('app', { initialUrl: '/daily/alarms' });

  // --- the sentence that matters --------------------------------------------
  await waitFor(() => {
    expect(screen.getByText(ALARM_LIMITATION)).toBeTruthy();
  });
  // Announced as a note, not drawn as fine print.
  expect(screen.getByLabelText(ALARM_LIMITATION)).toBeTruthy();
  // And it says the two things section 11 and section 71 require.
  expect(ALARM_LIMITATION).toContain('phone notifications');
  expect(ALARM_LIMITATION).toContain('never been run on a physical phone');

  // --- the list -------------------------------------------------------------
  expect(screen.getByText('Wake up')).toBeTruthy();
  expect(screen.getByText('Every day at 7:00 AM')).toBeTruthy();
  // A disabled alarm is listed, not hidden: somebody who switched it off at
  // the weekend needs to find it again.
  expect(screen.getByText('Take the bins out')).toBeTruthy();
  expect(screen.getByText('Tuesdays at 7:00 AM')).toBeTruthy();

  // --- the switch -----------------------------------------------------------
  //
  // `fireEvent.press` does nothing to a Switch in this stack; `valueChange` is
  // what a real toggle emits.
  const toggle = screen.getByLabelText('Wake up');
  await act(async () => {
    fireEvent(toggle, 'valueChange', false);
  });

  await waitFor(() => {
    expect(
      backend.requests.filter(
        (request) =>
          request.method === 'PATCH' && request.path.includes('/alarms/alarm-1')
      )
    ).toHaveLength(1);
  });
  const body = backend.requests.find(
    (request) => request.method === 'PATCH' && request.path.includes('/alarms/alarm-1')
  )?.body as Record<string, unknown>;
  expect(body.enabled).toBe(false);
  expect(backend.state.alarms.find((row) => row.id === 'alarm-1')?.enabled).toBe(false);
});
