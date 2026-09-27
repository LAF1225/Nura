/**
 * Medication reminders on the phone (PRD 5, sections 13-16, 41, 42, 55, 72).
 *
 * **These are OS-scheduled local notifications, and nothing else.** The
 * JavaScript process is not running most of the time, so anything that
 * depended on it would simply not fire (PRD 5, sections 13 and 55). The
 * backend stays the source of truth for schedules and history; this file's
 * whole job is to mirror the next few doses into the operating system's own
 * scheduler and keep that mirror honest.
 *
 * **Local, not push** (PRD 5, section 41). One channel, so there is no way for
 * the same dose to be announced twice. No remote notifications are sent, which
 * also means no medication name ever leaves the phone to reach a push service
 * (section 58).
 *
 * **No notification action buttons.** PRD 5 section 16 allows them only if
 * they are reliable in the stack, and says plainly not to fake unsupported
 * ones. Acting on a notification would have to reach the backend from a
 * background handler, which is not something this app can promise on both
 * platforms -- so tapping a reminder opens Nura, where Taken, Snooze and Skip
 * are real buttons. That is an honest reminder rather than a button that
 * sometimes does nothing.
 *
 * The planning half of this file is pure and is where the interesting rules
 * live: which doses deserve a reminder, how many the OS will accept, and what
 * has to be cancelled when a schedule changes.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { createLogger } from '../../utils/logger';
import { doseTitle, formatDoseTime } from './doses';
import type { MedicationDose } from './types';

const log = createLogger('medications');

/** Android needs a channel before anything can be posted to it. */
export const CHANNEL_ID = 'medication-reminders';

/**
 * iOS keeps at most 64 pending local notifications per app and silently drops
 * the rest. Staying under that leaves room for anything a later PRD schedules,
 * and a fortnight of twice-daily reminders fits comfortably inside it.
 */
export const MAX_SCHEDULED = 48;

const STORAGE_KEY = 'nura.medications.notifications';

export interface PlannedReminder {
  doseId: string;
  /** ISO instant the reminder should fire. */
  fireAt: string;
  title: string;
  body: string;
}

/** A reminder the OS has accepted, and the id needed to cancel it again. */
export interface ScheduledReminder {
  doseId: string;
  notificationId: string;
  fireAt: string;
}

export interface ReminderOptions {
  /**
   * Leaves the medication out of the notification body.
   *
   * Nothing sets this yet; it exists because a reminder appears on a lock
   * screen other people can see, and PRD 5 section 15 asks the content to be
   * built so that option can be added without rewriting the reminders.
   */
  hideNames?: boolean;
}

// --- planning (pure) --------------------------------------------------------

/**
 * What one reminder says (PRD 5, section 15).
 *
 * Concise, and nothing beyond the fact: no instruction, no encouragement, no
 * warning about what happens if it is missed (section 57).
 */
export function reminderContent(
  dose: Pick<MedicationDose, 'medicationName' | 'medicationDose' | 'scheduledFor'>,
  options: ReminderOptions = {}
): { title: string; body: string } {
  const at = formatDoseTime(dose.scheduledFor);
  if (options.hideNames) {
    return {
      title: 'Nura medication reminder',
      body: `It’s ${at} — open Nura to see what’s due.`,
    };
  }
  return {
    title: 'Nura medication reminder',
    body: `${doseTitle(dose)}\nScheduled for ${at}`,
  };
}

/**
 * The doses worth putting in front of somebody, soonest first.
 *
 * Only ones still waiting to be recorded, only ones still in the future, and
 * only as many as the OS will hold. A dose already taken, skipped or missed
 * has nothing left to remind anybody about.
 */
export function planReminders(
  doses: MedicationDose[],
  now: Date,
  options: ReminderOptions = {}
): PlannedReminder[] {
  const from = now.getTime();

  return doses
    .filter((dose) => dose.status === 'scheduled' || dose.status === 'snoozed')
    .map((dose) => ({
      dose,
      fireAt:
        dose.status === 'snoozed' && dose.snoozedUntil !== null
          ? dose.snoozedUntil
          : dose.scheduledFor,
    }))
    .filter((entry) => {
      const at = new Date(entry.fireAt).getTime();
      return Number.isFinite(at) && at > from;
    })
    .sort((left, right) => left.fireAt.localeCompare(right.fireAt))
    .slice(0, MAX_SCHEDULED)
    .map((entry) => ({
      doseId: entry.dose.id,
      fireAt: entry.fireAt,
      ...reminderContent({ ...entry.dose, scheduledFor: entry.fireAt }, options),
    }));
}

export interface Reconciliation {
  toCancel: ScheduledReminder[];
  toSchedule: PlannedReminder[];
  toKeep: ScheduledReminder[];
}

/**
 * The smallest set of changes that makes the OS agree with the plan.
 *
 * Reminders whose dose *and* time are unchanged are left alone rather than
 * being cancelled and re-created, so an app that is opened five times in an
 * hour does not churn the notification tray. Anything whose time moved -- or
 * whose dose is no longer waiting -- is cancelled, which is what makes a
 * schedule edit, a pause and an inactivated medication all stop reminding
 * without a special case each (PRD 5, section 42).
 */
export function reconcileReminders(
  existing: ScheduledReminder[],
  planned: PlannedReminder[]
): Reconciliation {
  const wanted = new Map(planned.map((entry) => [entry.doseId, entry]));
  const toKeep: ScheduledReminder[] = [];
  const toCancel: ScheduledReminder[] = [];

  for (const entry of existing) {
    const match = wanted.get(entry.doseId);
    if (match !== undefined && match.fireAt === entry.fireAt) {
      toKeep.push(entry);
      wanted.delete(entry.doseId);
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
    return parsed.filter(
      (entry): entry is ScheduledReminder =>
        entry !== null &&
        typeof entry === 'object' &&
        typeof (entry as ScheduledReminder).doseId === 'string' &&
        typeof (entry as ScheduledReminder).notificationId === 'string' &&
        typeof (entry as ScheduledReminder).fireAt === 'string'
    );
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
 * PRD 5 section 14: this is requested when somebody turns reminders on, not
 * at launch and not during onboarding, so the prompt arrives with an obvious
 * reason attached.
 */
export async function requestReminderPermission(): Promise<boolean> {
  try {
    const current = await Notifications.getPermissionsAsync();
    if (current.granted) return true;
    if (!current.canAskAgain) return false;
    const asked = await Notifications.requestPermissionsAsync();
    return asked.granted;
  } catch {
    // A platform that cannot answer is treated as "no". The schedule is still
    // saved on the server, and the app still shows what is due.
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
      name: 'Medication reminders',
      importance: Notifications.AndroidImportance.HIGH,
      // A reminder should be noticeable without being an alarm: this is a
      // routine part of somebody's day, not an emergency (PRD 5, section 29).
      vibrationPattern: [0, 250],
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
        // The dose id travels with the notification so a future tap handler
        // can open the right row. It is an opaque id: nothing about the
        // medication is in it (PRD 5, section 58).
        data: { doseId: reminder.doseId },
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
 * Makes the phone's pending reminders match these doses.
 *
 * This is the single entry point PRD 5 section 42 asks for: it is called after
 * a schedule changes, after a pause or resume, after a medication is
 * inactivated, and whenever the app comes back to the foreground. Being
 * idempotent is what lets it be called that freely.
 *
 * Does nothing at all without permission, and says so in the return value, so
 * a screen can tell the user their reminders are saved but silent rather than
 * pretending they will fire (PRD 5, section 75).
 */
export async function rebuildReminders(
  doses: MedicationDose[],
  options: ReminderOptions & { now?: Date } = {}
): Promise<{ scheduled: number; permitted: boolean }> {
  if (!(await hasReminderPermission())) {
    return { scheduled: 0, permitted: false };
  }

  await ensureChannel();

  const existing = await loadScheduledReminders();
  const planned = planReminders(doses, options.now ?? new Date(), options);
  const { toCancel, toSchedule, toKeep } = reconcileReminders(existing, planned);

  for (const entry of toCancel) {
    await cancelOne(entry.notificationId);
  }

  const added: ScheduledReminder[] = [];
  for (const reminder of toSchedule) {
    const notificationId = await scheduleOne(reminder);
    if (notificationId !== null) {
      added.push({
        doseId: reminder.doseId,
        notificationId,
        fireAt: reminder.fireAt,
      });
    }
  }

  const next = [...toKeep, ...added];
  await saveScheduledReminders(next);
  // Counts only -- never a medication, a time or a dose id (PRD 5, s58, s59).
  log.info('medication reminders rebuilt', {
    kept: toKeep.length,
    added: added.length,
    cancelled: toCancel.length,
  });
  return { scheduled: next.length, permitted: true };
}

/** Removes every medication reminder, e.g. on sign-out. */
export async function cancelAllReminders(): Promise<void> {
  for (const entry of await loadScheduledReminders()) {
    await cancelOne(entry.notificationId);
  }
  await saveScheduledReminders([]);
}
