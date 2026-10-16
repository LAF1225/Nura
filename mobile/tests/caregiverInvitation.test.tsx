/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Reviewing and accepting an invitation (PRD 9, sections 13, 14, 15, 81 and 96).
 *
 * Its own file because one `renderRouter` per file is the harness limit.
 *
 * What is under test is section 15's screen: both lists, named for what they
 * actually are rather than "access health information", and the sentence saying a
 * caregiver does not need a health profile of their own (section 14).
 *
 * The single-use rule is checked too: the stub spends the token on accept, the
 * way the real endpoint does, so a second attempt finds nothing (section 13).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { invitationPreviewFixture, mockBackend, signInAt } from './helpers';

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
    invitationPreview: invitationPreviewFixture(),
  });
});

afterEach(() => {
  backend.restore();
});

it('shows both lists before accepting an invitation', async () => {
  renderRouter('app', { initialUrl: '/caregivers/accept?token=nci_test-token' });

  await waitFor(() => {
    expect(
      screen.getByText('Ayesha, you have been asked to help with Ada’s care.')
    ).toBeVisible();
  });

  // Section 15: both lists, named for what they are. Not "access health
  // information".
  expect(screen.getByText('You will be able to see')).toBeVisible();
  expect(screen.getByText('You will not be able to see')).toBeVisible();
  expect(screen.getByText('Medication reminders')).toBeVisible();
  expect(screen.getByText('Symptoms')).toBeVisible();

  // Section 14: accepting does not require having a profile of your own.
  expect(screen.getByText(/do not need to set up Nura for yourself/i)).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Accept' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/accept'))
    ).toHaveLength(1);
  });
});
