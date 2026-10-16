/**
 * The shared notification scheduler (PRD 12, sections 9, 11, 34, 62 and 69).
 *
 * Section 69 says what these tests may and may not claim: a recording stub,
 * five behaviours, and **no claim of OS delivery**. Nothing in this project has
 * ever run on a physical phone, so what is testable is that the right calls
 * were made with the right values -- and that is all that is asserted.
 *
 * The one worth reading is "reconciling twice schedules nothing the second
 * time". That is section 34's *retries must not duplicate*, and it is a
 * property of the algorithm rather than of a guard somebody remembered to add.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  cancelAll,
  rebuild,
  reconcile,
  upcoming,
  type Domain,
  type Planned,
  type Scheduled,
} from '../src/features/notifications/scheduler';
import {
  ALARM_DOMAIN,
  REMINDER_DOMAIN,
  planAlarms,
  planReminders,
  rebuildAlarmNotifications,
  rebuildReminderNotifications,
} from '../src/features/productivity/notifications';
import { alarmFixture, occurrenceFixture } from './helpers';
import { parseAlarm, parseOccurrence } from '../src/features/productivity/api';

/**
 * The recording stub.
 *
 * `jest.mock` rather than `jest.spyOn`: `expo-notifications` exports
 * non-configurable properties, so a spy throws "Cannot redefine property".
 * The medication and appointment notification tests use the same shape.
 */
const scheduled: { title: string; body: string; date: string; channelId?: string }[] = [];
const cancelled: string[] = [];
const permission = { granted: true };

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4, DEFAULT: 3 },
  getPermissionsAsync: async () => ({
    granted: permission.granted,
    canAskAgain: true,
  }),
  requestPermissionsAsync: async () => ({ granted: permission.granted }),
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async (request: {
    content: { title: string; body: string };
    trigger: { date: Date; channelId?: string };
  }) => {
    scheduled.push({
      title: request.content.title,
      body: request.content.body,
      date: new Date(request.trigger.date).toISOString(),
      channelId: request.trigger.channelId,
    });
    return `notification-${scheduled.length}`;
  },
  cancelScheduledNotificationAsync: async (id: string) => {
    cancelled.push(id);
  },
}));

const NOW = new Date('2026-09-13T12:00:00Z');

const DOMAIN: Domain = {
  storageKey: 'nura.test.notifications',
  channelId: 'test-channel',
  channelName: 'Test',
  max: 3,
};

beforeEach(async () => {
  await AsyncStorage.clear();
  scheduled.length = 0;
  cancelled.length = 0;
  permission.granted = true;
});

function planned(key: string, fireAt: string): Planned {
  return { key, fireAt, title: `Title ${key}`, body: `Body ${key}` };
}

describe('reconciling', () => {
  it('keeps what already matches', () => {
    const existing: Scheduled[] = [
      { key: 'a', notificationId: 'n1', fireAt: '2026-09-13T18:00:00Z' },
    ];
    const result = reconcile(existing, [planned('a', '2026-09-13T18:00:00Z')]);
    expect(result.toKeep).toHaveLength(1);
    expect(result.toSchedule).toHaveLength(0);
    expect(result.toCancel).toHaveLength(0);
  });

  it('cancels one whose time moved', () => {
    const existing: Scheduled[] = [
      { key: 'a', notificationId: 'n1', fireAt: '2026-09-13T18:00:00Z' },
    ];
    const result = reconcile(existing, [planned('a', '2026-09-13T20:00:00Z')]);
    expect(result.toCancel.map((row) => row.notificationId)).toEqual(['n1']);
    expect(result.toSchedule).toHaveLength(1);
  });

  it('cancels one whose source is no longer waiting', () => {
    const existing: Scheduled[] = [
      { key: 'a', notificationId: 'n1', fireAt: '2026-09-13T18:00:00Z' },
    ];
    const result = reconcile(existing, []);
    expect(result.toCancel).toHaveLength(1);
    expect(result.toSchedule).toHaveLength(0);
  });

  it('drops anything whose moment has gone', () => {
    const rows = upcoming(
      [
        planned('past', '2026-09-13T08:00:00Z'),
        planned('future', '2026-09-13T18:00:00Z'),
      ],
      NOW,
      10
    );
    expect(rows.map((row) => row.key)).toEqual(['future']);
  });

  it('holds only as many as the domain allows, soonest first', () => {
    const rows = upcoming(
      [
        planned('c', '2026-09-13T20:00:00Z'),
        planned('a', '2026-09-13T14:00:00Z'),
        planned('d', '2026-09-13T22:00:00Z'),
        planned('b', '2026-09-13T16:00:00Z'),
      ],
      NOW,
      2
    );
    expect(rows.map((row) => row.key)).toEqual(['a', 'b']);
  });
});

describe('rebuilding', () => {
  it('schedules what is due and remembers the ids', async () => {
    const result = await rebuild(DOMAIN, [planned('a', '2026-09-13T18:00:00Z')], {
      now: NOW,
    });
    expect(result.permitted).toBe(true);
    expect(result.added).toBe(1);
    expect(scheduled).toHaveLength(1);
    expect(scheduled[0]!.channelId).toBe('test-channel');
    expect(scheduled[0]!.date).toBe('2026-09-13T18:00:00.000Z');
  });

  it('**schedules nothing the second time** (section 34)', async () => {
    const plan = [planned('a', '2026-09-13T18:00:00Z')];
    await rebuild(DOMAIN, plan, { now: NOW });
    scheduled.length = 0;

    const again = await rebuild(DOMAIN, plan, { now: NOW });
    expect(again.added).toBe(0);
    expect(again.cancelled).toBe(0);
    expect(scheduled).toHaveLength(0);
    expect(again.scheduled).toBe(1);
  });

  it('cancels the obsolete one when a time changes', async () => {
    await rebuild(DOMAIN, [planned('a', '2026-09-13T18:00:00Z')], { now: NOW });
    const result = await rebuild(DOMAIN, [planned('a', '2026-09-13T20:00:00Z')], {
      now: NOW,
    });
    expect(result.cancelled).toBe(1);
    expect(cancelled).toEqual(['notification-1']);
  });

  it('cancels everything when the plan empties', async () => {
    await rebuild(DOMAIN, [planned('a', '2026-09-13T18:00:00Z')], { now: NOW });
    const result = await rebuild(DOMAIN, [], { now: NOW });
    expect(result.scheduled).toBe(0);
    expect(cancelled).toEqual(['notification-1']);
  });

  it('does nothing without permission, and says so (section 9)', async () => {
    permission.granted = false;
    const result = await rebuild(DOMAIN, [planned('a', '2026-09-13T18:00:00Z')], {
      now: NOW,
    });
    expect(result.permitted).toBe(false);
    expect(result.scheduled).toBe(0);
    expect(scheduled).toHaveLength(0);
  });

  it('clears the lot on request', async () => {
    await rebuild(DOMAIN, [planned('a', '2026-09-13T18:00:00Z')], { now: NOW });
    await cancelAll(DOMAIN);
    expect(cancelled).toEqual(['notification-1']);
    expect(await AsyncStorage.getItem(DOMAIN.storageKey)).toBeNull();
  });
});

describe('what the daily-life domains plan', () => {
  it('maps an occurrence id to the notification (section 34)', () => {
    const occurrence = parseOccurrence(occurrenceFixture());
    const rows = planReminders([occurrence]);
    expect(rows[0]!.key).toBe('reminder-occurrence:occurrence-1');
    expect(rows[0]!.data?.occurrenceId).toBe('occurrence-1');
  });

  it('fires a snoozed occurrence at what it was snoozed to', () => {
    const occurrence = parseOccurrence(
      occurrenceFixture({
        status: 'snoozed',
        snoozed_until: '2026-09-13T18:30:00Z',
      })
    );
    expect(planReminders([occurrence])[0]!.fireAt).toBe('2026-09-13T18:30:00Z');
  });

  it('leaves an answered occurrence out', () => {
    const occurrence = parseOccurrence(occurrenceFixture({ status: 'completed' }));
    expect(planReminders([occurrence])).toEqual([]);
  });

  it('leaves out a reminder whose notifications are off', () => {
    const occurrence = parseOccurrence(occurrenceFixture());
    expect(planReminders([occurrence], { enabledReminderIds: new Set() })).toEqual([]);
    expect(
      planReminders([occurrence], { enabledReminderIds: new Set(['reminder-1']) })
    ).toHaveLength(1);
  });

  it("puts the alarm's moment in its key, so each morning is its own", () => {
    const alarm = parseAlarm(alarmFixture());
    const rows = planAlarms([alarm]);
    expect(rows[0]!.key).toBe('alarm:alarm-1:2026-09-14T07:00:00Z');
  });

  it('leaves a disabled alarm out', () => {
    const alarm = parseAlarm(alarmFixture({ enabled: false, next_fire_at: null }));
    expect(planAlarms([alarm])).toEqual([]);
  });

  it('uses two channels, so nothing is announced twice', () => {
    expect(REMINDER_DOMAIN.channelId).not.toBe(ALARM_DOMAIN.channelId);
    // An alarm is the one place this feature asks for more attention
    // (section 4), and it is still a notification (section 11).
    expect(ALARM_DOMAIN.importance).toBe('high');
    expect(REMINDER_DOMAIN.importance).toBeUndefined();
  });

  it('rebuilds both domains from server rows', async () => {
    const occurrence = parseOccurrence(occurrenceFixture());
    const alarm = parseAlarm(alarmFixture());
    const reminders = await rebuildReminderNotifications([occurrence], { now: NOW });
    const alarms = await rebuildAlarmNotifications([alarm], { now: NOW });
    expect(reminders.scheduled).toBe(1);
    expect(alarms.scheduled).toBe(1);
    expect(scheduled).toHaveLength(2);
  });
});

describe('what these tests do not prove', () => {
  it('records calls, never deliveries', () => {
    // **Section 69: do not claim OS delivery.** Everything above asserts that
    // the right call was made with the right values. No notification has ever
    // fired, because the app has never been run on a physical phone.
    expect(Array.isArray(scheduled)).toBe(true);
    expect(Array.isArray(cancelled)).toBe(true);
  });
});
