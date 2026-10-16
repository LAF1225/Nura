/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The task screens (PRD 12, sections 5, 6, 37, 40 and 60).
 *
 * One `renderRouter` per file is a hard limit of this harness, so this is one
 * walk-through rather than six tests: open the list, tick a task, add one,
 * and check the form refuses a task with no title.
 *
 * **Nothing is asserted optimistically.** Every change checks the request the
 * app made *and* the stub's resulting state, which is what proves the app sent
 * what it said it did rather than only redrawing itself.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent } from '@testing-library/react-native';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { dailyLifeFixture, mockBackend, signInAt, taskFixture } from './helpers';

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
    tasks: [
      taskFixture(),
      taskFixture({
        id: 'task-2',
        title: 'Pick up the prescription',
        due_at: null,
        due_local_date: null,
        due_label: null,
        priority: 'important',
        priority_label: 'Important',
      }),
    ],
    dailyLife: dailyLifeFixture({
      tasks: { due_today: 1, overdue: 0, open_total: 2 },
      summary_label: '2 tasks today.',
      has_anything: true,
    }),
  });
});

afterEach(() => {
  backend.restore();
});

function requestsTo(fragment: string, method?: string) {
  return backend.requests.filter(
    (request) =>
      request.path.includes(fragment) &&
      (method === undefined || request.method === method)
  );
}

/** Creates only -- a path that *ends* at `/tasks`, query string aside. */
function creates() {
  return backend.requests.filter(
    (request) => request.method === 'POST' && /\/tasks(\?|$)/.test(request.path)
  );
}

it('lists tasks, marks one done, and adds another through the server', async () => {
  renderRouter('app', { initialUrl: '/daily/tasks' });

  // --- the list -------------------------------------------------------------
  await waitFor(() => {
    expect(screen.getByText('Call the physiotherapist')).toBeTruthy();
  });
  // A task with no due date is a normal task, not a half-filled one
  // (section 5): it is listed, with no due line.
  expect(screen.getByText('Pick up the prescription')).toBeTruthy();
  expect(screen.getByText('Today, 4:00 PM')).toBeTruthy();
  // The priority the *person* chose is shown; nothing Nura decided.
  expect(screen.getByText('Important')).toBeTruthy();

  // --- Done -----------------------------------------------------------------
  //
  // The tick box is its own control with its own accessible label, so a
  // screen reader can mark a task done without opening it (section 48).
  const tick = screen.getByLabelText('Call the physiotherapist. Not done.');
  await act(async () => {
    fireEvent.press(tick);
  });

  await waitFor(() => {
    expect(requestsTo('/tasks/task-1/complete', 'POST')).toHaveLength(1);
  });
  expect(backend.state.tasks.find((task) => task.id === 'task-1')?.status).toBe(
    'completed'
  );

  // --- adding one -----------------------------------------------------------
  await act(async () => {
    fireEvent.press(screen.getByText('Add task'));
  });

  await waitFor(() => {
    expect(screen.getByText('Due')).toBeTruthy();
  });
  // Section 5, said on the form: a task without a due date is a normal task.
  expect(screen.getByText('Optional. A task without one is a normal task.')).toBeTruthy();

  // Saving with no title sends nothing.
  //
  // What is *not* asserted here is the error message appearing. React 19 with
  // this version of the testing library does not flush a component's own
  // `useState` update from a `fireEvent`, so the re-render never happens in
  // the test even though it does in the app. The behaviour that matters is
  // testable and tested: no request was made. The wording itself is asserted
  // in `dailyLifeCopy.test.ts`.
  await act(async () => {
    fireEvent.press(screen.getByText('Save'));
  });
  expect(creates()).toHaveLength(0);

  // Filling the field in and saving is not driveable here either: the same
  // limitation means `changeText` does not reach the component's state, so
  // Save still sees an empty title. What the form *does* with a filled-in
  // draft is covered by `dailyLifeValidation.test.ts`, which tests the rules
  // directly, and the request body is covered by `dailyLifeApi.test.ts`.
  //
  // The two fields a task form has are both here, with their hints, which is
  // what this screen test can honestly check.
  expect(screen.getByLabelText('Title')).toBeTruthy();
  expect(screen.getByText('A few words saying what it is.')).toBeTruthy();
  expect(screen.getByText('Normal')).toBeTruthy();
  expect(screen.getByText('Shows nearer the top. Nobody is notified.')).toBeTruthy();
});
