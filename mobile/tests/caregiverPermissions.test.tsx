/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The caregiver list and what each person can see (PRD 9, sections 53, 54, 96).
 *
 * One test, because one `renderRouter` per file is the harness limit (see
 * navigation.test.tsx) -- so this walks the whole thing: the list, the detail
 * screen, a permission change that really goes to the server, a role change that
 * does not, and the confirmation in front of Remove.
 *
 * Four things are under test.
 *
 * **Permission toggles persist**, asserted on the request body rather than on the
 * screen: a form that re-renders optimistically and sends nothing looks identical.
 *
 * **A change sends only what moved.** Section 53's "edit permissions at any time"
 * is only safe if one toggle does not silently deny the other seven.
 *
 * **A role change sends a role and nothing else** (section 54).
 *
 * **Two categories say they do nothing yet** (sections 94 and 27). Granting
 * `safety_alerts` or `routines` is stored faithfully and unlocks nothing, and a
 * toggle that quietly promised otherwise is what section 94 forbids.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import {
  act,
  fireEvent,
  renderRouter,
  screen,
  waitFor,
} from 'expo-router/testing-library';

import { caregiverFixture, careSummaryFixture, mockBackend, signInAt } from './helpers';

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
    caregivers: [
      caregiverFixture({
        granted: {
          medications: true,
          appointments: true,
          safety_alerts: true,
          routines: true,
        },
      }),
    ],
    careSummary: careSummaryFixture({ caregiver_count: 1 }),
  });
});

afterEach(() => {
  backend.restore();
});

function bodyOf(request: { body: unknown } | undefined): Record<string, unknown> {
  return (request?.body ?? {}) as Record<string, unknown>;
}

it('lists a caregiver, saves one permission, relabels without granting, and confirms removal', async () => {
  renderRouter('app', { initialUrl: '/caregivers' });

  await waitFor(() => {
    expect(screen.getByText('Ayesha')).toBeVisible();
  });

  // What they can see is a count on the list, not a list of categories.
  expect(screen.getByText('Can see 4 of 8 areas')).toBeVisible();

  act(() => {
    router.push('/caregivers/relationship-1');
  });

  await waitFor(() => {
    expect(screen.getByText('What they can see')).toBeVisible();
  });

  // Section 15: all eight categories are offered, each named for what it is. A
  // screen that only listed the granted ones could not take one away.
  for (const label of [
    'Medication reminders',
    'Appointments',
    'Symptoms',
    'Health reports',
    'Safety alerts',
    'Family messages',
    'Routines',
    'Health summary',
  ]) {
    expect(screen.getByLabelText(label)).toBeVisible();
  }

  // **No category claims to share nothing any more.** `safety_alerts` stopped
  // in PRD 10, which built the event source PRD 9 section 94 said not to
  // fabricate, and `routines` stopped in PRD 12, which built routines, runs
  // and steps. Either sentence would now be the untrue one.
  expect(screen.queryByText(/does not keep routines yet/i)).toBeNull();
  expect(screen.queryByText(/does not watch for falls/i)).toBeNull();
  expect(screen.queryByText(/does not share anything today/i)).toBeNull();

  // Section 54, where the role selector is.
  expect(
    screen.getByText('Changing this label does not change what they can see.')
  ).toBeVisible();

  // `fireEvent.press` does nothing to a Switch; `valueChange` is what a
  // ToggleRow emits.
  fireEvent(screen.getByLabelText('Symptoms'), 'valueChange', true);

  // Save enables once something has changed, and not before.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Save' }));

  await waitFor(() => {
    expect(
      backend.requests.filter(
        (request) => request.method === 'PATCH' && request.path.includes('/permissions')
      )
    ).toHaveLength(1);
  });

  const save = backend.requests.find(
    (request) => request.method === 'PATCH' && request.path.includes('/permissions')
  );
  // Only the toggle that moved. The other seven are left alone, so a client
  // sending one change cannot deny the rest (section 53).
  expect(bodyOf(save).permissions).toEqual({ symptoms: true });

  // A role change sends a role and nothing else (section 54).
  fireEvent.press(screen.getByLabelText('Primary caregiver'));
  await waitFor(() => {
    const roleChange = backend.requests.find(
      (request) =>
        request.method === 'PATCH' &&
        request.path.includes('/caregivers/relationship-1') &&
        !request.path.includes('/permissions')
    );
    expect(bodyOf(roleChange)).toEqual({ role: 'primary_caregiver' });
  });

  // Section 52's consequences, stated where the button is: access stops now, and
  // the conversation they have already had stays.
  expect(screen.getByText('Remove this person')).toBeVisible();
  expect(
    screen.getByText(/will not be able to see anything of yours from the moment/i)
  ).toBeVisible();

  // The first press confirms rather than removes, so Remove is never one mis-tap
  // away (section 77's large confirmation controls). The confirm step names the
  // person and offers a way out, so the first press is visibly a step.
  fireEvent.press(screen.getByRole('button', { name: 'Remove' }));
  expect(backend.requests.filter((request) => request.method === 'DELETE')).toHaveLength(
    0
  );

  // Waiting for the *control*, not for the store: a press arriving before the
  // re-render would read the old state.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Yes, remove Ayesha' })).toBeVisible();
  });
  expect(screen.getByRole('button', { name: 'Keep them' })).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Yes, remove Ayesha' }));
  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.method === 'DELETE')
    ).toHaveLength(1);
  });
});
