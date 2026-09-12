/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Setup-mode step (PRD 1, sections 16, 17, 29 and 43).
 *
 * Scope note: this asserts routing, rendered content and what reaches the
 * network. It deliberately does not drive a multi-step interaction, because
 * component-local `useState` does not re-render under this Jest setup -- see
 * the "Known issues" section of the README. The rules those interactions
 * enforce (the consent gate, profile validation, progression order) are
 * covered against a real database in backend/tests/test_onboarding.py.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('authenticated');
  backend = mockBackend({ status: 'authenticated' });
});

afterEach(() => {
  backend.restore();
});

it('routes a newly authenticated user to step 1 and holds until they choose', async () => {
  renderRouter('app', { initialUrl: '/' });

  // Authenticated but not onboarded: the gate sends them to step 1, not the
  // main app (PRD 1, section 6).
  await waitFor(
    () => {
      expect(screen.getByText('Who are you setting up Nura for?')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(screen.getByText('Step 1 of 5')).toBeTruthy();
  expect(screen.getByRole('radio', { name: 'For myself' })).toBeTruthy();
  expect(screen.getByRole('radio', { name: 'For someone else' })).toBeTruthy();

  // Neither "patient" nor "caregiver" appears at this point (PRD 1, section 16).
  expect(screen.queryByText(/patient|caregiver/i)).toBeNull();

  // The five-tab navigation is not shown during onboarding (PRD 1, section 43).
  expect(screen.queryByRole('button', { name: /^Health, tab/ })).toBeNull();

  // Signing out is available but not prominent (PRD 1, section 45).
  expect(screen.getByRole('button', { name: /different account/i })).toBeTruthy();

  // Continue sends nothing while no option is selected.
  fireEvent.press(screen.getByRole('button', { name: 'Continue' }));
  expect(backend.requests.filter((request) => request.method === 'PATCH')).toHaveLength(
    0
  );
});
