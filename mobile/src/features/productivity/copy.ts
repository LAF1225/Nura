/**
 * Every sentence the daily-life screens say (PRD 12, sections 6, 9, 11, 19).
 *
 * One module, for the reason the backend has one: a sentence written in three
 * screens is three sentences that will eventually disagree.
 *
 * **What is deliberately *not* here** is anything the server renders. A due
 * label, a schedule sentence, a routine's progress line and the alarm
 * limitation all arrive on the row, because `services/productivity/wording.py`
 * is the one place that writes them -- and the alarm limitation is a sentence
 * section 11 does not let a client leave out, so it cannot live in a file a
 * client could forget to read.
 */
import type { CapabilityState, SnoozeMinutes, TaskPriority } from './types';

// --- screens ----------------------------------------------------------------

export const DAILY_LIFE_TITLE = 'Tasks & routines';
export const DAILY_LIFE_SUBTITLE = 'Your own list, reminders, alarms and routines.';

export const TASKS_TITLE = 'Tasks';
export const REMINDERS_TITLE = 'Reminders';
export const ALARMS_TITLE = 'Alarms';
export const ROUTINES_TITLE = 'Routines';

export const NEW_TASK_TITLE = 'New task';
export const EDIT_TASK_TITLE = 'Edit task';
export const NEW_REMINDER_TITLE = 'New reminder';
export const NEW_ALARM_TITLE = 'New alarm';
export const NEW_ROUTINE_TITLE = 'New routine';
export const EDIT_ROUTINE_TITLE = 'Edit routine';

// --- empty states -----------------------------------------------------------

export const NO_TASKS = 'Nothing on your list.';
export const NO_TASKS_HINT = 'Add something you want to get done.';
export const NO_REMINDERS = 'No reminders set up.';
export const NO_REMINDERS_HINT = 'A reminder is a message at a time you choose.';
export const NO_ALARMS = 'No alarms set.';
export const NO_ROUTINES = 'No routines yet.';
export const NO_ROUTINES_HINT =
  'A routine is a few steps you do together, at the same time.';
export const NO_RUN_TODAY = 'Nothing scheduled today.';

// --- buttons and actions ----------------------------------------------------

export const ADD_TASK = 'Add task';
export const ADD_REMINDER = 'Add reminder';
export const ADD_ALARM = 'Add alarm';
export const ADD_ROUTINE = 'Add routine';
export const SAVE = 'Save';
export const DONE = 'Done';
export const UNDO = 'Undo';
export const ARCHIVE = 'Archive';
export const DELETE = 'Delete';
export const DISMISS = 'Dismiss';
export const SNOOZE = 'Snooze';
export const PAUSE = 'Pause';
export const RESUME = 'Resume';
export const SKIP = 'Skip today';
export const COMPLETE_RUN = 'Mark the whole routine done';
export const MOVE_UP = 'Move up';
export const MOVE_DOWN = 'Move down';
export const ADD_STEP = 'Add step';
export const REMOVE_STEP = 'Remove step';

// --- form labels ------------------------------------------------------------

export const TITLE_LABEL = 'Title';
export const NOTES_LABEL = 'Notes';
export const DUE_LABEL = 'Due';
export const PRIORITY_LABEL = 'Priority';
export const TIME_LABEL = 'Time';
export const REPEAT_LABEL = 'Repeat';
export const DAYS_LABEL = 'Days';
export const DAY_OF_MONTH_LABEL = 'Day of the month';
export const LABEL_LABEL = 'Label';
export const SOUND_LABEL = 'Sound';
export const VIBRATION_LABEL = 'Vibrate';
export const NOTIFICATION_LABEL = 'Notify me';
export const STEPS_LABEL = 'Steps';
export const OPTIONAL_STEP_LABEL = 'Optional';

export const TITLE_HINT = 'A few words saying what it is.';
export const NO_DUE_DATE = 'No due date';
export const DUE_DATE_HINT = 'Optional. A task without one is a normal task.';
export const TIME_HINT = 'A 24-hour time, like 07:30.';

// --- validation -------------------------------------------------------------

export const TITLE_REQUIRED = 'Give this a title.';
export const TIME_REQUIRED = 'Choose a time.';
export const TIME_INVALID = 'Use a 24-hour time, like 07:30.';
export const DAYS_REQUIRED = 'Choose at least one day.';
export const DAY_OF_MONTH_REQUIRED = 'Choose a day between 1 and 31.';
export const STEPS_REQUIRED = 'A routine needs at least one step.';
export const DATE_INVALID = 'Use a date like 2026-03-14.';

/** Section 35, said where somebody choosing a month-end date can read it. */
export const MONTH_END_NOTE =
  'A month without that day uses its last day, so the 31st is the 28th in February.';

// --- notifications (section 9) ----------------------------------------------

/**
 * Said when the operating system has refused notifications.
 *
 * The reminder is still stored, it is still on Today, and the screen says why
 * it will be quiet -- which is section 9's requirement, and the opposite of a
 * reminder that silently does nothing.
 */
export const NOTIFICATIONS_BLOCKED =
  'Notifications are turned off for Nura in your phone settings, so reminders ' +
  'will be quiet. They are still saved and still on your Today screen.';

export const NOTIFICATIONS_ASK = 'Allow notifications';

/**
 * **Section 11 and section 71, in the app.**
 *
 * The server sends the authoritative sentence with every alarm list and the
 * screen shows that one. This is the shorter version for a form, where there
 * is no list response to read it from -- and it says the same thing, because
 * saying anything stronger would be a claim nothing in this project can back.
 */
export const ALARM_FORM_NOTE =
  'Nura schedules alarms as phone notifications. Whether one actually wakes ' +
  'you has never been tested on a physical phone.';

// --- labels -----------------------------------------------------------------

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  normal: 'Normal',
  important: 'Important',
};

export const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const WEEKDAY_NAMES = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

export const REPEAT_LABELS: Record<string, string> = {
  one_time: 'Once',
  daily: 'Every day',
  selected_days: 'On chosen days',
  weekly: 'Every week',
  monthly: 'Every month',
};

export const SNOOZE_LABELS: Record<SnoozeMinutes, string> = {
  10: '10 minutes',
  30: '30 minutes',
  60: '1 hour',
};

/** What a capability row says next to its name (sections 25-29). */
export const CAPABILITY_STATE_LABELS: Record<CapabilityState, string> = {
  available: 'Available',
  not_configured: 'Not set up in this build',
  unavailable: 'Not working right now',
};

/**
 * **Section 42, said on the caregiver's own screen.**
 *
 * A caregiver with the `routines` permission sees routines and nothing else.
 * Saying so is better than a short list somebody has to wonder about -- and it
 * is the truth: there is no caregiver route anywhere that reaches a task, an
 * alarm or a personal reminder.
 */
export const CAREGIVER_ROUTINES_ONLY =
  'Routines only. Tasks, alarms and personal reminders stay private.';

export const EXTERNAL_TITLE = 'What Nura can reach';
export const EXTERNAL_NOTE =
  'Nura cannot look anything up on the internet in this build, and nothing ' +
  'you add here goes to any calendar outside Nura.';

// --- offline (sections 37, 38 and 39) ---------------------------------------

export const PENDING_BADGE = 'Saved on this phone';
export const PENDING_NOTE =
  'This is saved here and will sync when Nura can reach the server.';

// --- sentences built from values --------------------------------------------

export function taskCountSentence(open: number, overdue: number): string {
  if (open === 0) return NO_TASKS;
  const base = open === 1 ? '1 task' : `${open} tasks`;
  return overdue > 0 ? `${base}, ${overdue} past its due time` : base;
}

export function routineCountSentence(active: number): string {
  if (active === 0) return NO_ROUTINES;
  return active === 1 ? '1 routine' : `${active} routines`;
}

export function reminderCountSentence(count: number): string {
  if (count === 0) return NO_REMINDERS;
  return count === 1 ? '1 reminder' : `${count} reminders`;
}

export function alarmCountSentence(count: number): string {
  if (count === 0) return NO_ALARMS;
  return count === 1 ? '1 alarm' : `${count} alarms`;
}

/** "Mon, Wed and Fri", or "Every day" for nothing chosen. */
export function weekdaySentence(weekdays: number[] | null): string {
  if (!weekdays || weekdays.length === 0) return 'Every day';
  const ordered = [...new Set(weekdays)].sort((left, right) => left - right);
  if (ordered.length === 7) return 'Every day';
  const names = ordered.map((day) => WEEKDAY_SHORT[day] ?? '');
  const last = names[names.length - 1] ?? '';
  if (names.length === 1) return last;
  return `${names.slice(0, -1).join(', ')} and ${last}`;
}

/** The accessible label for a step row, so a screen reader hears its state. */
export function stepAccessibilityLabel(
  title: string,
  state: 'completed' | 'skipped' | null
): string {
  if (state === 'completed') return `${title}. Done.`;
  if (state === 'skipped') return `${title}. Skipped.`;
  return `${title}. Not done yet.`;
}

/**
 * The accessible label for a task's tick box -- never colour alone (s48).
 *
 * Always carries a state phrase, even for an ordinary open task. Two reasons:
 * a screen reader should hear whether a task is done without having to infer
 * it from a checkbox role, and the row beside it is labelled with the bare
 * title -- two controls with identical labels is exactly the ambiguity this
 * is meant to avoid.
 */
export function taskAccessibilityLabel(
  title: string,
  done: boolean,
  overdue: boolean
): string {
  if (done) return `${title}. Done.`;
  return overdue ? `${title}. Past its due time.` : `${title}. Not done.`;
}
