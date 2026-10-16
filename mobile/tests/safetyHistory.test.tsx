/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Safety history and one event in full (PRD 10, sections 16, 47, 48, 49, 51,
 * 52 and 113).
 *
 * Three things are under test.
 *
 * **The history says what was observed, never what it meant** (sections 16
 * and 52). "Possible fall" is on screen, and the forbidden labels are
 * asserted absent -- this is the client half of a rule the backend enforces
 * in its wording module.
 *
 * **The detail reads as section 51.** Type, what was observed, the response,
 * the escalation, the outcome.
 *
 * **A false alarm can be marked either way** (sections 47 and 48). "No / not
 * sure" is recorded rather than ignored, so "they said it was real" and
 * "nobody asked" stay different facts -- and the note says nothing trains on
 * it.
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
  mockBackend,
  safetyCheckFixture,
  safetyEventFixture,
  safetyStatusFixture,
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
    safetyStatus: safetyStatusFixture(),
    safetyEvents: [
      safetyCheckFixture({
        id: 'event-fall',
        status: 'resolved',
        resolution: 'user_confirmed_ok',
        resolution_label: 'You said you were okay',
        user_response: 'im_okay',
        response_deadline_at: '2026-10-02T18:42:45Z',
        no_response_seconds: null,
        no_response_label: null,
      }),
      safetyEventFixture({
        id: 'event-sos',
        status: 'resolved',
        resolution: 'no_response_escalated',
        resolution_label: 'No response, so escalation started',
        no_response_seconds: 45,
        no_response_label: 'No response after 45 seconds.',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('lists what happened, opens one, and records a false-alarm answer', async () => {
  renderRouter('app', { initialUrl: '/safety/history' });

  await waitFor(() => {
    expect(screen.getByText('Possible fall')).toBeVisible();
  });
  expect(screen.getByText('Emergency request')).toBeVisible();
  expect(screen.getByText('You said you were okay')).toBeVisible();
  expect(screen.getByText('No response, so escalation started')).toBeVisible();

  // Sections 16 and 52: nothing on this screen states a cause.
  for (const forbidden of [/fall detected/i, /seizure/i, /unconscious/i]) {
    expect(screen.queryByText(forbidden)).toBeNull();
  }

  act(() => {
    router.push('/safety/event-sos');
  });

  // Section 51's layout.
  await waitFor(() => {
    expect(screen.getByText('You asked Nura for help.')).toBeVisible();
  });
  expect(screen.getByText('No response after 45 seconds.')).toBeVisible();
  expect(screen.getByText('In-app alert created for Ayesha.')).toBeVisible();
  expect(
    screen.getByText('Phone call for Spouse: not set up in this build.')
  ).toBeVisible();
  expect(
    screen.getByText('Some steps were taken and some are not available')
  ).toBeVisible();

  // Section 47: asked after the event finished, with both answers available.
  expect(screen.getByText('Was this a false alarm?')).toBeVisible();
  expect(screen.getByText('I was testing it')).toBeVisible();
  // Section 48: and the note that nothing trains on it.
  expect(screen.getByText(/Nothing is trained on it/i)).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'No, or not sure' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/false-alarm'))
    ).toHaveLength(1);
  });
  const sent = backend.requests.find((request) => request.path.includes('/false-alarm'))
    ?.body as Record<string, unknown>;
  // Recorded, not ignored: `false` is a real answer (section 48).
  expect(sent.false_positive).toBe(false);
  expect(sent.reason).toBeNull();

  await waitFor(() => {
    expect(screen.getByText('Recorded as not a false alarm.')).toBeVisible();
  });
});
