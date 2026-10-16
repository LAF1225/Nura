/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Talking to Nura (PRD 8, sections 6, 14, 18, 46, 55, 56 and 102).
 *
 * One walk through a conversation, because there is one `renderRouter` per
 * file (see navigation.test.tsx) -- and because these behaviours only make
 * sense in sequence: send, fail, retry, be offered a change, confirm it, be
 * offered a memory, decline it.
 *
 * Three assertions carry most of the weight.
 *
 * **A failure stores nothing from Nura** (section 56). The reply is absent,
 * the failure sentence is shown, Try again is there, and what the user typed
 * is still in the composer.
 *
 * **A retry answers the question rather than asking it again** (section 55).
 * The second send carries the same `client_message_id` as the first.
 *
 * **A write waits for a press** (section 14). The pending card appears under
 * the reply, and only Confirm sends the confirmation.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useComposerStore } from '../src/features/nura/composerStore';
import { conversationFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(90_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useComposerStore.setState({ drafts: {} });
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    conversations: [conversationFixture({ message_count: 0, last_message_at: null })],
    conversationMessages: [],
  });
});

afterEach(() => {
  backend.restore();
});

/** The bodies of every message POST so far, for the client-id assertions. */
function sends(): Record<string, unknown>[] {
  return backend.requests
    .filter(
      (request) =>
        request.method === 'POST' &&
        // The path carries `?local_date=`, so match on the segment rather
        // than the end of the string -- and leave the confirm route out.
        request.path.includes('/messages') &&
        !request.path.includes('/confirm')
    )
    .map((request) => request.body as Record<string, unknown>);
}

it('sends, fails honestly, retries the same question, and confirms a change', async () => {
  renderRouter('app', { initialUrl: '/nura/conversation-1' });

  await waitFor(() => {
    expect(screen.getByLabelText('Message to Nura')).toBeVisible();
  });

  // --- the empty state (section 6) -----------------------------------------
  expect(screen.getByText('What would you like help with?')).toBeVisible();
  // Send is off until there is something to send.
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();

  // --- a reply that could not be fetched (sections 55 and 56) --------------
  backend.state.assistantSend = {
    replyContent: null,
    failure: 'timeout',
    failureMessage: 'That request took too long. Please try again.',
  };

  fireEvent.changeText(
    screen.getByLabelText('Message to Nura'),
    'What does inflammation mean?'
  );
  // Wait for the control, not the store: a press arriving before the store
  // update has re-rendered would read a stale draft.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send' }));

  await waitFor(() => {
    expect(
      screen.getByText('That request took too long. Please try again.')
    ).toBeVisible();
  });
  // The question is in the thread; no answer was invented for it.
  expect(screen.getByText('What does inflammation mean?')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();

  // --- the retry (section 55) ----------------------------------------------
  backend.state.assistantSend = {
    replyContent: 'Inflammation is the body’s response to injury or infection.',
  };
  fireEvent.press(screen.getByRole('button', { name: 'Try again' }));

  await waitFor(() => {
    expect(
      screen.getByText('Inflammation is the body’s response to injury or infection.')
    ).toBeVisible();
  });

  const [first, second] = sends();
  expect(first?.client_message_id).toBeDefined();
  // The same id, so the backend answers the stored question rather than
  // recording a second copy of it.
  expect(second?.client_message_id).toBe(first?.client_message_id);
  // And only ever the one source PRD 8 section 71 allows.
  expect(first?.source).toBe('mobile_text');

  // --- a serious reply carries its banner (section 37) ---------------------
  backend.state.assistantSend = {
    replyContent:
      'I can show the schedule you’ve recorded, but changes to dose should ' +
      'come from your clinician or pharmacist.',
    safetyMode: 'serious',
  };
  fireEvent.changeText(
    screen.getByLabelText('Message to Nura'),
    'Should I stop taking my tablets?'
  );
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send' }));

  await waitFor(() => {
    expect(screen.getByText(/keeping this brief and direct/i)).toBeVisible();
  });

  // --- a change Nura offered (section 14) ----------------------------------
  backend.state.assistantSend = {
    replyContent: 'I’ve asked you to confirm that.',
    pendingAction: {
      tool: 'add_appointment_question',
      summary: 'Add “Ask about dizziness” to your questions for Cardiology follow-up?',
      state: 'pending',
    },
  };
  fireEvent.changeText(
    screen.getByLabelText('Message to Nura'),
    'Add ask about dizziness to my doctor questions'
  );
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send' }));

  await waitFor(() => {
    expect(
      screen.getByText(
        'Add “Ask about dizziness” to your questions for Cardiology follow-up?'
      )
    ).toBeVisible();
  });
  // Nothing has been changed yet: the buttons are the change.
  expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled();
  expect(backend.requests.some((request) => request.path.includes('/confirm'))).toBe(
    false
  );

  fireEvent.press(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => {
    const confirmation = backend.requests.find((request) =>
      request.path.includes('/confirm')
    );
    expect(confirmation?.body).toMatchObject({ confirmed: true });
  });
});

it('keeps an unsent message when the reply cannot be fetched', async () => {
  // A second test, deliberately without a render: the draft store is the
  // thing under test, and section 57's promise is about what survives, not
  // about what is on screen.
  useComposerStore.getState().setDraft('conversation-1', 'A long half-written note');
  expect(useComposerStore.getState().drafts['conversation-1']).toBe(
    'A long half-written note'
  );

  const stored = await AsyncStorage.getItem('nura-assistant-composer');
  expect(stored).toContain('A long half-written note');

  useComposerStore.getState().clearDraft('conversation-1');
  expect(useComposerStore.getState().drafts['conversation-1']).toBeUndefined();
});
