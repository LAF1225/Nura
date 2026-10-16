/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * What Nura offers after a reply, and how it reads (PRD 8, ss18, 46, 68, 83).
 *
 * Three offers and one banner, all on the conversation screen:
 *
 * **A memory is proposed, never taken** (section 46). The card is section
 * 94's shape, and nothing is written until Remember is pressed.
 *
 * **A new symptom goes to the PRD 6 flow** (section 18) rather than being
 * discussed in chat.
 *
 * **Privacy mode is clearly indicated** (section 68).
 *
 * The accessibility assertions are section 83's: a screen reader moving down
 * a thread should hear who is speaking before what was said, and every
 * control should have a name that means something on its own.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useComposerStore } from '../src/features/nura/composerStore';
import {
  assistantPreferencesFixture,
  conversationFixture,
  mockBackend,
  signInAt,
} from './helpers';

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
    // Privacy mode, so the banner has something to render (section 68).
    assistantPreferences: assistantPreferencesFixture({ mode: 'privacy' }),
  });
});

afterEach(() => {
  backend.restore();
});

/** Types a message and sends it, waiting for the control between the two. */
async function say(text: string) {
  fireEvent.changeText(screen.getByLabelText('Message to Nura'), text);
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Send' }));
}

it('offers a memory and a symptom log without taking either, and reads aloud sensibly', async () => {
  renderRouter('app', { initialUrl: '/nura/conversation-1' });

  await waitFor(() => {
    expect(screen.getByLabelText('Message to Nura')).toBeVisible();
  });

  // Section 68: Privacy mode is clearly indicated.
  expect(screen.getByText(/Privacy mode is on/i)).toBeVisible();

  // --- a durable preference is offered (sections 46 and 94) ----------------
  backend.state.assistantSend = {
    replyContent: 'Of course.',
    memorySuggestion: {
      category: 'communication',
      content: 'Prefers to be called Baba.',
    },
  };
  await say('Please call me Baba.');

  await waitFor(() => {
    expect(screen.getByText('Would you like Nura to remember this?')).toBeVisible();
  });
  expect(screen.getByText('Prefers to be called Baba.')).toBeVisible();
  // Nothing has been saved: the buttons are the decision.
  expect(
    backend.requests.some(
      (request) => request.method === 'POST' && request.path.includes('/memories')
    )
  ).toBe(false);

  fireEvent.press(screen.getByRole('button', { name: 'Remember' }));
  await waitFor(() => {
    const saved = backend.requests.find(
      (request) => request.method === 'POST' && request.path.includes('/memories')
    );
    expect(saved?.body).toMatchObject({
      content: 'Prefers to be called Baba.',
      category: 'communication',
      // Section 46: it came from a conversation, and a person said yes.
      source: 'conversation',
    });
  });

  // --- a new symptom is handed to PRD 6 (section 18) -----------------------
  backend.state.assistantSend = {
    replyContent: 'I can help you record that.',
    suggestSymptomLog: true,
  };
  await say('I have been feeling dizzy.');

  await waitFor(() => {
    expect(screen.getByText(/record that as a symptom/i)).toBeVisible();
  });
  // Both of section 18's buttons, and neither of them discusses the symptom.
  expect(screen.getByRole('button', { name: 'Record a symptom' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'No, just asking' })).toBeVisible();

  // --- accessibility (section 83) ------------------------------------------
  // Every bubble says who is speaking before what was said, so a screen
  // reader moving down the thread can follow the conversation.
  expect(screen.getByLabelText('You: Please call me Baba.')).toBeVisible();
  expect(screen.getByLabelText('Nura: Of course.')).toBeVisible();
  expect(screen.getByLabelText('Nura: I can help you record that.')).toBeVisible();

  // And no control is announced as a bare word with no context.
  for (const button of screen.getAllByRole('button')) {
    const label = String(button.props.accessibilityLabel ?? '');
    expect(label.length).toBeGreaterThan(2);
  }
});
