/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Reviewing a care request (PRD 9, sections 24, 25, 77, 86, 87, 88 and 96).
 *
 * Four things are under test.
 *
 * **The diff is explicit and labelled.** Section 86 asks for current versus
 * proposed, and this checks both halves are on screen with their own labels --
 * because a visual side-by-side is not something a screen reader conveys
 * (section 77).
 *
 * **Approve applies and Decline does not.** Both asserted on the request, not on
 * the screen.
 *
 * **A decline note is kept and marked private** (sections 25 and 88). The hint
 * under the field says so, and the note goes in the decline body.
 *
 * **A request whose target has gone offers no Approve** (section 24, step 2). The
 * server would refuse it, and a button that cannot work is worse than a sentence
 * saying why.
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
  careSuggestionFixture,
  careSummaryFixture,
  mockBackend,
  signInAt,
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
    careSuggestions: [
      careSuggestionFixture(),
      careSuggestionFixture({
        id: 'suggestion-2',
        action_type: 'pause_medication_reminder',
        action_label: 'Pause a medication reminder',
        diff: {
          subject: 'A medication reminder',
          current: null,
          proposed: 'Reminders paused',
          target_missing: true,
        },
      }),
    ],
    careSummary: careSummaryFixture({
      caregiver_count: 1,
      pending_suggestion_count: 2,
    }),
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the diff, approves one request, and refuses to approve a missing target', async () => {
  renderRouter('app', { initialUrl: '/caregivers/requests' });

  // Two waiting requests, both from Ayesha, so both cards carry the same line.
  await waitFor(() => {
    expect(screen.getAllByText('Ayesha suggested a change')).toHaveLength(2);
  });

  // Section 86: the pair, each half labelled. "Now" and "Suggested" as their own
  // lines rather than two values side by side.
  expect(screen.getAllByText('Now').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Suggested').length).toBeGreaterThan(0);
  expect(screen.getByText('7:00 PM')).toBeVisible();
  expect(screen.getByText('8:00 PM')).toBeVisible();
  expect(screen.getAllByText('Metformin').length).toBeGreaterThan(0);

  act(() => {
    router.push('/caregivers/requests/suggestion-1');
  });

  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Approve' })).toBeVisible();
  });

  // Section 25 and 88: the note is private, and the screen says so where it is
  // typed rather than only in the documentation.
  expect(screen.getByText('Only you can see this.')).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Approve' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/approve'))
    ).toHaveLength(1);
  });
  expect(backend.state.careSuggestions[0]?.status).toBe('approved');

  // Approving navigates back, so wait for the list before pushing again --
  // otherwise the pop races the push and lands on the wrong screen.
  await waitFor(() => {
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
  });

  // The one whose target has gone: no Approve, and a sentence saying why
  // (section 24, step 2).
  act(() => {
    router.push('/caregivers/requests/suggestion-2');
  });

  // The note field only exists on the detail screen, so finding it is what says
  // the navigation landed.
  await waitFor(() => {
    expect(screen.getByLabelText(/Add a note for yourself/)).toBeVisible();
  });
  expect(
    screen.getAllByText(
      'The thing this would change is no longer there, so it cannot be applied.'
    ).length
  ).toBeGreaterThan(0);
  expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();

  // Declining still works, with the note.
  fireEvent.changeText(
    screen.getByLabelText(/Add a note for yourself/),
    'The nurse asked me to keep it'
  );
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Decline' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Decline' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/decline'))
    ).toHaveLength(1);
  });
  const decline = backend.requests.find((request) => request.path.includes('/decline'));
  expect((decline?.body as Record<string, unknown>).note).toBe(
    'The nurse asked me to keep it'
  );
});
