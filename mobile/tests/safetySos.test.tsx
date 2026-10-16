/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Asking for help, and what the app says happened (PRD 10, sections 12, 13,
 * 21, 26, 42, 43, 45, 68, 72 and 113).
 *
 * Five things are under test, and the third is the one this whole PRD turns
 * on.
 *
 * **An accidental press cannot raise an emergency** (section 13). One tap
 * shows what will happen; a second one sends it.
 *
 * **The confirm step says what will *not* happen.** Somebody deciding
 * whether to press this needs to know nobody will be called, so section 42's
 * honesty applies before the emergency as well as during it.
 *
 * **The escalation list shows the lines that say a channel is not set up.**
 * A screen that showed only the successful halves would be section 42's
 * "Ayesha has been contacted" assembled out of omissions. Both lines are
 * asserted, and the forbidden wording is asserted absent.
 *
 * **Emergency mode minimises the screen** (section 43). The SOS card and the
 * history link go away while something is live.
 *
 * **Cancelling asks first, and says what it does not undo** (section 45).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import {
  emergencyContactFixture,
  mockBackend,
  safetyStatusFixture,
  signInAt,
} from './helpers';

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
    safetyStatus: safetyStatusFixture({ emergency_contact_count: 1 }),
    emergencyContacts: [emergencyContactFixture({ name: 'Ayesha' })],
  });
});

afterEach(() => {
  backend.restore();
});

it('asks before sending, reports only what happened, and cancels on confirmation', async () => {
  renderRouter('app', { initialUrl: '/safety' });

  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Ask for help' })).toBeVisible();
  });

  // Section 74's warning, which is a deployment fact rather than a sentence
  // somebody remembered to add.
  expect(
    screen.getByText(/External notifications and calling are not set up in this build/i)
  ).toBeVisible();

  // Section 13: one press is not enough.
  fireEvent.press(screen.getByRole('button', { name: 'Ask for help' }));

  await waitFor(() => {
    expect(screen.getByText('Ask for help now?')).toBeVisible();
  });
  expect(backend.requests.filter((request) => request.path.endsWith('/sos'))).toEqual([]);

  // And the confirm step says what will not happen (section 42).
  expect(screen.getByText(/It cannot call or text anyone\./)).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Yes, ask for help' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.endsWith('/sos'))
    ).toHaveLength(1);
  });
  // Section 77: a client id, so a retry is the same emergency.
  const sent = backend.requests.find((request) => request.path.endsWith('/sos'))
    ?.body as Record<string, unknown>;
  expect(typeof sent.client_event_id).toBe('string');
  expect(sent.event_type).toBe('manual_sos');

  // Section 42: both halves of the truth.
  await waitFor(() => {
    expect(screen.getByText('In-app alert created for Ayesha.')).toBeVisible();
  });
  expect(
    screen.getByText('Phone call for Spouse: not set up in this build.')
  ).toBeVisible();
  expect(screen.getByText('An in-app alert was created for 1 caregiver.')).toBeVisible();
  expect(screen.queryByText(/has been contacted/i)).toBeNull();
  expect(screen.queryByText(/notified/i)).toBeNull();

  // Section 68: the dialler is offered, and labelled as the phone's.
  expect(screen.getByText(/Nura does not place the call/i)).toBeVisible();

  // Section 43: the SOS card and the history link are gone while this is live.
  expect(screen.queryByRole('button', { name: 'Ask for help' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Safety history' })).toBeNull();

  // Section 45: cancelling asks, and says what it does not undo.
  fireEvent.press(screen.getByRole('button', { name: 'Cancel this request' }));

  await waitFor(() => {
    expect(screen.getByText('Cancel emergency request?')).toBeVisible();
  });
  expect(
    screen.getByText(/Alerts that already exist stay where they are\./)
  ).toBeVisible();
  expect(backend.requests.filter((request) => request.path.includes('/cancel'))).toEqual(
    []
  );

  fireEvent.press(screen.getByRole('button', { name: 'Cancel request' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/cancel'))
    ).toHaveLength(1);
  });
});
