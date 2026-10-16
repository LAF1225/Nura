/**
 * Appointment reminders on the phone (PRD 7, sections 36, 37 and 54).
 *
 * `expo-notifications` is replaced by a recording stub, so these tests exercise
 * the real service -- which reminders it decides to schedule, what they say, and
 * what it cancels when an appointment moves or is cancelled -- without an OS
 * scheduler underneath.
 *
 * What is *not* claimed anywhere here: that a notification has ever actually
 * fired on a device. That needs a phone, and the README says so.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { parseAppointment } from '../src/features/appointments/api';
import {
  cancelAllAppointmentReminders,
  loadScheduledReminders,
  MAX_SCHEDULED,
  OFFSETS,
  planReminders,
  rebuildAppointmentReminders,
  reconcileReminders,
  reminderContent,
  requestReminderPermission,
} from '../src/features/appointments/notifications';
import type { Appointment } from '../src/features/appointments/types';
import { appointmentFixture } from './helpers';

// `jest.mock` is hoisted above every import, so the stub is in place before the
// service under test is loaded even though it is written below them.
const scheduled: { id: string; content: any; trigger: any }[] = [];
const cancelled: string[] = [];
const permission = { granted: true, canAskAgain: true, asked: false };

jest.mock('expo-notifications', () => ({
  SchedulableTriggerInputTypes: { DATE: 'date' },
  AndroidImportance: { DEFAULT: 3, HIGH: 4 },
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
    scheduled.push({ id, ...(request as { content: any; trigger: any }) });
    return id;
  },
  cancelScheduledNotificationAsync: async (id: string) => {
    cancelled.push(id);
  },
}));

const NOW = new Date('2026-09-28T09:00:00Z');

function appointment(overrides: Record<string, unknown> = {}): Appointment {
  return parseAppointment(appointmentFixture(overrides), '/appointments');
}

beforeEach(async () => {
  scheduled.length = 0;
  cancelled.length = 0;
  permission.granted = true;
  permission.canAskAgain = true;
  permission.asked = false;
  await AsyncStorage.clear();
});

describe('planning', () => {
  it('plans two reminders: a day before, and two hours before', () => {
    const plan = planReminders([appointment()], NOW);

    expect(plan.map((entry) => entry.kind)).toEqual(['prepare', 'soon']);
    const due = new Date('2026-10-02T14:30:00Z').getTime();
    expect(new Date(plan[0]!.fireAt).getTime()).toBe(due - OFFSETS.prepare);
    expect(new Date(plan[1]!.fireAt).getTime()).toBe(due - OFFSETS.soon);
  });

  it('leaves out an appointment with reminders switched off', () => {
    expect(planReminders([appointment({ reminders_enabled: false })], NOW)).toEqual([]);
  });

  it('leaves out a cancelled or completed appointment', () => {
    // Which is what makes cancelling stop its reminders with no special case
    // (PRD 7, section 54).
    expect(
      planReminders(
        [
          appointment({ status: 'cancelled', cancelled_at: '2026-09-28T09:00:00Z' }),
          appointment({
            id: 'a2',
            status: 'completed',
            completed_at: '2026-09-28T09:00:00Z',
          }),
        ],
        NOW
      )
    ).toEqual([]);
  });

  it('leaves out a moment that has already passed', () => {
    // Two hours before an appointment happening in one hour is in the past.
    const soon = appointment({ scheduled_at: '2026-09-28T10:00:00Z' });
    const plan = planReminders([soon], NOW);
    expect(plan).toEqual([]);
  });

  it('keeps the two-hour reminder when only the day-before one has passed', () => {
    // Tomorrow at 06:00, so the day-before reminder was due three hours ago and
    // the two-hour one is still to come.
    const tomorrow = appointment({ scheduled_at: '2026-09-29T06:00:00Z' });
    const plan = planReminders([tomorrow], NOW);
    expect(plan.map((entry) => entry.kind)).toEqual(['soon']);
  });

  it('orders by when they fire and stays inside the OS budget', () => {
    const many = Array.from({ length: 20 }, (_, index) =>
      appointment({
        id: `appointment-${index}`,
        scheduled_at: new Date(Date.UTC(2026, 9, 5 + index, 12, 0)).toISOString(),
      })
    );

    const plan = planReminders(many, NOW);
    expect(plan.length).toBe(MAX_SCHEDULED);
    const times = plan.map((entry) => entry.fireAt);
    expect([...times].sort()).toEqual(times);
  });
});

describe('what a reminder says', () => {
  it('offers to prepare the day before (PRD 7, section 37)', () => {
    const content = reminderContent(
      {
        title: 'Cardiology follow-up',
        whenLabel: 'Tomorrow at 3:30 PM',
        preparationStatus: 'not_started',
      },
      'prepare'
    );

    expect(content.title).toBe('Cardiology follow-up tomorrow');
    expect(content.body).toContain('Would you like to prepare your Nura health summary?');
  });

  it('says the summary is ready when it already is', () => {
    const content = reminderContent(
      {
        title: 'Cardiology follow-up',
        whenLabel: 'Tomorrow at 3:30 PM',
        preparationStatus: 'complete',
      },
      'prepare'
    );
    expect(content.body).toContain('Your Nura summary is ready.');
  });

  it('says where to look two hours before', () => {
    const content = reminderContent(
      {
        title: 'Physiotherapy',
        whenLabel: 'Today at 5:00 PM',
        preparationStatus: 'not_started',
      },
      'soon'
    );
    expect(content.title).toBe('Physiotherapy');
    expect(content.body).toContain('Today at 5:00 PM');
  });

  it('never mentions a clinician, a place or anything clinical', () => {
    // PRD 7 section 57. A reminder appears on a lock screen other people see.
    const withDetail = appointment({
      title: 'Cardiology follow-up',
      location_name: 'City Hospital',
    });
    for (const kind of ['prepare', 'soon'] as const) {
      const content = reminderContent(withDetail, kind);
      const text = `${content.title} ${content.body}`;
      expect(text).not.toContain('Ahmed');
      expect(text).not.toContain('City Hospital');
      for (const phrase of ['symptom', 'medication', 'dose', 'diagnos', 'urgent']) {
        expect(text.toLowerCase()).not.toContain(phrase);
      }
    }
  });

  it('carries only an opaque id in its data', () => {
    const plan = planReminders([appointment()], NOW);
    expect(plan[0]!.appointmentId).toBe('appointment-1');
  });
});

describe('reconciling with the OS', () => {
  it('keeps a reminder whose appointment, kind and time are unchanged', () => {
    const plan = planReminders([appointment()], NOW);
    const existing = plan.map((entry, index) => ({
      appointmentId: entry.appointmentId,
      kind: entry.kind,
      notificationId: `n-${index}`,
      fireAt: entry.fireAt,
    }));

    const result = reconcileReminders(existing, plan);
    expect(result.toKeep.length).toBe(2);
    expect(result.toSchedule).toEqual([]);
    expect(result.toCancel).toEqual([]);
  });

  it('cancels and reschedules a reminder whose time moved', () => {
    const before = planReminders([appointment()], NOW);
    const existing = before.map((entry, index) => ({
      appointmentId: entry.appointmentId,
      kind: entry.kind,
      notificationId: `n-${index}`,
      fireAt: entry.fireAt,
    }));

    const after = planReminders(
      [appointment({ scheduled_at: '2026-10-03T09:00:00Z' })],
      NOW
    );
    const result = reconcileReminders(existing, after);

    expect(result.toCancel.length).toBe(2);
    expect(result.toSchedule.length).toBe(2);
    expect(result.toKeep).toEqual([]);
  });

  it('cancels everything for an appointment that is no longer scheduled', () => {
    const before = planReminders([appointment()], NOW);
    const existing = before.map((entry, index) => ({
      appointmentId: entry.appointmentId,
      kind: entry.kind,
      notificationId: `n-${index}`,
      fireAt: entry.fireAt,
    }));

    const result = reconcileReminders(existing, []);
    expect(result.toCancel.length).toBe(2);
    expect(result.toSchedule).toEqual([]);
  });
});

describe('rebuilding', () => {
  it('schedules the plan and remembers the ids', async () => {
    const outcome = await rebuildAppointmentReminders([appointment()], { now: NOW });

    expect(outcome.permitted).toBe(true);
    expect(outcome.scheduled).toBe(2);
    expect(scheduled.length).toBe(2);
    expect((await loadScheduledReminders()).length).toBe(2);
  });

  it('is idempotent: calling it again changes nothing', async () => {
    await rebuildAppointmentReminders([appointment()], { now: NOW });
    scheduled.length = 0;

    await rebuildAppointmentReminders([appointment()], { now: NOW });

    expect(scheduled).toEqual([]);
    expect(cancelled).toEqual([]);
  });

  it('reschedules when the appointment moves (PRD 7, section 54)', async () => {
    await rebuildAppointmentReminders([appointment()], { now: NOW });
    scheduled.length = 0;

    await rebuildAppointmentReminders(
      [appointment({ scheduled_at: '2026-10-03T09:00:00Z' })],
      { now: NOW }
    );

    expect(cancelled.length).toBe(2);
    expect(scheduled.length).toBe(2);
  });

  it('cancels everything when reminders are switched off', async () => {
    await rebuildAppointmentReminders([appointment()], { now: NOW });
    scheduled.length = 0;

    const outcome = await rebuildAppointmentReminders(
      [appointment({ reminders_enabled: false })],
      { now: NOW }
    );

    expect(cancelled.length).toBe(2);
    expect(outcome.scheduled).toBe(0);
    expect(await loadScheduledReminders()).toEqual([]);
  });

  it('does nothing at all without permission, and says so', async () => {
    permission.granted = false;
    const outcome = await rebuildAppointmentReminders([appointment()], { now: NOW });

    expect(outcome).toEqual({ scheduled: 0, permitted: false });
    expect(scheduled).toEqual([]);
  });

  it('asks for permission only when asked to', async () => {
    permission.granted = false;
    await rebuildAppointmentReminders([appointment()], { now: NOW });
    expect(permission.asked).toBe(false);

    permission.granted = true;
    expect(await requestReminderPermission()).toBe(true);
  });

  it('cancels every reminder on sign-out', async () => {
    await rebuildAppointmentReminders([appointment()], { now: NOW });
    await cancelAllAppointmentReminders();

    expect(cancelled.length).toBe(2);
    expect(await loadScheduledReminders()).toEqual([]);
  });
});
