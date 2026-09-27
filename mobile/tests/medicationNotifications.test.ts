/**
 * Medication reminders on the phone (PRD 5, sections 13-16, 42 and 55).
 *
 * `expo-notifications` is replaced by a recording stub, so these tests
 * exercise the real service -- which reminders it decides to schedule, what
 * they say, what it cancels when a schedule changes, and what it does when
 * permission is refused -- without an OS scheduler underneath.
 *
 * What is *not* claimed anywhere here: that a notification has ever actually
 * fired on a device. That needs a phone, and the README says so.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  cancelAllReminders,
  loadScheduledReminders,
  MAX_SCHEDULED,
  planReminders,
  rebuildReminders,
  reconcileReminders,
  reminderContent,
  requestReminderPermission,
} from '../src/features/medications/notifications';
import type { MedicationDose } from '../src/features/medications/types';

// `jest.mock` is hoisted above every import, so the stub is in place before
// the service under test is loaded even though it is written below them.
const scheduled: { id: string; content: unknown; trigger: unknown }[] = [];
const cancelled: string[] = [];
const permission = { granted: true, canAskAgain: true, asked: false };

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { HIGH: 4 },
  getPermissionsAsync: async () => ({
    granted: permission.granted,
    canAskAgain: permission.canAskAgain,
  }),
  requestPermissionsAsync: async () => {
    permission.asked = true;
    return { granted: permission.granted };
  },
  setNotificationChannelAsync: async () => undefined,
  scheduleNotificationAsync: async (request: { content: unknown; trigger: unknown }) => {
    const id = `notification-${scheduled.length + 1}`;
    scheduled.push({ id, ...request });
    return id;
  },
  cancelScheduledNotificationAsync: async (id: string) => {
    cancelled.push(id);
  },
}));

const NOW = new Date('2026-09-13T07:00:00Z');

function dose(overrides: Partial<MedicationDose> = {}): MedicationDose {
  return {
    id: 'dose-1',
    medicationId: 'medication-1',
    medicationName: 'Metformin',
    medicationDose: '500 mg',
    scheduleId: 'schedule-1',
    scheduledFor: '2026-09-13T08:00:00Z',
    localDate: '2026-09-13',
    status: 'scheduled',
    window: 'upcoming',
    actionAt: null,
    source: null,
    skipReasonCode: null,
    skipReasonText: null,
    snoozedUntil: null,
    snoozeCount: 0,
    late: false,
    canSnooze: true,
    ...overrides,
  };
}

beforeEach(async () => {
  await AsyncStorage.clear();
  scheduled.length = 0;
  cancelled.length = 0;
  permission.granted = true;
  permission.canAskAgain = true;
  permission.asked = false;
});

describe('reminderContent', () => {
  it('names the medication and the time, and says nothing else', () => {
    const content = reminderContent(dose());
    expect(content.title).toBe('Nura medication reminder');
    expect(content.body).toContain('Metformin — 500 mg');
    // PRD 5, section 57: no instruction, encouragement or warning.
    expect(content.body.toLowerCase()).not.toMatch(/don’t forget|must|important|urgent/);
  });

  it('can leave the medication out entirely', () => {
    // The privacy option PRD 5 section 15 asks to be architected for: nothing
    // switches this on yet, but a reminder on a lock screen can already be
    // built without a name in it.
    const content = reminderContent(dose(), { hideNames: true });
    expect(content.body).not.toContain('Metformin');
    expect(content.body).toContain('open Nura');
  });
});

describe('planReminders', () => {
  it('only schedules doses that are still waiting and still ahead', () => {
    const planned = planReminders(
      [
        dose({ id: 'past', scheduledFor: '2026-09-13T06:00:00Z' }),
        dose({ id: 'taken', status: 'taken' }),
        dose({ id: 'skipped', status: 'skipped' }),
        dose({ id: 'missed', status: 'missed' }),
        dose({ id: 'future' }),
      ],
      NOW
    );

    expect(planned.map((entry) => entry.doseId)).toEqual(['future']);
  });

  it('reminds at the snooze, not at the original time', () => {
    const planned = planReminders(
      [
        dose({
          status: 'snoozed',
          scheduledFor: '2026-09-13T06:00:00Z',
          snoozedUntil: '2026-09-13T09:00:00Z',
        }),
      ],
      NOW
    );

    expect(planned).toHaveLength(1);
    expect(planned[0]!.fireAt).toBe('2026-09-13T09:00:00Z');
  });

  it('stays under the number the OS will hold, keeping the soonest', () => {
    const many = Array.from({ length: MAX_SCHEDULED + 10 }, (_, index) =>
      dose({
        id: `dose-${index}`,
        scheduledFor: new Date(NOW.getTime() + (index + 1) * 3_600_000).toISOString(),
      })
    );

    const planned = planReminders(many, NOW);
    expect(planned).toHaveLength(MAX_SCHEDULED);
    expect(planned[0]!.doseId).toBe('dose-0');
  });

  it('sorts soonest first', () => {
    const planned = planReminders(
      [
        dose({ id: 'later', scheduledFor: '2026-09-13T20:00:00Z' }),
        dose({ id: 'sooner', scheduledFor: '2026-09-13T08:00:00Z' }),
      ],
      NOW
    );
    expect(planned.map((entry) => entry.doseId)).toEqual(['sooner', 'later']);
  });
});

describe('reconcileReminders', () => {
  const existing = [
    { doseId: 'a', notificationId: 'n-a', fireAt: '2026-09-13T08:00:00Z' },
    { doseId: 'b', notificationId: 'n-b', fireAt: '2026-09-13T20:00:00Z' },
  ];

  it('leaves an unchanged reminder alone rather than churning it', () => {
    const result = reconcileReminders(existing, [
      { doseId: 'a', fireAt: '2026-09-13T08:00:00Z', title: 't', body: 'b' },
      { doseId: 'b', fireAt: '2026-09-13T20:00:00Z', title: 't', body: 'b' },
    ]);

    expect(result.toCancel).toEqual([]);
    expect(result.toSchedule).toEqual([]);
    expect(result.toKeep).toHaveLength(2);
  });

  it('cancels a reminder whose time moved, and schedules the new one', () => {
    const result = reconcileReminders(existing, [
      { doseId: 'a', fireAt: '2026-09-13T09:00:00Z', title: 't', body: 'b' },
      { doseId: 'b', fireAt: '2026-09-13T20:00:00Z', title: 't', body: 'b' },
    ]);

    expect(result.toCancel.map((entry) => entry.notificationId)).toEqual(['n-a']);
    expect(result.toSchedule.map((entry) => entry.doseId)).toEqual(['a']);
  });

  it('cancels everything when the plan is empty', () => {
    // This is a paused schedule, a deleted one, and an inactivated medication
    // all at once: they all arrive here as "no doses" (PRD 5, section 42).
    const result = reconcileReminders(existing, []);
    expect(result.toCancel).toHaveLength(2);
    expect(result.toSchedule).toEqual([]);
  });
});

describe('rebuildReminders', () => {
  it('schedules the planned reminders and remembers their ids', async () => {
    const result = await rebuildReminders([dose()], { now: NOW });

    expect(result).toEqual({ scheduled: 1, permitted: true });
    expect(scheduled).toHaveLength(1);
    expect(scheduled[0]!.trigger).toMatchObject({ type: 'date' });

    const stored = await loadScheduledReminders();
    expect(stored).toEqual([
      {
        doseId: 'dose-1',
        notificationId: 'notification-1',
        fireAt: '2026-09-13T08:00:00Z',
      },
    ]);
  });

  it('is idempotent, so calling it on every focus costs nothing', async () => {
    await rebuildReminders([dose()], { now: NOW });
    await rebuildReminders([dose()], { now: NOW });

    expect(scheduled).toHaveLength(1);
    expect(cancelled).toEqual([]);
  });

  it('takes a reminder down once its dose has been recorded', async () => {
    await rebuildReminders([dose()], { now: NOW });
    await rebuildReminders([dose({ status: 'taken' })], { now: NOW });

    expect(cancelled).toEqual(['notification-1']);
    await expect(loadScheduledReminders()).resolves.toEqual([]);
  });

  it('carries the dose id and nothing about the medication in its payload', async () => {
    await rebuildReminders([dose()], { now: NOW });
    const content = scheduled[0]!.content as { data: Record<string, unknown> };
    expect(content.data).toEqual({ doseId: 'dose-1' });
  });

  it('schedules nothing without permission, and says so', async () => {
    // PRD 5, section 75: a refusal is handled rather than pretended past. The
    // schedule still exists on the server; only the phone's alert is off.
    permission.granted = false;

    const result = await rebuildReminders([dose()], { now: NOW });
    expect(result).toEqual({ scheduled: 0, permitted: false });
    expect(scheduled).toEqual([]);
  });
});

describe('requestReminderPermission', () => {
  it('does not ask again when permission is already granted', async () => {
    await expect(requestReminderPermission()).resolves.toBe(true);
    expect(permission.asked).toBe(false);
  });

  it('asks when it can, and reports the answer', async () => {
    permission.granted = false;
    await expect(requestReminderPermission()).resolves.toBe(false);
    expect(permission.asked).toBe(true);
  });

  it('does not nag when the user has already said no for good', async () => {
    permission.granted = false;
    permission.canAskAgain = false;

    await expect(requestReminderPermission()).resolves.toBe(false);
    expect(permission.asked).toBe(false);
  });
});

describe('cancelAllReminders', () => {
  it('takes every reminder down, e.g. on sign-out', async () => {
    await rebuildReminders(
      [dose({ id: 'a' }), dose({ id: 'b', scheduledFor: '2026-09-13T20:00:00Z' })],
      { now: NOW }
    );
    await cancelAllReminders();

    expect(cancelled).toHaveLength(2);
    await expect(loadScheduledReminders()).resolves.toEqual([]);
  });
});
