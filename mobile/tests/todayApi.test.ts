/**
 * Mapping `/api/v1/today` onto what the screen renders (PRD 3, section 64).
 *
 * The three device states PRD 3 section 6 requires -- no robot, linked and
 * offline, linked and online -- are all decided here, from the backend's own
 * answer. The app never derives a connection status of its own.
 */
import {
  parseDashboardPreferences,
  parseTodaySummary,
  submitDailyCheckIn,
} from '../src/services/api/today';

const BASE = {
  local_date: '2026-09-21',
  profile: { id: 'profile-1', preferred_name: 'Safdar' },
  daily_checkin: {
    status: 'not_completed',
    checkin: null,
    recent_completed_count: 0,
    recent_window_days: 7,
  },
  device: null,
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

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('parseTodaySummary', () => {
  it('maps the wire body onto the screen model', () => {
    const summary = parseTodaySummary(BASE);
    expect(summary.localDate).toBe('2026-09-21');
    expect(summary.profile).toEqual({ id: 'profile-1', preferredName: 'Safdar' });
    expect(summary.dailyCheckIn.status).toBe('not_completed');
    expect(summary.important).toEqual([]);
  });

  it('reports no device as null rather than as an error (state A)', () => {
    expect(parseTodaySummary({ ...BASE, device: null }).device).toBeNull();
  });

  it('maps an offline device, with when it was last seen (state B)', () => {
    const summary = parseTodaySummary({
      ...BASE,
      device: {
        device_id: 'device-1',
        display_name: 'Nura',
        connection_status: 'offline',
        last_seen_at: '2026-09-21T11:18:00Z',
        setup_completed: true,
      },
    });
    expect(summary.device).toEqual({
      deviceId: 'device-1',
      displayName: 'Nura',
      connectionStatus: 'offline',
      lastSeenAt: '2026-09-21T11:18:00Z',
      setupCompleted: true,
    });
  });

  it('maps an online device (state C)', () => {
    const summary = parseTodaySummary({
      ...BASE,
      device: {
        device_id: 'device-1',
        display_name: 'Bedroom Nura',
        connection_status: 'online',
        last_seen_at: '2026-09-21T12:00:00Z',
        setup_completed: true,
      },
    });
    expect(summary.device?.connectionStatus).toBe('online');
    expect(summary.device?.displayName).toBe('Bedroom Nura');
  });

  it('never reads an unrecognised status as online', () => {
    const summary = parseTodaySummary({
      ...BASE,
      device: {
        device_id: 'device-1',
        display_name: 'Nura',
        connection_status: 'probably_fine',
        last_seen_at: null,
        setup_completed: false,
      },
    });
    expect(summary.device?.connectionStatus).toBe('unknown');
  });

  it('maps a completed check-in', () => {
    const summary = parseTodaySummary({
      ...BASE,
      daily_checkin: {
        status: 'completed',
        checkin: {
          id: 'checkin-1',
          profile_id: 'profile-1',
          checkin_date: '2026-09-21',
          wellbeing_level: 'not_great',
          note: 'Feeling tired today.',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:05:00Z',
        },
        recent_completed_count: 4,
        recent_window_days: 7,
      },
    });
    expect(summary.dailyCheckIn.status).toBe('completed');
    expect(summary.dailyCheckIn.checkIn).toMatchObject({
      date: '2026-09-21',
      wellbeingLevel: 'not_great',
      note: 'Feeling tired today.',
      syncStatus: 'synced',
    });
    expect(summary.dailyCheckIn.recentCompletedCount).toBe(4);
  });

  it('drops a card this build has no renderer for', () => {
    // A backend that has shipped a new card should not break an older app.
    const summary = parseTodaySummary({
      ...BASE,
      cards: [
        ...BASE.cards,
        {
          key: 'astrology',
          title: 'Astrology',
          available: true,
          visible: true,
          position: 2,
        },
      ],
    });
    expect(summary.cards.map((card) => card.key)).toEqual([
      'daily_checkin',
      'device_status',
    ]);
  });

  it('returns cards in position order whatever order they arrive in', () => {
    const summary = parseTodaySummary({
      ...BASE,
      cards: [
        {
          key: 'device_status',
          title: 'Nura status',
          available: true,
          visible: true,
          position: 1,
        },
        {
          key: 'daily_checkin',
          title: 'Daily check-in',
          available: true,
          visible: true,
          position: 0,
        },
      ],
    });
    expect(summary.cards.map((card) => card.key)).toEqual([
      'daily_checkin',
      'device_status',
    ]);
  });

  it('survives an account with no profile yet', () => {
    const summary = parseTodaySummary({ ...BASE, profile: null });
    expect(summary.profile).toBeNull();
  });
});

describe('parseDashboardPreferences', () => {
  it('keeps unavailable cards out of the app entirely', () => {
    const preferences = parseDashboardPreferences({
      profile_id: 'profile-1',
      cards: [
        ...BASE.cards,
        {
          key: 'medications',
          title: 'Medications',
          available: false,
          visible: false,
          position: 2,
        },
      ],
    });
    // Parsed -- the filtering to renderable cards happens in `cards.ts`, but
    // the flag has to survive the trip.
    expect(preferences.cards.find((card) => card.key === 'medications')?.available).toBe(
      false
    );
  });
});

describe('submitDailyCheckIn', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('sends the local date, the level and the note', async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return jsonResponse({
        checkin: {
          id: 'checkin-1',
          profile_id: 'profile-1',
          checkin_date: '2026-09-21',
          wellbeing_level: 'good',
          note: 'Slept well',
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T08:00:00Z',
        },
        applied: true,
      });
    }) as unknown as typeof fetch;

    const saved = await submitDailyCheckIn({
      localDate: '2026-09-21',
      wellbeingLevel: 'good',
      note: 'Slept well',
      clientUpdatedAt: '2026-09-21T08:00:00.000Z',
    });

    expect(saved.applied).toBe(true);
    expect(saved.checkIn.wellbeingLevel).toBe('good');

    const call = calls[0]!;
    expect(call.url).toContain('/api/v1/daily-checkins/today');
    // PUT, not POST: one check-in per day, so a retry must not create a second.
    expect(call.init.method).toBe('PUT');
    expect(JSON.parse(String(call.init.body))).toEqual({
      local_date: '2026-09-21',
      wellbeing_level: 'good',
      note: 'Slept well',
      client_updated_at: '2026-09-21T08:00:00.000Z',
    });
  });

  it('reports when the server kept a newer answer of its own', async () => {
    globalThis.fetch = (async () =>
      jsonResponse({
        checkin: {
          id: 'checkin-1',
          profile_id: 'profile-1',
          checkin_date: '2026-09-21',
          wellbeing_level: 'not_great',
          note: null,
          created_at: '2026-09-21T08:00:00Z',
          updated_at: '2026-09-21T10:00:00Z',
        },
        applied: false,
      })) as unknown as typeof fetch;

    const saved = await submitDailyCheckIn({
      localDate: '2026-09-21',
      wellbeingLevel: 'good',
    });
    expect(saved.applied).toBe(false);
    // The client is handed the stored answer so it can converge on it.
    expect(saved.checkIn.wellbeingLevel).toBe('not_great');
  });
});
