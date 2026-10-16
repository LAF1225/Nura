/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The Today appointments card with nothing upcoming (PRD 7, section 9).
 *
 * The state that separates this card from the medication and symptom ones: those
 * draw *nothing at all* for somebody who has not used the feature, and this one
 * draws the empty state PRD 7 section 9 writes out -- "No upcoming appointments"
 * and a way to add one.
 *
 * That difference is deliberate and is what this file exists to pin down, so a
 * later change cannot quietly make the card disappear for everybody who has not
 * been to a doctor.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

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
    appointments: [],
  });
});

afterEach(() => {
  backend.restore();
});

it('still draws the card, says the list is empty, and offers the first one', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(() => {
    expect(screen.getByText('Appointments')).toBeVisible();
  });

  expect(screen.getByText('No upcoming appointments.')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Add appointment' })).toBeVisible();

  // Nothing is invented to fill the space.
  expect(screen.queryByText('Next appointment')).toBeNull();
  expect(screen.queryByText('Prepare for appointment')).toBeNull();

  fireEvent.press(screen.getByRole('button', { name: 'Add appointment' }));
  await waitFor(() => {
    expect(screen.getByText('What is the appointment?')).toBeVisible();
  });
});
