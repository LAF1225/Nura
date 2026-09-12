/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Save-and-resume (PRD 1, sections 30 and 53).
 *
 * Closing the app partway through onboarding and reopening it must land on the
 * step the user stopped at -- not back at the beginning, and not skipping
 * ahead into the main app.
 *
 * This mounts at "/" the way a cold launch does, so the gate has to do the
 * routing itself from the persisted status.
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  // Stopped after choosing preferences: the consent step is next.
  signInAt('preferences_complete');
  backend = mockBackend({
    status: 'preferences_complete',
    setupMode: 'self',
  });
});

afterEach(() => {
  backend.restore();
});

it('reopens on the consent step, with both acknowledgements still outstanding', async () => {
  const router = renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText('Your privacy')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(router.getPathname()).toBe('/consent');
  expect(screen.getByText('Step 4 of 5')).toBeTruthy();

  // Two separate controls, never merged into one (PRD 1, section 27).
  const terms = screen.getByRole('checkbox', {
    name: 'I agree to the Terms of Service',
  });
  const privacy = screen.getByRole('checkbox', {
    name: 'I acknowledge the Privacy Policy',
  });
  expect(terms.props.accessibilityState?.checked).toBe(false);
  expect(privacy.props.accessibilityState?.checked).toBe(false);

  // Placeholder legal documents are labelled as such (PRD 1, section 26).
  expect(screen.getByText('Placeholder documents')).toBeTruthy();

  // The user was not dropped into the main app, nor sent back to the start.
  expect(screen.queryByRole('button', { name: /^Today, tab/ })).toBeNull();
  expect(screen.queryByText('Welcome to Nura')).toBeNull();
});
