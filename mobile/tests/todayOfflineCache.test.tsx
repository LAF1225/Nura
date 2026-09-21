/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Today when the backend cannot be reached but we have seen it before
 * (PRD 3, sections 26 and 30).
 *
 * The user still gets their day: their check-in and their card layout, marked
 * as saved rather than live. The one thing that is *not* carried over is the
 * robot's connection, because offline we genuinely do not know it — and a
 * cached "Online" would break the rule that presence only ever comes from the
 * backend.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

import { localDateString } from '../src/utils/date';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

/** A body in wire format, as the backend would have returned it today. */
function snapshotForToday() {
  return {
    local_date: localDateString(),
    profile: { id: 'profile-1', preferred_name: 'Ada' },
    daily_checkin: {
      status: 'completed',
      checkin: {
        id: 'checkin-1',
        profile_id: 'profile-1',
        checkin_date: localDateString(),
        wellbeing_level: 'good',
        note: null,
        created_at: '2026-09-21T08:00:00Z',
        updated_at: '2026-09-21T08:00:00Z',
      },
      recent_completed_count: 3,
      recent_window_days: 7,
    },
    device: {
      device_id: 'device-1',
      display_name: 'Bedroom Nura',
      connection_status: 'online',
      last_seen_at: '2026-09-21T11:59:00Z',
      setup_completed: true,
    },
    cards: [
      {
        key: 'daily_checkin',
        title: 'Daily check-in',
        available: true,
        visible: true,
        position: 0,
      },
      {
        key: 'device_status',
        title: 'Nura status',
        available: true,
        visible: true,
        position: 1,
      },
    ],
    important: [],
  };
}

beforeEach(async () => {
  await AsyncStorage.setItem(
    'nura.today.lastSummary',
    JSON.stringify(snapshotForToday())
  );
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing', todayStatus: 503 });
});

afterEach(async () => {
  backend.restore();
  await AsyncStorage.clear();
});

it('shows the saved day, and refuses to claim the robot is online', async () => {
  renderRouter('app', { initialUrl: '/' });

  await waitFor(
    () => {
      expect(screen.getByText(/Showing what Nura last saved on this phone/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // The user's own day survives the outage.
  expect(screen.getByText(/You checked in as “Good” today\./)).toBeTruthy();
  expect(screen.getByText('This week: 3 check-ins completed')).toBeTruthy();
  expect(screen.getByText('Bedroom Nura')).toBeTruthy();

  // But the cached connection status does not. The card says what it can.
  expect(
    screen.getByText(/can’t check the connection while you’re offline/)
  ).toBeTruthy();
  expect(screen.queryByText('Online')).toBeNull();
  expect(screen.queryByText(/is online\./)).toBeNull();

  // And the error card is not shown, because the screen is not empty.
  expect(screen.queryByText(/can’t load today’s information/)).toBeNull();
});
