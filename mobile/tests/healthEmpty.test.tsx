/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * A section with nothing in it yet (PRD 4, sections 37 and 51).
 *
 * An empty section is a starting point, not a gap. It explains what belongs
 * there and offers to add the first one -- and never says "No data".
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
  backend = mockBackend({ status: 'ready_for_pairing', healthRecords: {} });
});

afterEach(() => {
  backend.restore();
});

it('invites a first entry rather than reporting an absence', async () => {
  renderRouter('app', { initialUrl: '/health/allergies' });

  await waitFor(
    () => {
      expect(screen.getByText('No allergies added yet.')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // Says what belongs here, and that Nura will not judge it.
  expect(screen.getByText(/Anything that causes you a reaction/)).toBeTruthy();
  expect(screen.getByText(/does not work out how serious it is/)).toBeTruthy();

  expect(screen.getByRole('button', { name: 'Add an allergy' })).toBeTruthy();
  expect(screen.queryByText(/no data/i)).toBeNull();
});
