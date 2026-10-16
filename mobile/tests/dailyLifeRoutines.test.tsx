/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The routine screens (PRD 12, sections 12, 13, 14, 33, 39, 48 and 60).
 *
 * One walk-through, because one `renderRouter` per file is a hard limit of
 * this harness: open a routine, tick a step, un-tick it, and pause the
 * routine.
 *
 * **A ticked step is a mutation and a query, not component state**, which is
 * why this is testable where a form is not: the progress line comes back from
 * the server and the screen redraws from the cache.
 *
 * **Every step state is announced** (section 48). The tick box reads as "Drink
 * water. Not done yet." and then as "Drink water. Done." -- not as a colour.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { act, fireEvent } from '@testing-library/react-native';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, routineFixture, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
  backend = mockBackend({
    status: 'onboarding_complete',
    routines: [routineFixture()],
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

it('shows a routine, ticks a step, un-ticks it, and pauses the routine', async () => {
  renderRouter('app', { initialUrl: '/daily/routine/routine-1' });

  // --- the routine ----------------------------------------------------------
  await waitFor(() => {
    expect(screen.getByText('Morning routine')).toBeTruthy();
  });
  expect(screen.getByText('Every day at 7:30 AM')).toBeTruthy();
  // Section 33's own line, rendered by the server.
  expect(screen.getByText('0 of 3 complete. Next: Drink water')).toBeTruthy();
  // The optional step says so, so nobody wonders why the run can finish
  // without it (section 14).
  expect(screen.getAllByText('Optional').length).toBeGreaterThan(0);

  // --- ticking a step -------------------------------------------------------
  //
  // The label carries the state, which is section 48's non-colour-only
  // requirement.
  const step = screen.getByLabelText('Drink water. Not done yet.');
  await act(async () => {
    fireEvent.press(step);
  });

  await waitFor(() => {
    expect(requestsTo('/routine-runs/run-1/steps/step-1/complete', 'POST')).toHaveLength(
      1
    );
  });
  const body = requestsTo('/routine-runs/run-1/steps/step-1/complete', 'POST')[0]!
    .body as Record<string, unknown>;
  // Section 39: a client id, so a retried tick is one row rather than two.
  expect(typeof body.client_completion_id).toBe('string');

  await waitFor(() => {
    expect(screen.getByText('1 of 3 complete. Next: Stretch for 5 minutes')).toBeTruthy();
  });
  expect(screen.getByLabelText('Drink water. Done.')).toBeTruthy();

  // --- un-ticking it --------------------------------------------------------
  //
  // A checklist needs Undo as much as a task does.
  await act(async () => {
    fireEvent.press(screen.getByLabelText('Drink water. Done.'));
  });
  await waitFor(() => {
    expect(
      requestsTo('/routine-runs/run-1/steps/step-1/complete', 'DELETE')
    ).toHaveLength(1);
  });

  // --- pausing --------------------------------------------------------------
  await act(async () => {
    fireEvent.press(screen.getByText('Pause'));
  });
  await waitFor(() => {
    expect(requestsTo('/routines/routine-1/pause', 'POST')).toHaveLength(1);
  });
  expect(backend.state.routines.find((row) => row.id === 'routine-1')?.status).toBe(
    'paused'
  );
});
