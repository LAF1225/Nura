/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The symptoms overview (PRD 6, sections 4, 7, 49 and 91).
 *
 * Mounted at `/symptoms` through the real router, so this is the screen a user
 * gets: the two equal ways in, what is active, and the way into the history.
 *
 * The first assertion is the one PRD 6 section 4 actually requires -- two options,
 * both present and both offered. A "Talk to Nura" button with "log manually" as a
 * link underneath would satisfy the letter of it and not the point.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  mockBackend,
  signInAt,
  symptomEntryFixture,
  symptomEpisodeFixture,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    symptoms: [
      symptomEpisodeFixture(),
      symptomEpisodeFixture({
        id: 'episode-2',
        name: 'Knee pain',
        body_site: 'left knee',
        latest_entry: symptomEntryFixture({
          id: 'entry-2',
          symptom_episode_id: 'episode-2',
          main_symptom: 'knee pain',
          severity: 3,
          change_state: 'improving',
          associated_symptoms: [],
        }),
      }),
      // Ended, so it must not appear in the active list (PRD 6, section 37).
      symptomEpisodeFixture({
        id: 'episode-3',
        name: 'Sore throat',
        status: 'resolved',
        resolved_at: '2026-09-20T09:00:00Z',
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('offers both ways in, lists what is active, and leaves out what has ended', async () => {
  renderRouter('app', { initialUrl: '/symptoms' });

  // PRD 6 section 4: two equal options, both present.
  await waitFor(
    () => {
      expect(screen.getByRole('button', { name: 'Talk to Nura' })).toBeTruthy();
    },
    { timeout: 20_000 }
  );
  expect(screen.getByRole('button', { name: 'Log manually' })).toBeTruthy();

  // What is active, with the user's own numbers and a worded change state.
  await waitFor(() => {
    expect(screen.getByText('Headache — 5/10')).toBeTruthy();
  });
  expect(screen.getByText('Knee pain — 3/10')).toBeTruthy();
  expect(screen.getAllByText(/Getting worse/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Getting better/).length).toBeGreaterThan(0);

  // Resolved episodes are not in the active list; they are in the history.
  expect(screen.queryByText(/Sore throat/)).toBeNull();
  expect(screen.getByText('All symptoms')).toBeTruthy();

  // The one sentence that comes near advice points away from Nura
  // (PRD 6, section 81).
  expect(screen.getByText(/does not work out what is causing it/)).toBeTruthy();

  // No diagnosis anywhere on the screen. "diagnosed condition" is deliberately
  // not in this list: the description says a symptom is *not* one, which is the
  // distinction PRD 6 section 6 asks to be made. The reviewed safety wording is
  // checked word by word in symptomCopy.test.ts.
  for (const word of [/migraine/i, /probably/i, /you may have/i, /sounds like/i]) {
    expect(screen.queryByText(word)).toBeNull();
  }

  // The active list is fetched with the filter, not fetched whole and trimmed.
  expect(
    backend.requests.some((request) => request.path.includes('symptoms?active=true'))
  ).toBe(true);
});
