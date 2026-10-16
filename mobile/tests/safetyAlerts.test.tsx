/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * A caregiver's safety alerts (PRD 10, sections 31, 37, 38, 50, 83, 84, 85,
 * 125 and 113).
 *
 * Four things are under test, and the second is the one section 50 is about.
 *
 * **An alert says what was observed and asks the caregiver to check** --
 * section 37's sentence, rendered by the server.
 *
 * **It carries no health data.** The person has a medication and a symptom
 * recorded, and neither word is anywhere on the page. Checked by absence, the
 * way PRD 9's caregiver-mode test checks section 18.
 *
 * **The permission decides whether any of this exists** (section 31). Without
 * `safety_alerts` the caregiver home has no safety section at all -- absent,
 * not empty, so the response cannot be read to learn whether anything has
 * ever happened.
 *
 * **Acknowledging records and nothing more** (sections 84 and 125). The
 * control says what it does not do, and the event is untouched.
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

import {
  caregiverHomeFixture,
  mockBackend,
  safetyAlertFixture,
  signInAt,
  supportedProfileFixture,
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
    supportedProfiles: [supportedProfileFixture({ granted: ['safety_alerts'] })],
    caregiverHome: caregiverHomeFixture({
      granted: ['safety_alerts'],
      safety: {
        unread_count: 1,
        latest_alert_id: 'alert-1',
        latest_event_label: 'Emergency request',
        latest_at: '2026-10-02T18:42:00Z',
        latest_acknowledged: false,
      },
    }),
    safetyAlerts: [safetyAlertFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('shows the alert, carries no health data, and acknowledging resolves nothing', async () => {
  renderRouter('app', { initialUrl: '/care-mode/profiles' });

  await waitFor(() => {
    expect(screen.getByText('Mum')).toBeVisible();
  });
  const [row] = screen.getAllByRole('radio', { name: 'View their care' });
  fireEvent.press(row as Parameters<typeof fireEvent.press>[0]);

  // The home's safety section: a count and the latest one (section 50).
  await waitFor(() => {
    expect(screen.getByText('1 new safety alert.')).toBeVisible();
  });
  expect(screen.getByText('Safety alerts')).toBeVisible();

  act(() => {
    router.push('/care-mode/safety-alerts');
  });

  // Section 37's sentence, from the server.
  await waitFor(() => {
    expect(
      screen.getByText(
        'Nura recorded emergency request at 2 Oct, 6:42 PM. Please check on them.'
      )
    ).toBeVisible();
  });
  // Section 38: a record, said to be a record.
  expect(
    screen.getByText(/An alert is a record, not proof anybody was reached/i)
  ).toBeVisible();

  // Section 85, by absence. The person's medication and symptom are in the
  // fixtures the stub serves elsewhere; neither word reaches this screen.
  expect(screen.queryByText(/Metformin/i)).toBeNull();
  expect(screen.queryByText(/Headache/i)).toBeNull();
  expect(screen.queryByText(/Symptoms/)).toBeNull();

  // Sections 84 and 125: the control says what it records and what it does not.
  expect(
    screen.getByText('This records that you are checking. It does not resolve the event.')
  ).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'I’m checking on them' }));

  await waitFor(() => {
    expect(
      backend.requests.filter((request) => request.path.includes('/acknowledge'))
    ).toHaveLength(1);
  });
  await waitFor(() => {
    expect(screen.getByText('You said you were checking on them.')).toBeVisible();
  });
  // Section 125: the event is not resolved by this, and nothing claims it is.
  expect(screen.queryByText(/resolved/i)).toBeNull();
});

it('has no safety section at all when the permission was not granted', async () => {
  // Driven through the client rather than a second `renderRouter`. What is
  // being checked is that the key is *absent* -- section 18's rule, applied
  // to PRD 10's data -- so the parser's answer is the assertion.
  backend.restore();
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    caregiverHome: caregiverHomeFixture({ granted: ['medications'] }),
  });
  const { fetchCaregiverHome } = require('../src/features/caregivers/api');
  const home = await fetchCaregiverHome('profile-2', '2026-10-02');
  expect(home.safety).toBeNull();
  // And `granted_without_data` no longer mentions safety: PRD 10 built the
  // source PRD 9 section 94 said not to fabricate.
  expect(home.grantedWithoutData).not.toContain('safety_alerts');
});
