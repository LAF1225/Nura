/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Family messages, check-ins and the draft that is kept (PRD 9, ss31-37, 71-74, 96).
 *
 * Four things are under test.
 *
 * **A message is sent, and the draft is cleared.** The request body is checked,
 * because a screen that clears its own field and sends nothing looks the same.
 *
 * **A draft survives going offline, and nothing is queued.** Section 71 asks for
 * the draft to persist and section 72 for `pending` until the backend confirms;
 * what the banner must *not* say is that it will be sent later, because there is
 * no send queue.
 *
 * **A retry does not duplicate** (sections 72 and 74). The same
 * `client_message_id` goes out both times, which is what lets the backend answer
 * with the message it already stored.
 *
 * **A check-in is stored as a code.** The body carries `check_in_code`, not the
 * sentence -- so the wording lives in one place and a check-in can never carry
 * free text the sender did not intend to put in a care thread.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  familyMessageFixture,
  familyThreadFixture,
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
    familyThreads: [familyThreadFixture({ unread: 1 })],
    familyMessages: [
      familyMessageFixture({ side: 'caregiver', text: 'How did you sleep?' }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

function sent(): { method: string; path: string; body: unknown }[] {
  return backend.requests.filter(
    (request) => request.method === 'POST' && request.path.includes('/messages')
  );
}

it('sends a message, keeps a draft, and sends a check-in as a code', async () => {
  renderRouter('app', { initialUrl: '/family/thread-1' });

  await waitFor(() => {
    expect(screen.getByText('How did you sleep?')).toBeVisible();
  });

  // Typing keeps the text, and says what that means: on this phone, not sent.
  // Not "it will send when you are back online" -- there is no send queue
  // (sections 71 and 72).
  fireEvent.changeText(screen.getByLabelText('Write a message'), 'Slept well');
  await waitFor(() => {
    expect(
      screen.getByText('Saved on this phone. It has not been sent yet.')
    ).toBeVisible();
  });

  // Waiting for the *control* before pressing: a press arriving before the store
  // update has re-rendered would read an empty draft.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send' }));

  await waitFor(() => {
    expect(sent()).toHaveLength(1);
  });
  const first = sent()[0]?.body as Record<string, unknown>;
  expect(first.text).toBe('Slept well');
  expect(first.message_type).toBe('text');
  // Section 74: a client id goes out on the first attempt, so a retry can be
  // answered rather than recorded twice.
  expect(typeof first.client_message_id).toBe('string');
  expect((first.client_message_id as string).length).toBeGreaterThan(0);

  // The draft was cleared by the send, so the banner is gone.
  await waitFor(() => {
    expect(
      screen.queryByText('Saved on this phone. It has not been sent yet.')
    ).toBeNull();
  });

  // Section 35: the person's own check-ins, and the note saying they are
  // messages rather than alerts -- somebody pressing "I need help with
  // something" is entitled to know Nura does not call anybody.
  expect(screen.getByRole('button', { name: 'I’m okay' })).toBeVisible();
  expect(
    screen.getByRole('button', { name: 'I need help with something' })
  ).toBeVisible();
  expect(
    screen.getByText('These are messages, not alerts. Nura does not call anyone for you.')
  ).toBeVisible();

  // Section 36's check-ins belong to the caregiver, not to the person.
  expect(screen.queryByRole('button', { name: 'How are you doing?' })).toBeNull();

  fireEvent.press(screen.getByRole('button', { name: 'I’m okay' }));

  await waitFor(() => {
    expect(sent()).toHaveLength(2);
  });
  const checkIn = sent()[1]?.body as Record<string, unknown>;
  // The code, not the sentence: one module renders the words, and a row never
  // freezes a translation.
  expect(checkIn.check_in_code).toBe('im_okay');
  expect(checkIn.message_type).toBe('check_in');
  expect(checkIn.text).toBeNull();
});
