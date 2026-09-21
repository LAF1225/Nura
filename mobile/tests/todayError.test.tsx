/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today when the backend cannot answer (PRD 3, sections 29, 30 and 64).
 *
 * Two rules: the screen never renders as an unexplained blank page, and the
 * user never sees a status code or an exception message -- only the wording
 * from the app's own error vocabulary, with a way to try again.
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
  backend = mockBackend({ status: 'ready_for_pairing', todayStatus: 503 });
});

afterEach(() => {
  backend.restore();
});

it('explains that today could not be loaded, and offers to try again', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText(/Nura can’t load today’s information/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy();
  // The wording comes from the app's typed error vocabulary.
  expect(screen.getByText(/Something went wrong on our side/)).toBeTruthy();
  // Never a status code or a raw message.
  expect(screen.queryByText(/503/)).toBeNull();

  // The greeting still renders, so the screen is a page, not a blank error.
  expect(screen.getByText(/^Good (morning|afternoon|evening)/)).toBeTruthy();
});
