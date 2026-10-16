/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The appointments list with nothing in it (PRD 7, section 9).
 *
 * The state most accounts are in, and the one PRD 7 section 9 gives its own
 * wording to: not an error, not an empty table, but a sentence and a way to add
 * the first one.
 *
 * The queued-appointment case is in `appointmentsSync.test.tsx`, because opening
 * this screen *sends* anything queued -- so the two cannot be observed together.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useAppointmentListStore } from '../src/features/appointments/listStore';
import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useAppointmentListStore.setState({ scope: 'upcoming' });
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [],
  });
});

afterEach(() => {
  backend.restore();
});

it('says the list is empty and offers the first appointment', async () => {
  renderRouter('app', { initialUrl: '/appointments' });

  await waitFor(() => {
    expect(screen.getByText('No upcoming appointments.')).toBeVisible();
  });

  // Always a way to add one, whatever the list says (PRD 7, section 9).
  expect(screen.getByRole('button', { name: 'Add appointment' })).toBeVisible();

  // Nothing is invented to fill the space.
  expect(screen.queryByText('Prepare for appointment')).toBeNull();
});
