/**
 * The schedule form, and how a schedule reads in a sentence
 * (PRD 5, sections 9, 11 and 36).
 *
 * All of this is pure: values in, values out, no hooks and no requests. That
 * is deliberate. What a form *means* -- what it refuses, what it actually
 * sends, how a pattern reads back to the user -- is the part worth testing
 * thoroughly, and it is testable on its own.
 *
 * Only two patterns exist, because PRD 5 section 9 asks for only two: every
 * day, or on chosen weekdays. Several times a day is not a third pattern, it
 * is several times on one of these; a date range is a start and an end on
 * either. Tapering, sliding scales and every-N-hours are out of scope
 * (section 10), and there is nowhere here to express them.
 */
import type { MedicationSchedule, ScheduleType, SchedulePayload, Weekday } from './types';

/** Monday first, matching the backend's 0 = Monday. */
export const WEEKDAYS: { value: Weekday; label: string; short: string }[] = [
  { value: 0, label: 'Monday', short: 'Mon' },
  { value: 1, label: 'Tuesday', short: 'Tue' },
  { value: 2, label: 'Wednesday', short: 'Wed' },
  { value: 3, label: 'Thursday', short: 'Thu' },
  { value: 4, label: 'Friday', short: 'Fri' },
  { value: 5, label: 'Saturday', short: 'Sat' },
  { value: 6, label: 'Sunday', short: 'Sun' },
];

/** Mirrors `MAX_TIMES_PER_SCHEDULE` on the server. */
export const MAX_TIMES = 12;

/** Offered as a starting point, so most people never type a time at all. */
export const SUGGESTED_TIMES = ['08:00', '12:00', '18:00', '22:00'];

export interface ScheduleFormValues {
  scheduleType: ScheduleType;
  /** `HH:MM`, in the schedule's own zone. */
  times: string[];
  /** Only used when `scheduleType` is `specific_days`. */
  weekdays: Weekday[];
  startDate: string;
  endDate: string | null;
  timezone: string;
}

const TIME_PATTERN = /^([01][0-9]|2[0-3]):([0-5][0-9])$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/**
 * "8:00 AM". Written out rather than delegated to `toLocaleTimeString`, which
 * returns a different string on every platform and locale and would make the
 * schedule sentence untestable. The app is English-only for now; a translation
 * pass replaces this function rather than working around it.
 */
export function formatTimeOfDay(value: string): string {
  const match = TIME_PATTERN.exec(value.slice(0, 5));
  if (match === null) return value;
  const hours = Number(match[1]);
  const minutes = match[2];
  const suffix = hours < 12 ? 'AM' : 'PM';
  const displayHour = hours % 12 === 0 ? 12 : hours % 12;
  return `${displayHour}:${minutes} ${suffix}`;
}

/** `HH:MM` from the `HH:MM:SS` the API returns. */
export function toFormTime(value: string): string {
  return value.slice(0, 5);
}

/** The values a brand-new schedule starts with. */
export function initialScheduleValues(
  timezone: string,
  today: string
): ScheduleFormValues {
  return {
    scheduleType: 'daily',
    times: ['08:00'],
    weekdays: [],
    startDate: today,
    endDate: null,
    timezone,
  };
}

/** An existing schedule, as the form holds it. */
export function valuesFromSchedule(schedule: MedicationSchedule): ScheduleFormValues {
  const times = Array.from(
    new Set(schedule.times.map((entry) => toFormTime(entry.timeOfDay)))
  ).sort();
  const weekdays = Array.from(
    new Set(
      schedule.times
        .map((entry) => entry.weekday)
        .filter((day): day is number => day !== null)
    )
  ).sort() as Weekday[];

  return {
    scheduleType: schedule.scheduleType,
    times: times.length > 0 ? times : ['08:00'],
    weekdays,
    startDate: schedule.startDate,
    endDate: schedule.endDate,
    timezone: schedule.timezone,
  };
}

export interface ScheduleErrors {
  times?: string;
  weekdays?: string;
  startDate?: string;
  endDate?: string;
}

/**
 * What is wrong with these values, in the user's words.
 *
 * Mirrors the server's rules rather than replacing them: the backend refuses
 * the same things, and this exists so somebody hears about it before they
 * press Save rather than after (PRD 5, section 75).
 */
export function validateSchedule(values: ScheduleFormValues): ScheduleErrors {
  const errors: ScheduleErrors = {};

  if (values.times.length === 0) {
    errors.times = 'Add at least one time.';
  } else if (values.times.some((entry) => !TIME_PATTERN.test(entry))) {
    errors.times = 'Enter a time as HH:MM, for example 08:00.';
  } else if (new Set(values.times).size !== values.times.length) {
    errors.times = 'That time is already on this schedule.';
  } else if (values.times.length > MAX_TIMES) {
    errors.times = `A schedule can have at most ${MAX_TIMES} times.`;
  }

  if (values.scheduleType === 'specific_days' && values.weekdays.length === 0) {
    errors.weekdays = 'Choose which days this should repeat on.';
  }

  if (!DATE_PATTERN.test(values.startDate)) {
    errors.startDate = 'Enter a start date as YYYY-MM-DD.';
  }

  if (values.endDate !== null && values.endDate.length > 0) {
    if (!DATE_PATTERN.test(values.endDate)) {
      errors.endDate = 'Enter an end date as YYYY-MM-DD, or leave it blank.';
    } else if (values.endDate < values.startDate) {
      errors.endDate = 'The end date is before the start date.';
    }
  }

  return errors;
}

export function isScheduleValid(values: ScheduleFormValues): boolean {
  return Object.keys(validateSchedule(values)).length === 0;
}

/**
 * The request body for these values.
 *
 * An every-day schedule sends its times with no weekday; a specific-days one
 * sends every chosen time on every chosen day. The cross product is built
 * here rather than asked of the user, because "9am on Mon, Wed and Fri" is how
 * people describe it and three rows is how the database stores it.
 */
export function buildSchedulePayload(
  medicationId: string,
  values: ScheduleFormValues
): SchedulePayload {
  const times = Array.from(new Set(values.times)).sort();
  const slots =
    values.scheduleType === 'daily'
      ? times.map((timeOfDay) => ({ timeOfDay: `${timeOfDay}:00`, weekday: null }))
      : Array.from(new Set(values.weekdays))
          .sort()
          .flatMap((weekday) =>
            times.map((timeOfDay) => ({ timeOfDay: `${timeOfDay}:00`, weekday }))
          );

  return {
    medicationId,
    scheduleType: values.scheduleType,
    timezone: values.timezone,
    startDate: values.startDate,
    endDate: values.endDate && values.endDate.length > 0 ? values.endDate : null,
    times: slots,
  };
}

/** "8:00 AM and 8:00 PM", "8:00 AM, 2:00 PM and 8:00 PM". */
function joinTimes(times: string[]): string {
  const formatted = times.map(formatTimeOfDay);
  if (formatted.length <= 1) return formatted[0] ?? '';
  const last = formatted[formatted.length - 1];
  return `${formatted.slice(0, -1).join(', ')} and ${last}`;
}

/** "Mon, Wed and Fri". */
function joinDays(weekdays: number[]): string {
  const labels = WEEKDAYS.filter((day) => weekdays.includes(day.value)).map(
    (day) => day.short
  );
  if (labels.length <= 1) return labels[0] ?? '';
  const last = labels[labels.length - 1];
  return `${labels.slice(0, -1).join(', ')} and ${last}`;
}

/**
 * A schedule in one sentence: "Every day at 8:00 AM and 8:00 PM".
 *
 * Used on the schedule list and above the form, so somebody can check what
 * they built without reading a table of rows back.
 */
export function describeSchedule(schedule: MedicationSchedule): string {
  const values = valuesFromSchedule(schedule);
  const times = joinTimes(values.times);

  if (schedule.scheduleType === 'specific_days') {
    const days = joinDays(values.weekdays);
    return days.length > 0 ? `${days} at ${times}` : `At ${times}`;
  }
  return `Every day at ${times}`;
}

/** "Until 14 October 2026", or null for an open-ended schedule. */
export function describeEnd(schedule: MedicationSchedule): string | null {
  if (schedule.endDate === null) return null;
  const parsed = new Date(`${schedule.endDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return `Until ${schedule.endDate}`;
  return `Until ${parsed.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  })}`;
}

/**
 * The phone's own IANA zone, for a new schedule.
 *
 * Falls back to UTC only if the platform cannot say, which would otherwise
 * mean a schedule with no zone at all -- and the server requires one, for
 * good reason (PRD 5, section 12).
 */
export function deviceTimezone(): string {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof zone === 'string' && zone.length > 0 ? zone : 'UTC';
  } catch {
    return 'UTC';
  }
}
