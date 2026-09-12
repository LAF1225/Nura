/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Welcome and sign-in screens (PRD 1, sections 7, 8 and 54).
 *
 * Signed out, with a configured provider, so the auth options render as they
 * would in a real build.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { signOut } from './helpers';

// Configured, but with no active session: a first launch.
jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock(null)
);

// `config` reads EXPO_PUBLIC_* at import time, which the test environment does
// not set. Report a configured project so the provider buttons are enabled.
jest.mock('../src/constants/config', () => {
  const actual = jest.requireActual('../src/constants/config');
  return {
    ...actual,
    config: {
      ...actual.config,
      supabaseUrl: 'https://test.supabase.co',
      supabaseAnonKey: 'test-anon-key',
      isSupabaseConfigured: true,
      googleClientId: 'test-google-client-id',
    },
  };
});

jest.setTimeout(60_000);

beforeEach(() => {
  signOut();
});

it('starts a signed-out user at Welcome and offers every configured provider', async () => {
  renderRouter('app', { initialUrl: '/' });

  // The gate should send an unauthenticated user here, not into the tabs.
  await waitFor(
    () => {
      expect(screen.getByText('Welcome to Nura')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  expect(screen.getByText('Your health and daily-life companion.')).toBeTruthy();
  // No unvalidated medical claims (PRD 1, section 7).
  expect(
    screen.queryByText(/prevents emergencies|detects seizures|keeps you safe/i)
  ).toBeNull();
  // And the main tabs are not visible during onboarding (PRD 1, section 43).
  expect(screen.queryByRole('button', { name: /^Health, tab/ })).toBeNull();

  fireEvent.press(screen.getByRole('button', { name: 'Get started' }));

  await waitFor(() => {
    expect(screen.getByText('Sign in to Nura')).toBeTruthy();
  });

  // Fallback methods are always offered; Google appears because a client id is
  // configured. Apple is iOS-only, so it is not asserted here.
  expect(screen.getByRole('button', { name: 'Continue with email' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Continue with phone' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Continue with Google' })).toBeTruthy();

  // A configured build must not show the development-state warning.
  expect(screen.queryByText(/not configured in this build/i)).toBeNull();
});
