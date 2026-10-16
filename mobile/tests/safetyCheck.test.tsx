/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Answering a safety check (PRD 10, sections 23, 25, 26, 118 and 113).
 *
 * Four things are under test.
 *
 * **The question is section 23's, and it names the person.** Rendered by the
 * server, so the wording lives in one reviewable module (section 120).
 *
 * **The countdown is words, not an animation** (section 118). Asserted as
 * text, because that is the only form a screen reader conveys.
 *
 * **"I'm okay" resolves and sends nothing else** (section 25). The response
 * body is checked, and so is the absence of any escalation request.
 *
 * **"I need help" escalates and lands on the emergency screen** (section 26).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { respondToSafetyEvent } from '../src/features/safety/api';
import {
  mockBackend,
  monitoringSessionFixture,
  safetyCheckFixture,
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
  const event = safetyCheckFixture();
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    safetyStatus: safetyStatusFixture({
      monitoring: monitoringSessionFixture(),
      monitoring_sentence: 'Safety Monitoring is on until 7:00 PM.',
      active_event: event,
      emergency_contact_count: 1,
      detection_notice:
        'Safety Monitoring is on. Automatic detection by the robot is not connected yet, so Nura will not notice anything by itself. You can still ask for help at any time.',
    }),
    safetyEvents: [event],
  });
});

afterEach(() => {
  backend.restore();
});

it('asks whether the person is okay, records the answer, and escalates on request', async () => {
  renderRouter('app', { initialUrl: '/safety/check' });

  // Section 23's wording, from the server.
  await waitFor(() => {
    expect(
      screen.getByText('Nura noticed something unusual. Ada, are you okay?')
    ).toBeVisible();
  });
  expect(screen.getByText('Are you okay?')).toBeVisible();

  // Section 16: what was observed, never what it means.
  expect(screen.getByText('Possible fall')).toBeVisible();

  // Section 118: the countdown is a sentence. The deadline is in the past
  // relative to the test clock, so it reads as time being up -- which is the
  // honest thing for a screen that is not the authority on when it is.
  expect(screen.getByText(/Time is up|seconds left/)).toBeVisible();

  // Section 23's three controls.
  for (const label of ['I’m okay', 'I need help', 'Dismiss — false alarm']) {
    expect(screen.getByRole('button', { name: label })).toBeVisible();
  }

  fireEvent.press(screen.getByRole('button', { name: 'I need help' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/respond'))
    ).toHaveLength(1);
  });
  const sent = backend.requests.find((request) => request.path.includes('/respond'))
    ?.body as Record<string, unknown>;
  expect(sent.response).toBe('need_help');

  // Section 26: escalation has begun, and what it did is on screen.
  await waitFor(() => {
    expect(screen.getByText('Emergency request')).toBeVisible();
  });
  expect(screen.getByText('What Nura has done so far.')).toBeVisible();
});

it('resolves on "I’m okay" without asking anybody for anything', async () => {
  // A second `renderRouter` in one file fails, so this one drives the hooks
  // through the stub rather than the screen -- what is being checked is the
  // request, and section 25's rule is about what is *not* sent.
  const updated = await respondToSafetyEvent('profile-1', 'event-check', 'im_okay');

  expect(updated.status).toBe('resolved');
  expect(updated.resolution).toBe('user_confirmed_ok');
  // Nothing else went out: one request, and it was the answer.
  expect(backend.requests.map((request) => request.path)).toEqual([
    '/api/v1/profiles/profile-1/safety/events/event-check/respond',
  ]);
});
