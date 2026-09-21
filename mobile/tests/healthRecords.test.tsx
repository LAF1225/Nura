/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * A section of the health record, and removing something from it
 * (PRD 4, sections 20, 37, 46 and 51).
 *
 * The delete confirmation is the part worth pinning down: PRD 4 section 46
 * says nothing may be removed silently. It goes through a native alert, so the
 * test can check exactly what the user would be asked -- including that
 * nothing is deleted when they do not confirm.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;
let alertSpy: jest.SpyInstance;

const MEDICATION = {
  id: 'm1',
  profile_id: 'profile-1',
  name: 'Salbutamol',
  dose: '100',
  dose_unit: 'mcg',
  form: 'inhaler',
  frequency_text: 'two puffs when needed',
  is_active: true,
  source: 'user',
  created_at: '2026-09-21T08:00:00Z',
  updated_at: '2026-09-21T08:00:00Z',
};

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    healthRecords: { medications: [MEDICATION] },
  });
  alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
});

afterEach(() => {
  backend.restore();
  alertSpy.mockRestore();
});

it('lists a section, and asks before removing anything from it', async () => {
  renderRouter('app', { initialUrl: '/health/medications/m1' });

  // The form opens on the record, with its stored values in place.
  await waitFor(
    () => {
      expect(screen.getByDisplayValue('Salbutamol')).toBeTruthy();
    },
    { timeout: 30_000 }
  );
  expect(screen.getByDisplayValue('two puffs when needed')).toBeTruthy();

  // PRD 4, section 55: the screen says what it is, and what it is not.
  expect(screen.getByText(/Nura does not check or interpret it/)).toBeTruthy();

  const { fireEvent } = require('@testing-library/react-native');
  fireEvent.press(screen.getByRole('button', { name: 'Remove medication' }));

  expect(alertSpy).toHaveBeenCalledTimes(1);
  const [title, message, buttons] = alertSpy.mock.calls[0] as [
    string,
    string,
    { text: string; style?: string }[],
  ];

  expect(title).toBe('Remove this medication?');
  expect(message).toContain('Salbutamol');
  expect(message).toContain('health profile');
  expect(buttons.map((button) => button.text)).toEqual(['Cancel', 'Remove']);
  expect(buttons[1]?.style).toBe('destructive');

  // Nothing has been deleted merely by asking.
  expect(backend.requests.some((request) => request.method === 'DELETE')).toBe(false);
});
