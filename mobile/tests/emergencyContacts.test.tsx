/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The emergency-contact chain (PRD 9, sections 43-47, 89 and 96).
 *
 * Three things are under test.
 *
 * **Reordering works, with explicit controls.** Section 89 says to prefer
 * move-up/move-down over drag-and-drop when drag is unstable or inaccessible, and
 * the order sent is the list as displayed -- the server renumbers from it.
 *
 * **The ends have no control that does nothing.** The first contact has no Move
 * up and the last no Move down: a button that announces itself to a screen reader
 * and then does nothing is worse than one that is not there.
 *
 * **The screen says Nura contacts nobody** (section 47). This is the assertion
 * that matters most on this screen: somebody entering three phone numbers has
 * every reason to assume otherwise, and PRD 9 builds the chain while PRD 10 walks
 * it.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { emergencyContactFixture, mockBackend, signInAt } from './helpers';

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
    emergencyContacts: [
      emergencyContactFixture({ id: 'contact-1', name: 'Bilal', priority: 1 }),
      emergencyContactFixture({
        id: 'contact-2',
        name: 'Ayesha',
        relationship_label: 'Daughter',
        priority: 2,
      }),
      emergencyContactFixture({
        id: 'contact-3',
        name: 'Hana',
        relationship_label: 'Neighbour',
        priority: 3,
      }),
    ],
  });
});

afterEach(() => {
  backend.restore();
});

it('reorders the chain, hides the controls that would do nothing, and says Nura calls nobody', async () => {
  renderRouter('app', { initialUrl: '/emergency-contacts' });

  await waitFor(() => {
    expect(screen.getByText('Bilal')).toBeVisible();
  });

  // PRD 9 section 47 and PRD 10 sections 30 and 74, where the phone numbers
  // are. PRD 10 walks this chain, so the sentence says it does -- and says in
  // the same breath that it cannot call or text anybody in this build.
  expect(screen.getByText(/uses this order if you ask for help/i)).toBeVisible();
  expect(screen.getByText(/cannot call or text anyone in this build/i)).toBeVisible();

  // The order, announced rather than only implied by position.
  expect(screen.getByText('Number 1 in the list')).toBeVisible();
  expect(screen.getByText('Number 3 in the list')).toBeVisible();

  // Three contacts: two Move up (not the first) and two Move down (not the last).
  expect(screen.getAllByLabelText('Move up')).toHaveLength(2);
  expect(screen.getAllByLabelText('Move down')).toHaveLength(2);

  // Move the last one to second. The first Move up belongs to Ayesha, the second
  // to Hana, since Bilal has none.
  const moveUps = screen.getAllByLabelText('Move up');
  fireEvent.press(moveUps[1] as Parameters<typeof fireEvent.press>[0]);

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/reorder'))
    ).toHaveLength(1);
  });

  const reorder = backend.requests.find((request) => request.path.includes('/reorder'));
  // The ids in the order the list is about to show them. Not priorities the
  // client had to keep consistent (section 45).
  expect((reorder?.body as Record<string, unknown>).order).toEqual([
    'contact-1',
    'contact-3',
    'contact-2',
  ]);

  // The server renumbered, and the screen shows its answer rather than jumping
  // back to the old order for a frame.
  await waitFor(() => {
    expect(screen.getAllByText(/Number \d in the list/)).toHaveLength(3);
  });
  const names = screen
    .getAllByText(/^(Bilal|Ayesha|Hana)$/)
    .map((node) => node.props.children as string);
  expect(names).toEqual(['Bilal', 'Hana', 'Ayesha']);
});
