/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Today card and the Important Today rows (PRD 12, sections 18 and 19).
 *
 * **Section 18's rule is the one worth having a test for**: *daily-life items
 * must never obscure safety-critical items.* So the assertion that matters
 * here is an ordering one -- a medication dose comes before a task in the
 * Important Today list, whatever either of them says.
 *
 * The card itself draws nothing for somebody who has never made a task, which
 * `dailyLifeAccessibility.test.tsx` checks on an account with nothing. Here
 * there is something, so the card is drawn.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { dailyLifeFixture, mockBackend, signInAt } from './helpers';

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
    dailyLife: dailyLifeFixture({
      tasks: { due_today: 3, overdue: 1, open_total: 4 },
      reminders: { due_today: 2, due_now: 1 },
      routines: { due_today: 1, in_progress: 1, completed_today: 0 },
      alarm_count: 1,
      next_alarm_at: '2026-09-14T07:00:00Z',
      summary_label: '3 tasks, 1 routine and 2 reminders today.',
      has_anything: true,
    }),
    // Section 18's order: a dose first, then the daily-life rows, whatever
    // either of them says. The server builds this list; the app renders it in
    // the order it arrives.
    important: [
      {
        id: 'medication-dose:dose-1',
        type: 'medication_dose',
        title: 'Metformin — 500 mg',
        subtitle: 'Due now',
        due_at: '2026-09-13T12:10:00Z',
        priority: 'normal',
        action_route: '/medications',
      },
      {
        id: 'task:task-1',
        type: 'task',
        title: 'Ring the clinic',
        subtitle: 'Past its due time',
        due_at: '2026-09-13T09:00:00Z',
        priority: 'important',
        action_route: '/daily',
      },
      {
        id: 'routine-run:run-1',
        type: 'routine_run',
        title: 'Morning routine',
        subtitle: '1 of 3 complete. Next: Stretch',
        due_at: '2026-09-13T07:30:00Z',
        priority: 'normal',
        action_route: '/daily/run/run-1',
      },
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('draws the card, and keeps daily-life rows below the medical ones', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText('Tasks & routines')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // --- the card -------------------------------------------------------------
  expect(screen.getByText('3 tasks, 1 routine and 2 reminders today.')).toBeTruthy();
  // Stated, not warned about. Section 18 keeps all of this below anything
  // safety-critical, and an overdue task is a fact about a clock.
  expect(screen.getByText('1 task is past its due time.')).toBeTruthy();
  expect(screen.getByText('1 routine is under way.')).toBeTruthy();
  expect(screen.getByText('1 reminder is waiting for an answer.')).toBeTruthy();

  // Section 19's quick add, as three reachable buttons rather than a sheet
  // behind a plus icon.
  expect(screen.getByText('Add task')).toBeTruthy();
  expect(screen.getByText('Add reminder')).toBeTruthy();
  expect(screen.getByText('Add routine')).toBeTruthy();

  // --- **section 18's ordering** --------------------------------------------
  const dose = screen.getByText('Metformin — 500 mg');
  const task = screen.getByText('Ring the clinic');
  const routine = screen.getByText('Morning routine');
  expect(dose).toBeTruthy();
  expect(task).toBeTruthy();
  expect(routine).toBeTruthy();

  // The rows are rendered in the order the server sent them, which is where
  // the ordering is decided (`api/v1/today.py`). Asserting the order here
  // would mean asserting it twice; what this proves is that the app renders
  // all three without re-sorting, which is the half it is responsible for.
  const all = screen.getAllByText(/Metformin — 500 mg|Ring the clinic|Morning routine/);
  expect(all.map((node) => node.props.children)).toEqual([
    'Metformin — 500 mg',
    'Ring the clinic',
    'Morning routine',
  ]);

  // The routine row carries the progress line the server rendered.
  expect(screen.getByText('1 of 3 complete. Next: Stretch')).toBeTruthy();
});
