/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Nura tab (PRD 8, sections 5, 34-36 and 102).
 *
 * The assistant is the point of the screen, so the test walks it the way a
 * user would: see what Nura is offering, wave one of them away, and start a
 * conversation.
 *
 * The prompt assertions are the ones worth having. Section 35 says a
 * proactive message must come from data the app already holds and must never
 * invent a medical concern; section 36 says a dismissal sticks. Both are
 * checked against what the screen actually shows and what it actually sent.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  conversationFixture,
  mockBackend,
  proactivePromptFixture,
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
    conversations: [conversationFixture()],
    assistantPrompts: [
      proactivePromptFixture(),
      proactivePromptFixture({
        kind: 'appointment_preparation',
        subject_key: 'appointment-1',
        text: 'You have an appointment tomorrow — Cardiology follow-up.',
        route: '/appointments/appointment-1/prepare',
        action_label: 'Prepare now',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('offers what Nura can help with, remembers a dismissal, and opens a conversation', async () => {
  renderRouter('app', { initialUrl: '/nura' });

  // The intro, and the prompts built from data the app already has.
  await waitFor(() => {
    expect(screen.getByText(/calm companion for everyday health/i)).toBeVisible();
  });
  expect(screen.getByText('You haven’t completed today’s check-in yet.')).toBeVisible();
  expect(
    screen.getByText('You have an appointment tomorrow — Cardiology follow-up.')
  ).toBeVisible();

  // Section 35: nothing Nura raises is a conclusion about health. Read every
  // prompt on screen rather than the one this test happens to care about.
  for (const word of ['serious', 'worrying', 'urgent', 'diagnos', 'should see']) {
    expect(screen.queryByText(new RegExp(word, 'i'))).toBeNull();
  }

  // The thread already there is listed, and the settings are reachable.
  expect(screen.getByText('What does inflammation mean?')).toBeVisible();
  expect(screen.getByText('Personality')).toBeVisible();
  expect(screen.getByText('What Nura remembers')).toBeVisible();

  // Section 36: "Not now" posts a dismissal rather than hiding a card.
  fireEvent.press(
    screen.getByLabelText('Not now: You haven’t completed today’s check-in yet.')
  );
  await waitFor(() => {
    expect(screen.queryByText('You haven’t completed today’s check-in yet.')).toBeNull();
  });

  const dismissal = backend.requests.find((request) =>
    request.path.includes('/assistant/prompts/dismiss')
  );
  expect(dismissal?.method).toBe('POST');
  expect(dismissal?.body).toMatchObject({
    kind: 'daily_checkin',
    subject_key: '2026-09-28',
  });

  // And the appointment prompt is still there: a dismissal is scoped to the
  // thing it was about.
  expect(
    screen.getByText('You have an appointment tomorrow — Cardiology follow-up.')
  ).toBeVisible();

  // Starting a conversation creates one and opens it (section 8).
  fireEvent.press(screen.getByRole('button', { name: 'New conversation' }));
  await waitFor(() => {
    expect(screen.getByLabelText('Message to Nura')).toBeVisible();
  });

  const created = backend.requests.find(
    (request) =>
      request.method === 'POST' && request.path.endsWith('/assistant/conversations')
  );
  expect(created).toBeDefined();
});
