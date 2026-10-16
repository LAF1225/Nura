/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The safety client's parsing decisions (PRD 10, sections 42, 48, 64 and 77).
 *
 * Four of them carry a rule rather than only a shape.
 *
 * **An unrecognised capability state falls back to `unavailable`, never
 * `available`.** Guessing in the generous direction is exactly how a screen
 * ends up offering a call that cannot happen (section 64).
 *
 * **`false_positive` keeps three states.** `true`, `false` and "nobody was
 * asked" are different facts, and collapsing the third into `false` would
 * turn silence into a claim (section 48).
 *
 * **An attempt's rendered line survives untouched** (section 42). The client
 * never rebuilds it, because a second renderer is a second place a claim
 * could be written.
 *
 * **An SOS always carries a client id and always says `manual_sos`**
 * (sections 12 and 77). The caller cannot choose an event type, so a button
 * on a phone cannot post a sensor event.
 */
import {
  fetchCapabilities,
  fetchSafetyStatus,
  raiseSos,
  startMonitoring,
} from '../src/features/safety/api';
import {
  capabilityRowsFixture,
  mockBackend,
  safetyEventFixture,
  safetyStatusFixture,
  signInAt,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing', todayDevice: null });
});

afterEach(() => {
  backend.restore();
});

it('reads the capability map as section 106 writes it', async () => {
  const capabilities = await fetchCapabilities('profile-1');
  const states = Object.fromEntries(
    capabilities.capabilities.map((row) => [row.key, row.state])
  );
  expect(states).toEqual({
    manual_sos: 'available',
    in_app_safety_checks: 'available',
    caregiver_in_app_alerts: 'available',
    push_delivery: 'not_configured',
    sms_delivery: 'not_configured',
    audio_calling: 'not_configured',
    robot_detection: 'not_connected',
  });
  expect(capabilities.externalDeliveryAvailable).toBe(false);
  expect(capabilities.warning).toMatch(/cannot reach anybody for you/i);
});

it('treats an unrecognised capability state as unavailable, not available', async () => {
  backend.state.safetyStatus = safetyStatusFixture({
    capabilities: [
      {
        key: 'audio_calling',
        state: 'probably_fine',
        label: 'Audio calling',
        state_label: '',
      },
    ],
  });
  const capabilities = await fetchCapabilities('profile-1');
  expect(capabilities.capabilities[0]?.state).toBe('unavailable');
});

it('drops a capability key it does not know rather than rendering a mystery row', async () => {
  backend.state.safetyStatus = safetyStatusFixture({
    capabilities: [
      ...capabilityRowsFixture(),
      {
        key: 'telepathy',
        state: 'available',
        label: 'Telepathy',
        state_label: 'Available',
      },
    ],
  });
  const capabilities = await fetchCapabilities('profile-1');
  expect(capabilities.capabilities.map((row) => row.key)).not.toContain('telepathy');
  expect(capabilities.capabilities).toHaveLength(7);
});

it('keeps false_positive as three states, so silence is not a claim', async () => {
  backend.state.safetyStatus = safetyStatusFixture({
    active_event: safetyEventFixture({ false_positive: null }),
  });
  expect((await fetchSafetyStatus('profile-1')).activeEvent?.falsePositive).toBeNull();

  backend.state.safetyStatus = safetyStatusFixture({
    active_event: safetyEventFixture({ false_positive: false }),
  });
  expect((await fetchSafetyStatus('profile-1')).activeEvent?.falsePositive).toBe(false);

  backend.state.safetyStatus = safetyStatusFixture({
    active_event: safetyEventFixture({ false_positive: true }),
  });
  expect((await fetchSafetyStatus('profile-1')).activeEvent?.falsePositive).toBe(true);
});

it('keeps the escalation line exactly as the server rendered it', async () => {
  const event = await raiseSos('profile-1', 'sos-1');
  expect(event.attempts.map((attempt) => attempt.line)).toEqual([
    'In-app alert created for Ayesha.',
    'Phone call for Spouse: not set up in this build.',
  ]);
  // And the status that makes the second line true, kept rather than smoothed.
  expect(event.attempts[1]?.status).toBe('not_configured');
  expect(event.attempts[1]?.failureCode).toBe('calling_not_configured');
});

it('never lets a caller choose an event type, and always sends a client id', async () => {
  await raiseSos('profile-1', 'sos-42');
  const sent = backend.requests.find((request) => request.path.endsWith('/sos'))
    ?.body as Record<string, unknown>;
  expect(sent).toEqual({ event_type: 'manual_sos', client_event_id: 'sos-42' });
});

it('sends a duration mode and never an end instant', async () => {
  await startMonitoring('profile-1', {
    durationMode: '30_minutes',
    timezone: 'Europe/London',
    responseTimeoutSeconds: 30,
    secondPromptEnabled: true,
  });
  const sent = backend.requests.find((request) =>
    request.path.includes('/monitoring/start')
  )?.body as Record<string, unknown>;
  expect(sent).toEqual({
    duration_mode: '30_minutes',
    timezone: 'Europe/London',
    response_timeout_seconds: 30,
    second_prompt_enabled: true,
  });
  // Section 61: the server decides when it ends, so there is no field for it.
  expect(Object.keys(sent)).not.toContain('ends_at');
});

it('keeps a missing session as null rather than inventing one', async () => {
  const status = await fetchSafetyStatus('profile-1');
  expect(status.monitoring).toBeNull();
  expect(status.activeEvent).toBeNull();
  expect(status.emergencyMode).toBe(false);
});
