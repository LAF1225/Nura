/**
 * Daily-life notifications on the phone (PRD 12, sections 9, 11, 34 and 62).
 *
 * The domain wrapper section 62 asks for: the engine is
 * `features/notifications/scheduler`, and this file decides *what* to
 * schedule. Two domains, deliberately separate channels:
 *
 *   reminders   a message at a time the person chose
 *   alarms      a time whose purpose is to be noticed
 *
 * Routines get no notification of their own, and that is a decision rather
 * than an omission: a routine is a checklist for a day, its run is open all
 * day, and a notification at half past seven for something somebody can tick
 * off at nine would be noise. Today shows it; the robot shows it; the phone
 * does not interrupt for it.
 *
 * **The planning half is pure** and is where the interesting rules live: which
 * occurrences deserve a notification, how many the operating system will
 * accept, and what has to be cancelled when a reminder changes.
 *
 * **Nothing in this file has ever fired.** The app has never been run on a
 * physical phone, so no notification has fired, no alarm has fired and no
 * vibration has been felt. `copy.ALARM_FORM_NOTE` says so where somebody
 * setting one can read it, and the server says it again with every alarm list.
 */
import {
  cancelAll,
  rebuild,
  type Domain,
  type Planned,
  type RebuildResult,
} from '../notifications/scheduler';
import type { Alarm, ReminderOccurrence } from './types';

/**
 * Reminders take a modest share of the operating system's 64.
 *
 * Medication reminders already claim up to 48 and appointments 12. A fortnight
 * of daily reminders would not fit beside them, so this holds the next few
 * days -- which is what matters, because the app brings the mirror back in
 * step every time it is opened (section 34).
 */
export const REMINDER_DOMAIN: Domain = {
  storageKey: 'nura.productivity.reminderNotifications',
  channelId: 'general-reminders',
  channelName: 'Reminders',
  max: 8,
};

/**
 * Alarms get their own channel and the `high` importance, which is the one
 * place this feature asks the operating system for more attention -- section 4
 * defines an alarm as a time-critical alert whose purpose is to be noticed.
 *
 * **It is still a notification.** Section 11: a notification channel is not a
 * clock app, nothing here has been verified on a handset, and the app says so
 * rather than implying otherwise.
 */
export const ALARM_DOMAIN: Domain = {
  storageKey: 'nura.productivity.alarmNotifications',
  channelId: 'alarms',
  channelName: 'Alarms',
  max: 8,
  importance: 'high',
};

// --- planning (pure) --------------------------------------------------------

/**
 * What one reminder notification says.
 *
 * The reminder's own title, which the person wrote and which appears on their
 * lock screen either way, and nothing else: no medical content, and no
 * instruction about what happens if it is missed.
 */
export function reminderContent(occurrence: ReminderOccurrence): {
  title: string;
  body: string;
} {
  return {
    title: occurrence.title,
    body: occurrence.body ?? 'Open Nura to mark this done.',
  };
}

/**
 * The occurrences worth putting in front of somebody.
 *
 * Only ones still waiting to be answered, only ones whose reminder has
 * notifications switched on, and only in the future. A snoozed occurrence is
 * scheduled for what it was snoozed *to* -- otherwise snoozing would do
 * nothing to the notification, which is the one thing snoozing is for.
 *
 * `notificationEnabled` is checked per occurrence through the flag the row
 * carries from its reminder, so turning notifications off for one reminder
 * does not silence the rest.
 */
export function planReminders(
  occurrences: ReminderOccurrence[],
  options: { enabledReminderIds?: ReadonlySet<string> } = {}
): Planned[] {
  const allowed = options.enabledReminderIds;
  return occurrences
    .filter(
      (occurrence) =>
        (occurrence.status === 'scheduled' || occurrence.status === 'snoozed') &&
        (allowed === undefined || allowed.has(occurrence.reminderId))
    )
    .map((occurrence) => ({
      key: `reminder-occurrence:${occurrence.id}`,
      fireAt:
        occurrence.status === 'snoozed' && occurrence.snoozedUntil !== null
          ? occurrence.snoozedUntil
          : occurrence.scheduledFor,
      data: { occurrenceId: occurrence.id, reminderId: occurrence.reminderId },
      ...reminderContent(occurrence),
    }));
}

/**
 * The alarms worth scheduling, with the instant each is for in the key.
 *
 * The instant is part of the key because a daily alarm is a different occasion
 * every morning and there are no occurrence rows to carry that -- the same
 * reason the robot's dedupe key carries it.
 */
export function planAlarms(alarms: Alarm[]): Planned[] {
  return alarms
    .filter((alarm) => alarm.enabled && alarm.nextFireAt !== null)
    .map((alarm) => ({
      key: `alarm:${alarm.id}:${alarm.nextFireAt ?? ''}`,
      fireAt: alarm.nextFireAt as string,
      title: alarm.label,
      body: alarm.scheduleLabel,
      data: { alarmId: alarm.id },
    }));
}

// --- the OS side ------------------------------------------------------------

/**
 * Brings the phone's reminder notifications in step with the server's rows.
 *
 * Section 34's reconciliation: load what is due, compare with what the
 * operating system holds, create the missing ones, cancel the stale ones. Safe
 * to call on every app start and resume, because it is idempotent.
 */
export async function rebuildReminderNotifications(
  occurrences: ReminderOccurrence[],
  options: { enabledReminderIds?: ReadonlySet<string>; now?: Date } = {}
): Promise<RebuildResult> {
  return rebuild(REMINDER_DOMAIN, planReminders(occurrences, options), {
    now: options.now,
  });
}

export async function rebuildAlarmNotifications(
  alarms: Alarm[],
  options: { now?: Date } = {}
): Promise<RebuildResult> {
  return rebuild(ALARM_DOMAIN, planAlarms(alarms), { now: options.now });
}

/** Removes every daily-life notification, e.g. on sign-out. */
export async function cancelDailyLifeNotifications(): Promise<void> {
  await cancelAll(REMINDER_DOMAIN);
  await cancelAll(ALARM_DOMAIN);
}
