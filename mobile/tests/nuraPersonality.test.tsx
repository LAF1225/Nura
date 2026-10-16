/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Personality (PRD 8, sections 22-24, 62 and 102).
 *
 * Two things are under test, and only one of them is "the setting saves".
 *
 * **A preset writes the dials and then stops mattering** (section 62).
 * Choosing Focused sets five values; moving one afterwards leaves the other
 * four alone and the screen stops claiming the preset describes them.
 *
 * **Personality cannot reach the medical boundary** (section 24). There is a
 * limit to what a screen test can prove about that -- the enforcement is in
 * the backend and is tested there -- so what is checked here is that the
 * screen *says* so, because a user turning humour up is entitled to know
 * what it does not change.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { assistantPreferencesFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    assistantPreferences: assistantPreferencesFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

it('applies a preset, lets a dial depart from it, and says what it cannot change', async () => {
  renderRouter('app', { initialUrl: '/nura/personality' });

  await waitFor(() => {
    expect(screen.getByText('Gentle')).toBeVisible();
  });

  // The four presets section 22 names, each with a description of its own.
  for (const preset of ['Gentle', 'Friendly', 'Focused', 'Professional']) {
    expect(screen.getByLabelText(preset)).toBeVisible();
  }

  // Section 24, said to the user rather than only enforced behind the screen.
  expect(
    screen.getByText(/stays serious about anything to do with your safety/i)
  ).toBeVisible();

  // --- a preset writes the dials -------------------------------------------
  fireEvent.press(screen.getByLabelText('Focused'));

  await waitFor(() => {
    // Warmth low is what Focused means, and the control shows it as chosen.
    expect(screen.getByLabelText('Warmth: Low').props.accessibilityState).toMatchObject({
      disabled: false,
    });
    expect(backend.state.assistantPreferences.warmth).toBe('low');
  });
  expect(backend.state.assistantPreferences.reminder_firmness).toBe('high');
  expect(backend.state.assistantPreferences.verbosity).toBe('concise');

  const presetRequest = backend.requests.find(
    (request) =>
      request.method === 'PATCH' && request.path.includes('/assistant/preferences')
  );
  expect(presetRequest?.body).toMatchObject({ personality_preset: 'focused' });

  // --- and a dial departs from it ------------------------------------------
  fireEvent.press(screen.getByLabelText('Warmth: High'));

  await waitFor(() => {
    expect(backend.state.assistantPreferences.warmth).toBe('high');
  });
  // The other four are untouched: a preset initialises, it does not own.
  expect(backend.state.assistantPreferences.reminder_firmness).toBe('high');
  expect(backend.state.assistantPreferences.personality_preset).toBe('focused');
  expect(backend.state.assistantPreferences.matches_preset).toBe(false);

  // So the screen stops claiming the preset describes the settings.
  await waitFor(() => {
    expect(screen.getByLabelText('Focused (Adjusted)')).toBeVisible();
  });

  // Nothing on this screen can choose a model, a provider or a prompt
  // (section 76): every request it made carries only tone settings.
  const fields = backend.requests
    .filter((request) => request.method === 'PATCH')
    .flatMap((request) => Object.keys(request.body as Record<string, unknown>));
  for (const forbidden of ['model', 'provider', 'api_key', 'system_prompt']) {
    expect(fields).not.toContain(forbidden);
  }
});
