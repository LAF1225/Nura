/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Deleting your data, on screen (PRD 13, sections 21, 22, 44 and 50).
 *
 * **What this can and cannot check, stated up front.** Section 21 forbids a
 * one-tap destructive action, and the first screen is the evidence: it offers
 * Continue and Keep my data, and no delete button exists on it. That is
 * assertable here.
 *
 * What is not assertable through this screen is the phrase box. Under React 19
 * with React Native Testing Library 14 a component's own `useState` does not
 * flush from `fireEvent` -- PRD 12 established that and PRD 13's own
 * `app/privacy/delete.tsx` is built around it -- so typing into the field and
 * watching the button enable cannot be driven. The rule itself lives in
 * `features/privacy/validation.ts` as a pure function and is tested directly
 * in `privacyValidation.test.ts`, which is the stronger test anyway: it checks
 * the comparison is exact rather than that one keystroke produced one state.
 *
 * One `renderRouter` per file, as every screen test here has.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
});

afterEach(() => {
  backend?.restore();
});

it('opens on what would go, with no way to delete in one tap', async () => {
  backend = mockBackend({ status: 'onboarding_complete' });

  renderRouter('app', { initialUrl: '/privacy/delete' });

  await waitFor(() => {
    expect(screen.getByText('Continue')).toBeTruthy();
  });

  // Section 21: the first screen explains and offers a way out. There is no
  // delete control on it at all -- not a disabled one, not one behind a
  // confirmation sheet.
  expect(screen.getByText(/shows exactly what that is/)).toBeTruthy();
  expect(screen.getByText('Keep my data')).toBeTruthy();
  expect(screen.queryByText('Delete everything')).toBeNull();

  // And nothing on it claims anything has happened yet.
  for (const forbidden of [/\bDeleted\b/, /\bRemoved\b/]) {
    expect(screen.queryByText(forbidden)).toBeNull();
  }
});
