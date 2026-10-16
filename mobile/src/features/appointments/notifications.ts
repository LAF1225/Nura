/**
 * Appointment reminders on the phone (PRD 7, sections 36, 37 and 54).
 *
 * Two reminders per appointment -- a day before and two hours before -- scheduled
 * with the operating system exactly as medication reminders are. This file reuses
 * PRD 5's permission, channel and reconciliation machinery rather than repeating
 * it: same storage shape, same "make the OS agree with the plan" call, same
 * honesty about what a reminder can and cannot do.
 *
 * Three things that follow from PRD 7.
 *
 * **The reminder is an offer, not an alarm** (sections 10 and 37). The day-before
 * one asks whether the person would like to prepare; the two-hour one says where
 * and when. Neither is urgent and neither says anything medical.
 *
 * **Rescheduling is the whole point of section 54.** Changing the time, changing
 * the date, cancelling the appointment and turning reminders off all go through
 * one idempotent `rebuildAppointmentReminders` call, so there is no per-case
 * cancel logic to get wrong.
 *
 * **Nothing medical is in a notification** (section 57). The title is the
 * appointment's own name -- which the user wrote and which appears on their lock
 * screen either way -- and nothing else: no clinician, no location, no notes, and
 * no symptom or medication ever.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { createLogger } from '../../utils/logger';
import type { Appointment } from './types';

const log = createLogger('appointments');

/** Android needs a channel before anything can be posted to it. */
export const CHANNEL_ID = 'appointment-reminders';

const STORAGE_KEY = 'nura.appointments.notifications';

/**
 * How far ahead of an appointment each reminder fires (PRD 7, section 36).
 *
 * `prepare` is the day-before one, which is the one that offers to build the
 * summary (section 37). `soon` is the two-hour one.
 */
export const OFFSETS = {
  prepare: 24 * 60 * 60 * 1000,
  soon: 2 * 60 * 60 * 1000,
} as const;

export type ReminderKind = keyof typeof OFFSETS;

/**
 * iOS keeps at most 64 pending local notifications per app and silently drops
 * the rest. Medication reminders already claim up to 48, so appointments take a
 * small share: two reminders each for the next six appointments is far more than
 * anybody has in a fortnight.
 */
export const MAX_SCHEDULED = 12;

export interface PlannedReminder {
  appointmentId: string;
  kind: ReminderKind;
  /** ISO instant the reminder should fire. */
  fireAt: string;
  title: string;
  body: string;
}

/** A reminder the OS has accepted, and the id needed to cancel it again. */
export interface ScheduledReminder {
  appointmentId: string;
  kind: ReminderKind;
  notificationId: string;
  fireAt: string;
}

// --- planning (pure) --------------------------------------------------------

/**
 * What one reminder says (PRD 7, sections 36 and 37).
 *
 * The day-before reminder is the prompt from section 37, phrased as an offer.
 * Neither mentions the clinician, the address or anything clinical
 * (section 57).
 */
export function reminderContent(
  appointment: Pick<Appointment, 'title' | 'whenLabel' | 'preparationStatus'>,
  kind: ReminderKind
): { title: string; body: string } {
  if (kind === 'prepare') {
    const offer =
      appointment.preparationStatus === 'complete'
        ? 'Your Nura summary is ready.'
        : 'Would you like to prepare your Nura health summary?';
    return {
      title: `${appointment.title} tomorrow`,
      body: `${appointment.whenLabel}. ${offer}`,
    };
  }
  return {
    title: appointment.title,
    body: `${appointment.whenLabel}. Open Nura for your questions and summary.`,
  };
}

/**
 * The reminders worth putting in front of somebody, soonest first.
 *
 * Only appointments that are still scheduled, only ones with reminders switched
 * on, only moments still in the future, and only as many as the OS will hold. A
 * cancelled or completed appointment has nothing left to remind anybody about,
 * which is what makes cancelling stop its reminders with no special case
 * (PRD 7, section 54).
 */
export function planReminders(appointments: Appointment[], now: Date): PlannedReminder[] {
  const from = now.getTime();
  const planned: PlannedReminder[] = [];

  for (const appointment of appointments) {
    if (appointment.status !== 'scheduled') continue;
    if (!appointment.remindersEnabled) continue;

    const at = new Date(appointment.scheduledAt).getTime();
    if (!Number.isFinite(at)) continue;

    for (const kind of ['prepare', 'soon'] as const) {
      const fireAtMs = at - OFFSETS[kind];
      if (fireAtMs <= from) continue;
      planned.push({
        appointmentId: appointment.id,
        kind,
        fireAt: new Date(fireAtMs).toISOString(),
        ...reminderContent(appointment, kind),
      });
    }
  }

  return planned
    .sort((left, right) => left.fireAt.localeCompare(right.fireAt))
    .slice(0, MAX_SCHEDULED);
}

export interface Reconciliation {
  toCancel: ScheduledReminder[];
  toSchedule: PlannedReminder[];
  toKeep: ScheduledReminder[];
}

function keyOf(entry: { appointmentId: string; kind: ReminderKind }): string {
  return `${entry.appointmentId}:${entry.kind}`;
}

/**
 * The smallest set of changes that makes the OS agree with the plan.
 *
 * Reminders whose appointment, kind *and* time are unchanged are left alone
 * rather than cancelled and re-created, so an app opened five times in an hour
 * does not churn the notification tray. Anything whose time moved -- or whose
 * appointment is no longer scheduled -- is cancelled, which is what makes a time
 * change, a cancellation and a reminders-off switch all work without a special
 * case each (PRD 7, section 54).
 */
export function reconcileReminders(
  existing: ScheduledReminder[],
  planned: PlannedReminder[]
): Reconciliation {
  const wanted = new Map(planned.map((entry) => [keyOf(entry), entry]));
  const toKeep: ScheduledReminder[] = [];
  const toCancel: ScheduledReminder[] = [];

  for (const entry of existing) {
    const match = wanted.get(keyOf(entry));
    if (match !== undefined && match.fireAt === entry.fireAt) {
      toKeep.push(entry);
      wanted.delete(keyOf(entry));
    } else {
      toCancel.push(entry);
    }
  }

  return { toCancel, toSchedule: Array.from(wanted.values()), toKeep };
}

// --- the OS side ------------------------------------------------------------

export async function loadScheduledReminders(): Promise<ScheduledReminder[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is ScheduledReminder => {
      if (entry === null || typeof entry !== 'object') return false;
      const record = entry as ScheduledReminder;
      return (
        typeof record.appointmentId === 'string' &&
        typeof record.notificationId === 'string' &&
        typeof record.fireAt === 'string' &&
        (record.kind === 'prepare' || record.kind === 'soon')
      );
    });
  } catch {
    return [];
  }
}

async function saveScheduledReminders(entries: ScheduledReminder[]): Promise<void> {
  if (entries.length === 0) {
    await AsyncStorage.removeItem(STORAGE_KEY);
    return;
  }
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
}

/**
 * Asks for notification permission -- and only ever when called.
 *
 * Requested when somebody turns appointment reminders on, not at launch, so the
 * prompt arrives with an obvious reason attached (the rule PRD 5 section 14 set,
 * and there is no reason for PRD 7 to be different).
 */
export async function requestReminderPermission(): Promise<boolean> {
  try {
    const current = await Notifications.getPermissionsAsync();
    if (current.granted) return true;
    if (!current.canAskAgain) return false;
    return (await Notifications.requestPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

export async function hasReminderPermission(): Promise<boolean> {
  try {
    return (await Notifications.getPermissionsAsync()).granted;
  } catch {
    return false;
  }
}

async function ensureChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  try {
    await Notifications.setNotificationChannelAsync(CHANNEL_ID, {
      name: 'Appointment reminders',
      // Deliberately lower than the medication channel's HIGH: an appointment
      // tomorrow is something to know, not something to do this minute, and
      // PRD 7 section 10 rules out treating it as urgent.
      importance: Notifications.AndroidImportance.DEFAULT,
      vibrationPattern: [0, 200],
      enableVibrate: true,
    });
  } catch {
    // Channel setup failing is not worth blocking a reminder over; the OS
    // falls back to a default channel.
  }
}

async function scheduleOne(reminder: PlannedReminder): Promise<string | null> {
  try {
    return await Notifications.scheduleNotificationAsync({
      content: {
        title: reminder.title,
        body: reminder.body,
        // The appointment id travels with the notification so a tap handler can
        // open the right screen. It is an opaque id: nothing about the
        // appointment is in it (PRD 7, section 57).
        data: { appointmentId: reminder.appointmentId, kind: reminder.kind },
      },
      trigger: {
        type: Notifications.SchedulableTriggerInputTypes.DATE,
        date: new Date(reminder.fireAt),
        channelId: CHANNEL_ID,
      },
    });
  } catch {
    return null;
  }
}

async function cancelOne(notificationId: string): Promise<void> {
  try {
    await Notifications.cancelScheduledNotificationAsync(notificationId);
  } catch {
    // Already gone, or the OS forgot it. Either way there is nothing to do.
  }
}

/**
 * Makes the phone's pending reminders match these appointments.
 *
 * The single entry point PRD 7 section 54 asks for: called after an appointment
 * is created, edited, cancelled, completed or deleted, after the reminder switch
 * is changed, and whenever the appointment list is read. Being idempotent is what
 * lets it be called that freely.
 *
 * Does nothing at all without permission, and says so in the return value, so a
 * screen can tell the user their appointment is saved but their reminders are
 * silent rather than pretending they will fire.
 */
export async function rebuildAppointmentReminders(
  appointments: Appointment[],
  options: { now?: Date } = {}
): Promise<{ scheduled: number; permitted: boolean }> {
  if (!(await hasReminderPermission())) {
    return { scheduled: 0, permitted: false };
  }

  await ensureChannel();

  const existing = await loadScheduledReminders();
  const planned = planReminders(appointments, options.now ?? new Date());
  const { toCancel, toSchedule, toKeep } = reconcileReminders(existing, planned);

  for (const entry of toCancel) {
    await cancelOne(entry.notificationId);
  }

  const added: ScheduledReminder[] = [];
  for (const reminder of toSchedule) {
    const notificationId = await scheduleOne(reminder);
    if (notificationId !== null) {
      added.push({
        appointmentId: reminder.appointmentId,
        kind: reminder.kind,
        notificationId,
        fireAt: reminder.fireAt,
      });
    }
  }

  const next = [...toKeep, ...added];
  await saveScheduledReminders(next);
  // Counts only -- never a title, a time or an appointment id (PRD 7, s57).
  log.info('appointment reminders rebuilt', {
    kept: toKeep.length,
    added: added.length,
    cancelled: toCancel.length,
  });
  return { scheduled: next.length, permitted: true };
}

/** Removes every appointment reminder, e.g. on sign-out. */
export async function cancelAllAppointmentReminders(): Promise<void> {
  for (const entry of await loadScheduledReminders()) {
    await cancelOne(entry.notificationId);
  }
  await saveScheduledReminders([]);
}
