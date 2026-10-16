/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Talk to Nura, end to end (PRD 6, sections 26-30, 67, 91 and 96).
 *
 * The flow a user actually gets: a guided conversation, a review screen showing
 * what was captured, and a save that lands as an ordinary symptom record with its
 * source recorded as the guided flow.
 *
 * **Why the conversation is driven through the store rather than the text box.**
 * React 19 with this version of React Native Testing Library does not flush a
 * local `useState` update from `fireEvent.changeText`, so typing into the answer
 * box and pressing Send cannot be exercised here (the same limitation PRD 3
 * documented). Everything that matters is still driven the way a user drives it:
 * the conversation, the draft and the review all live in a Zustand store, so
 * tapping an offered answer *does* re-render, and `say()` is the exact function the
 * Send button calls. What is untested is one text input, not the flow.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  waitFor,
} from 'expo-router/testing-library';

import { useSymptomDraftStore } from '../src/features/symptoms/draftStore';
import { localDateString } from '../src/utils/date';
import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(90_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing', todayDevice: null, symptoms: [] });
  useSymptomDraftStore.setState({
    draft: null,
    conversation: null,
    episodeName: null,
    recurOf: null,
    hydrated: true,
  });
  useSymptomDraftStore.getState().start('guided_app');
});

afterEach(() => {
  backend.restore();
  useSymptomDraftStore.getState().clear();
});

it('captures a volunteered description, asks nothing again, and saves what was reviewed', async () => {
  renderRouter('app', { initialUrl: '/symptoms/talk' });

  // Nura opens by asking what is happening.
  await waitFor(
    () => {
      expect(screen.getByText('What are you experiencing?')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // One message volunteering five fields (PRD 6, section 28's own example).
  await act(async () => {
    useSymptomDraftStore
      .getState()
      .say('I have a sharp pain in my left knee that started yesterday and is 6/10');
  });

  // The answer is on screen as the user's own words, attributed to them for a
  // screen reader (PRD 6, section 66).
  await waitFor(() => {
    expect(screen.getByText(/I have a sharp pain in my left knee/)).toBeTruthy();
  });
  expect(
    screen.getByLabelText(/You said: I have a sharp pain in my left knee/)
  ).toBeTruthy();

  // And none of what was volunteered is asked again.
  expect(screen.queryByText(/Where do you feel it\?/)).toBeNull();
  expect(screen.queryByText(/When did it start\?/)).toBeNull();
  expect(screen.queryByText(/What does it feel like\?/)).toBeNull();
  expect(screen.queryByText(/How bad is it right now\?/)).toBeNull();

  const draft = useSymptomDraftStore.getState().draft;
  expect(draft?.mainSymptom).toBe('knee pain');
  expect(draft?.site).toBe('left knee');
  expect(draft?.character).toBe('sharp');
  expect(draft?.severity).toBe(6);

  // Answering by tapping works, which is what PRD 6 section 67 requires.
  const choice = screen.queryByRole('button', { name: 'Nothing else' });
  if (choice !== null) {
    fireEvent.press(choice);
    await waitFor(() => {
      expect(screen.getByText('Nothing else')).toBeTruthy();
      expect(screen.getByLabelText(/You said: Nothing else/)).toBeTruthy();
    });
  }

  // The user decides they have said enough.
  fireEvent.press(screen.getByRole('button', { name: 'That’s everything' }));
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Review and save' })).toBeTruthy();
  });

  // --- the review screen (PRD 6, sections 30 and 76) ------------------------
  fireEvent.press(screen.getByRole('button', { name: 'Review and save' }));

  await waitFor(() => {
    expect(screen.getByText('Review symptom')).toBeTruthy();
  });
  // Twice: as the summary's heading and as the "Symptom" row.
  expect(screen.getAllByText('knee pain')).toHaveLength(2);
  expect(screen.getByText('left knee')).toBeTruthy();
  expect(screen.getByText('sharp')).toBeTruthy();
  expect(screen.getByText('6/10')).toBeTruthy();
  // Editing is offered before saving, not only afterwards.
  expect(screen.getByRole('button', { name: 'Edit' })).toBeTruthy();

  // --- saving ---------------------------------------------------------------
  fireEvent.press(screen.getByRole('button', { name: 'Save' }));

  await waitFor(() => {
    const created = backend.requests.find(
      (request) => request.method === 'POST' && request.path.endsWith('/symptoms')
    );
    expect(created).toBeDefined();
  });

  const created = backend.requests.find(
    (request) => request.method === 'POST' && request.path.endsWith('/symptoms')
  );
  const body = created?.body as Record<string, unknown>;
  const entry = body.first_entry as Record<string, unknown>;

  // The guided flow is recorded as its own source (PRD 6, section 57)...
  expect(body.source).toBe('guided_app');
  expect(entry.source).toBe('guided_app');
  // ...and produces the same structured record the manual form would
  // (PRD 6, section 4).
  expect(body.name).toBe('knee pain');
  expect(entry.site).toBe('left knee');
  expect(entry.character).toBe('sharp');
  expect(entry.severity).toBe(6);
  // Yesterday on the *device's* calendar, which is what the conversation
  // resolved "yesterday" against. `toISOString` would convert to UTC first and
  // disagree with it for the hours when the two dates differ.
  expect(entry.onset_date).toBe(localDateString(new Date(Date.now() - 86_400_000)));
  // The idempotency key was generated before the request, not by it.
  expect(String(entry.client_entry_id)).toMatch(/^entry-/);

  // The draft is cleared once it is stored, so nothing lingers as a half-record
  // (PRD 6, section 29).
  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft).toBeNull();
  });
});
