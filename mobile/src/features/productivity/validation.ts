/**
 * What a daily-life form checks before it sends anything (PRD 12, s59, s68).
 *
 * Pure functions, deliberately. The forms are controlled components, and a
 * controlled `TextInput` cannot be driven from a test in this stack -- React
 * 19 with this testing library does not flush a component's own `useState`
 * update from a `fireEvent`. So the rules live here, where they can be tested
 * properly, and the screens become the thin part that collects values and
 * renders whatever comes back.
 *
 * **The server checks all of this again**, and the database checks most of it
 * a third time. That is not redundancy for its own sake: the constraint is
 * what makes a bad row impossible, the service's refusal is a sentence a
 * client can act on, and this is what stops somebody having to wait for a
 * round trip to be told they left the time blank.
 *
 * **Nothing here guesses.** A missing time is an error, not nine o'clock; a
 * missing day is an error, not today. Section 22's clarification rule is about
 * the assistant, and the same thing is true of a form: a reminder with no time
 * is not a reminder.
 */
import {
  DATE_INVALID,
  DAYS_REQUIRED,
  DAY_OF_MONTH_REQUIRED,
  STEPS_REQUIRED,
  TIME_INVALID,
  TIME_REQUIRED,
  TITLE_REQUIRED,
} from './copy';
import type {
  AlarmRecurrence,
  ReminderRecurrence,
  RoutineScheduleType,
  RoutineStepInput,
} from './types';

/** `YYYY-MM-DD`. */
export const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** `HH:MM` on a 24-hour clock. */
export const TIME_PATTERN = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;

/** Field name to message. Empty means nothing is wrong. */
export type Errors = Record<string, string>;

export function isValidDate(value: string): boolean {
  if (!DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  if (!year || !month || !day) return false;
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;
  // A real calendar date: 2026-02-30 matches the pattern and is not a day.
  const candidate = new Date(year, month - 1, day);
  return (
    candidate.getFullYear() === year &&
    candidate.getMonth() === month - 1 &&
    candidate.getDate() === day
  );
}

/**
 * A local date and a local time as an instant.
 *
 * Built with the `Date` constructor's local-time form rather than by parsing a
 * string, which is the one way to be sure the phone's own zone is used -- the
 * same reason `utils/date` builds a local date string by hand rather than
 * going through `toISOString`.
 *
 * The time defaults to nine in the morning when a date was given without one,
 * which is the only default in this module and is why it is named: a task due
 * "on Tuesday" has to land somewhere, and the start of the working day is the
 * least surprising answer. A *reminder* never reaches this -- it requires a
 * time, because a reminder with no time is not a reminder.
 */
export const DEFAULT_DUE_TIME = '09:00';

export function instantFrom(date: string, time?: string): string | null {
  if (!isValidDate(date)) return null;
  const chosen = time && TIME_PATTERN.test(time) ? time : DEFAULT_DUE_TIME;
  const [year, month, day] = date.split('-').map(Number);
  const [hour, minute] = chosen.split(':').map(Number);
  const value = new Date(
    year ?? 1970,
    (month ?? 1) - 1,
    day ?? 1,
    hour ?? 9,
    minute ?? 0
  );
  return Number.isFinite(value.getTime()) ? value.toISOString() : null;
}

// --- tasks ------------------------------------------------------------------

export interface TaskDraft {
  title: string;
  dueDate: string;
  dueTime: string;
}

/**
 * A task needs a title. Everything else is optional, including the due date --
 * section 5 is explicit that a task may have none.
 */
export function validateTask(draft: TaskDraft): Errors {
  const errors: Errors = {};
  if (draft.title.trim().length === 0) errors.title = TITLE_REQUIRED;
  if (draft.dueDate.length > 0 && !isValidDate(draft.dueDate)) {
    errors.dueDate = DATE_INVALID;
  }
  if (draft.dueTime.length > 0 && !TIME_PATTERN.test(draft.dueTime)) {
    errors.dueTime = TIME_INVALID;
  }
  // A time with no day is the one combination that cannot mean anything.
  if (draft.dueTime.length > 0 && draft.dueDate.length === 0) {
    errors.dueDate = DATE_INVALID;
  }
  return errors;
}

export function taskDueAt(draft: TaskDraft): string | null {
  if (draft.dueDate.length === 0) return null;
  return instantFrom(draft.dueDate, draft.dueTime);
}

// --- reminders --------------------------------------------------------------

export interface ReminderDraft {
  title: string;
  time: string;
  recurrence: ReminderRecurrence;
  weekdays: number[];
  dayOfMonth: string;
}

export function validateReminder(draft: ReminderDraft): Errors {
  const errors: Errors = {};
  if (draft.title.trim().length === 0) errors.title = TITLE_REQUIRED;
  if (draft.time.length === 0) errors.time = TIME_REQUIRED;
  else if (!TIME_PATTERN.test(draft.time)) errors.time = TIME_INVALID;

  if (draft.recurrence === 'selected_days' || draft.recurrence === 'weekly') {
    if (draft.weekdays.length === 0) errors.weekdays = DAYS_REQUIRED;
    else if (draft.recurrence === 'weekly' && draft.weekdays.length > 1) {
      errors.weekdays = 'A weekly reminder is on one day.';
    }
  }

  if (draft.recurrence === 'monthly') {
    const day = Number(draft.dayOfMonth);
    if (!Number.isInteger(day) || day < 1 || day > 31) {
      errors.dayOfMonth = DAY_OF_MONTH_REQUIRED;
    }
  }
  return errors;
}

// --- alarms -----------------------------------------------------------------

export interface AlarmDraft {
  label: string;
  time: string;
  recurrence: AlarmRecurrence;
  weekdays: number[];
}

export function validateAlarm(draft: AlarmDraft): Errors {
  const errors: Errors = {};
  if (draft.label.trim().length === 0) errors.label = TITLE_REQUIRED;
  if (draft.time.length === 0) errors.time = TIME_REQUIRED;
  else if (!TIME_PATTERN.test(draft.time)) errors.time = TIME_INVALID;
  if (draft.recurrence === 'selected_days' && draft.weekdays.length === 0) {
    errors.weekdays = DAYS_REQUIRED;
  }
  return errors;
}

// --- routines ---------------------------------------------------------------

export interface RoutineDraft {
  title: string;
  time: string;
  scheduleType: RoutineScheduleType;
  weekdays: number[];
  steps: RoutineStepInput[];
}

/** The steps with blanks dropped and titles trimmed, in their given order. */
export function usableSteps(steps: RoutineStepInput[]): RoutineStepInput[] {
  return steps
    .map((step) => ({ ...step, title: step.title.trim() }))
    .filter((step) => step.title.length > 0);
}

export function validateRoutine(draft: RoutineDraft): Errors {
  const errors: Errors = {};
  if (draft.title.trim().length === 0) errors.title = TITLE_REQUIRED;
  if (draft.time.length === 0) errors.time = TIME_REQUIRED;
  else if (!TIME_PATTERN.test(draft.time)) errors.time = TIME_INVALID;
  if (draft.scheduleType === 'selected_days' && draft.weekdays.length === 0) {
    errors.weekdays = DAYS_REQUIRED;
  }
  if (usableSteps(draft.steps).length === 0) errors.steps = STEPS_REQUIRED;
  return errors;
}

/**
 * Moves a step one place, or returns the list unchanged at either end.
 *
 * Here rather than in the screen because it is the whole of section 48's
 * "Move Up / Move Down", and an off-by-one in it would silently reorder
 * somebody's morning.
 */
export function moveStep<T>(steps: T[], index: number, by: -1 | 1): T[] {
  const target = index + by;
  if (target < 0 || target >= steps.length) return steps;
  const next = [...steps];
  const moved = next[index];
  const other = next[target];
  if (moved === undefined || other === undefined) return steps;
  next[index] = other;
  next[target] = moved;
  return next;
}

/** Whether any field failed. */
export function hasErrors(errors: Errors): boolean {
  return Object.keys(errors).length > 0;
}
