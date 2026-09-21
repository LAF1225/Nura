/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Health tab with a partly-filled profile (PRD 4, sections 19, 51 and 58).
 *
 * Two things this is really checking: that a partial profile reads as a normal
 * state rather than a warning, and that **none of it needs a robot** -- the
 * stubbed account has no device at all (PRD 4, sections 38 and 49).
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    preferredName: 'Ada',
    // No robot linked, and no device state of any kind.
    todayDevice: null,
    devices: [],
    healthSetup: { status: 'in_progress', step: 'allergies', blood_type: 'O+' },
    healthRecords: {
      conditions: [
        {
          id: 'c1',
          profile_id: 'profile-1',
          name: 'Asthma',
          status: 'active',
          diagnosed_year: 2015,
          diagnosed_date: null,
          source: 'user',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        },
        {
          id: 'c2',
          profile_id: 'profile-1',
          name: 'Ankle sprain',
          status: 'resolved',
          diagnosed_year: 2021,
          diagnosed_date: null,
          source: 'user',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        },
      ],
      medications: [
        {
          id: 'm1',
          profile_id: 'profile-1',
          name: 'Salbutamol',
          is_active: true,
          source: 'user',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        },
      ],
    },
  });
});

afterEach(() => {
  backend.restore();
});

it('shows what the profile holds, as counts, with no robot linked', async () => {
  renderRouter('app', { initialUrl: '/health' });

  await waitFor(
    () => {
      expect(screen.getByText('Your profile is partly complete')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // Three of seven sections have something: conditions, medications, blood type.
  expect(screen.getByText('3 of 7 sections have information.')).toBeTruthy();

  // Counts, never the names of what is in them (PRD 4, section 33).
  expect(screen.getByText('2 added')).toBeTruthy();
  expect(screen.getByText('1 added')).toBeTruthy();
  expect(screen.getByText('O positive')).toBeTruthy();
  expect(screen.queryByText('Asthma')).toBeNull();
  expect(screen.queryByText('Salbutamol')).toBeNull();

  // Sections with nothing in them say so plainly, and are not flagged.
  expect(screen.getAllByText('Not added yet').length).toBeGreaterThan(0);

  // "What are you dealing with now" is answered separately from the totals.
  expect(screen.getByText(/1 ongoing condition/)).toBeTruthy();
  expect(screen.getByText(/1 medication you are taking/)).toBeTruthy();

  // Partial is a normal state: an invitation to continue, not a warning.
  expect(screen.getByRole('button', { name: 'Continue setup' })).toBeTruthy();
  expect(screen.queryByText(/incomplete/i)).toBeNull();
  expect(screen.queryByText(/missing/i)).toBeNull();

  // PRD 4, section 55.
  expect(screen.getByText(/Nothing here has been checked by a clinician/)).toBeTruthy();

  // The whole screen loaded without a single device request.
  expect(
    backend.requests.some((request) => request.path.startsWith('/api/v1/devices'))
  ).toBe(false);
});
