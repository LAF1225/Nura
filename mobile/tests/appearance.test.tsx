/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Appearance screen (PRD 0, sections 22 and 27).
 *
 * Drives the real screen rather than the store directly, so this also covers
 * the radio accessibility semantics the rows are meant to expose.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

import { useAppStore } from '../src/store/appStore';

// Stands in for a configured Supabase project so the auth gate can let us in.
jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  // The auth gate only lets a signed-in, fully onboarded user reach the main
  // tabs; without this every render would redirect to the welcome screen.
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing' });
});

afterEach(() => {
  backend.restore();
});

it('lists the three theme options and applies the chosen one', async () => {
  useAppStore.setState({ themePreference: 'system' });

  renderRouter('app', { initialUrl: '/appearance' });

  await waitFor(
    () => {
      expect(screen.getByText('System')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // Exposed as radio options, with the current choice marked selected.
  const system = screen.getByRole('radio', { name: 'System' });
  const light = screen.getByRole('radio', { name: 'Light' });
  const dark = screen.getByRole('radio', { name: 'Dark' });

  expect(system.props.accessibilityState?.selected).toBe(true);
  expect(dark.props.accessibilityState?.selected).toBe(false);

  fireEvent.press(dark);
  expect(useAppStore.getState().themePreference).toBe('dark');

  fireEvent.press(light);
  expect(useAppStore.getState().themePreference).toBe('light');
});
