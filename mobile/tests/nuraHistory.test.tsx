/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Conversation history (PRD 8, sections 8, 61 and 102).
 *
 * Threads, not one endless log: the list shows each one, archiving moves it
 * out of the way, and showing archived brings it back into view.
 *
 * The assertion that matters most is the last one. Section 61 promises that
 * deleting a conversation does not delete medications, symptoms,
 * appointments, health records or memories -- so the test deletes one and
 * checks that the only request the app made was to the assistant's own
 * route. A delete that quietly reached elsewhere would show up here.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import { useHistoryListStore } from '../src/features/nura/listStore';
import { conversationFixture, memoryFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useHistoryListStore.setState({ showArchived: false });
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    conversations: [
      conversationFixture(),
      conversationFixture({
        id: 'conversation-2',
        title: 'Appointment questions',
        archived_at: '2026-09-27T09:00:00Z',
      }),
    ],
    memories: [memoryFixture()],
  });
});

afterEach(() => {
  backend.restore();
  jest.restoreAllMocks();
});

it('lists threads, archives one, and deletes one without touching anything else', async () => {
  // The delete confirmation is a platform alert. Taking the destructive
  // button straight away is what a user pressing Delete then confirming
  // does, and it keeps the promise in section 61 under test rather than
  // the dialog.
  jest.spyOn(Alert, 'alert').mockImplementation((_title, _message, buttons) => {
    const destructive = buttons?.find((button) => button.style === 'destructive');
    destructive?.onPress?.();
  });

  renderRouter('app', { initialUrl: '/nura/history' });

  await waitFor(() => {
    expect(screen.getByText('What does inflammation mean?')).toBeVisible();
  });
  // Archived threads are out of the way until asked for (section 8).
  expect(screen.queryByText('Appointment questions')).toBeNull();

  fireEvent.press(screen.getByRole('button', { name: 'Show archived' }));
  await waitFor(() => {
    expect(screen.getByText('Appointment questions')).toBeVisible();
  });
  expect(screen.getByText('Archived')).toBeVisible();

  // Archiving the open one.
  fireEvent.press(screen.getByLabelText('Archive: What does inflammation mean?'));
  await waitFor(() => {
    const archived = backend.state.conversations.find(
      (entry) => entry.id === 'conversation-1'
    );
    expect(archived?.archived).toBe(true);
  });

  // --- deleting one (section 61) -------------------------------------------
  const before = backend.requests.length;
  fireEvent.press(
    screen.getByLabelText('Delete conversation: What does inflammation mean?')
  );

  await waitFor(() => {
    expect(backend.state.conversations).toHaveLength(1);
  });

  // Every request the delete produced went to the assistant's own routes.
  // Nothing reached a medication, a symptom, an appointment or the record.
  const after = backend.requests.slice(before);
  expect(after.length).toBeGreaterThan(0);
  for (const request of after) {
    expect(request.path).toContain('/assistant/');
  }
  // And the memory is still there.
  expect(backend.state.memories).toHaveLength(1);
});
