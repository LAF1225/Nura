/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Adding a follow-up (PRD 6, sections 23, 47, 61 and 91).
 *
 * PRD 6 section 47's requirement is mostly about what is *absent*: a later update
 * must not make somebody re-enter the original description. So the strongest
 * assertions here are the negative ones -- no name field, no onset, no location,
 * no character -- and then that the update lands as an ordinary entry on the
 * existing episode rather than as a new symptom.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useSymptomDraftStore } from '../src/features/symptoms/draftStore';
import { clearAllPendingEntries } from '../src/features/symptoms/pendingEntries';
import { mockBackend, signInAt, symptomEpisodeFixture } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(90_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await clearAllPendingEntries();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    symptoms: [symptomEpisodeFixture()],
  });
  useSymptomDraftStore.setState({
    draft: null,
    conversation: null,
    episodeName: null,
    recurOf: null,
    hydrated: true,
  });
});

afterEach(() => {
  backend.restore();
  useSymptomDraftStore.getState().clear();
});

it('asks only what can have changed, and saves it onto the same symptom', async () => {
  renderRouter('app', { initialUrl: '/symptoms/episode-1/update' });

  await waitFor(
    () => {
      expect(screen.getByLabelText(/How bad is it right now\?/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The description already recorded is shown, not re-asked
  // (PRD 6, section 47).
  expect(screen.getByText('Headache — 5/10')).toBeTruthy();
  expect(screen.queryByLabelText(/What are you experiencing\?/)).toBeNull();
  expect(screen.queryByLabelText(/When did it start\?/)).toBeNull();
  expect(screen.queryByLabelText(/Where do you feel it\?/)).toBeNull();
  expect(screen.queryByLabelText(/What does it feel like\?/)).toBeNull();

  // What it does ask: how bad, which way it is going, anything new, a note, a
  // photo.
  expect(screen.getByLabelText(/How is it compared with last time\?/)).toBeTruthy();
  expect(screen.getByLabelText(/Anything else along with it\?/)).toBeTruthy();
  expect(screen.getByLabelText(/Anything else you want to remember\?/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Take a photo' })).toBeTruthy();

  // The draft knows which symptom it belongs to.
  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft?.episodeId).toBe('episode-1');
  });

  // --- the update ----------------------------------------------------------
  fireEvent.press(screen.getByLabelText('7 out of 10'));
  fireEvent.press(screen.getByLabelText('Getting worse'));
  fireEvent.changeText(
    screen.getByLabelText(/Anything else along with it\?/),
    'light sensitivity'
  );

  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft?.severity).toBe(7);
  });

  // Waiting on the *button* rather than only on the store: Save stays disabled
  // until there is something to save, and a press that arrives before the
  // screen has re-rendered lands on a disabled control and does nothing --
  // which is correct behaviour, and something a test has to respect.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Review and save' })).toBeEnabled();
  });

  fireEvent.press(screen.getByRole('button', { name: 'Review and save' }));
  await waitFor(() => {
    expect(screen.getByText('Review symptom')).toBeTruthy();
  });

  // The review names the symptom even though this draft has no name of its own.
  expect(screen.getByText('Headache')).toBeTruthy();
  expect(screen.getByLabelText('How bad: 7/10')).toBeTruthy();

  fireEvent.press(screen.getByRole('button', { name: 'Save' }));

  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) =>
          request.method === 'POST' &&
          request.path.endsWith('/symptoms/episode-1/entries')
      )
    ).toBe(true);
  });

  const entry = backend.requests.find(
    (request) =>
      request.method === 'POST' && request.path.endsWith('/symptoms/episode-1/entries')
  );
  const body = entry?.body as Record<string, unknown>;

  expect(body.severity).toBe(7);
  expect(body.change_state).toBe('worsening');
  expect(body.associated_symptoms).toEqual(['light sensitivity']);
  // Nothing was re-sent about the original description.
  expect(body.main_symptom).toBeNull();
  expect(body.site).toBeNull();
  expect(body.character).toBeNull();
  // And no second episode was created (PRD 6, section 61).
  expect(
    backend.requests.filter(
      (request) => request.method === 'POST' && request.path.endsWith('/symptoms')
    )
  ).toHaveLength(0);
});
