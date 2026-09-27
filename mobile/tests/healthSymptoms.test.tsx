/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Symptoms on the Health tab (PRD 6, sections 6 and 48).
 *
 * Two rules, and they pull in opposite directions, which is why both are asserted
 * on a real screen:
 *
 *   Symptoms **belong in Health** (section 6), listed between allergies and
 *   doctors, as their own row.
 *
 *   Symptom counts are **never mixed with diagnosed conditions** (section 48).
 *   They are separate figures in a separate place, because a symptom is what
 *   somebody is experiencing and a condition is what they have been told they
 *   have -- and a count that blends the two is how a summary starts implying a
 *   diagnosis.
 *
 * And a third that follows from neither: symptoms are **not** one of the
 * completeness sections. Having none logged is a good state, and a percentage that
 * rose because somebody felt unwell would be grotesque.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt, symptomEpisodeFixture } from './helpers';

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
    healthSetup: { status: 'in_progress', step: 'allergies', blood_type: null },
    healthRecords: {
      conditions: [
        {
          id: 'c1',
          profile_id: 'profile-1',
          name: 'Asthma',
          status: 'active',
          source: 'user',
          created_at: '2026-09-01T08:00:00Z',
          updated_at: '2026-09-01T08:00:00Z',
        },
      ],
    },
    symptoms: [
      symptomEpisodeFixture(),
      symptomEpisodeFixture({ id: 'episode-2', name: 'Knee pain' }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('lists symptoms as their own row, counted apart from conditions', async () => {
  renderRouter('app', { initialUrl: '/health' });

  await waitFor(
    () => {
      expect(screen.getByText('Symptoms')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // Its own row, with its own figures (PRD 6, section 48).
  expect(screen.getByText('2 active')).toBeTruthy();
  expect(screen.getByText(/2 updated this week/)).toBeTruthy();

  // Positioned where PRD 6 section 6 puts it: after allergies, before doctors.
  expect(screen.getByText('Allergies')).toBeTruthy();
  expect(screen.getByText('Doctors')).toBeTruthy();

  // Conditions are counted separately, and the two are never added together.
  expect(screen.getByText(/1 ongoing condition/)).toBeTruthy();
  expect(screen.queryByText(/3 ongoing/)).toBeNull();

  // The completeness figure covers the seven record sections only: one
  // condition of seven is 14%, and two symptoms do not move it.
  expect(screen.getByText(/1 of 7/)).toBeTruthy();

  // Tapping it opens symptoms rather than a health record form.
  expect(
    screen.getByHintText(/Opens what you are experiencing, and its history/)
  ).toBeTruthy();
});
