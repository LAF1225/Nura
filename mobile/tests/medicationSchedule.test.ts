/**
 * What a reminder schedule may be, and what it sends (PRD 5, sections 9-11).
 *
 * This is the half of the schedule form worth testing properly: what it
 * refuses, what it actually puts on the wire, and how a pattern reads back to
 * the person who built it. Typing into the fields is not tested -- see the
 * note in README section 11 -- but nothing below depends on rendering.
 */
import {
  buildSchedulePayload,
  describeEnd,
  describeSchedule,
  formatTimeOfDay,
  initialScheduleValues,
  isScheduleValid,
  MAX_TIMES,
  validateSchedule,
  valuesFromSchedule,
  type ScheduleFormValues,
} from '../src/features/medications/schedule';
import type { MedicationSchedule } from '../src/features/medications/types';

const BASE: ScheduleFormValues = {
  scheduleType: 'daily',
  times: ['08:00'],
  weekdays: [],
  startDate: '2026-09-13',
  endDate: null,
  timezone: 'Europe/London',
};

function schedule(overrides: Partial<MedicationSchedule> = {}): MedicationSchedule {
  return {
    id: 'schedule-1',
    profileId: 'profile-1',
    medicationId: 'medication-1',
    medicationName: 'Metformin',
    medicationDose: '500 mg',
    scheduleType: 'daily',
    timezone: 'Europe/London',
    startDate: '2026-09-13',
    endDate: null,
    isActive: true,
    pausedAt: null,
    times: [{ id: 't1', timeOfDay: '08:00:00', weekday: null }],
    ...overrides,
  };
}

describe('formatTimeOfDay', () => {
  it('reads a 24-hour time back in words', () => {
    expect(formatTimeOfDay('08:00')).toBe('8:00 AM');
    expect(formatTimeOfDay('20:30')).toBe('8:30 PM');
    // The two that a naive `% 12` gets wrong.
    expect(formatTimeOfDay('00:15')).toBe('12:15 AM');
    expect(formatTimeOfDay('12:00')).toBe('12:00 PM');
  });

  it('leaves something it cannot parse alone rather than inventing a time', () => {
    expect(formatTimeOfDay('not a time')).toBe('not a time');
  });
});

describe('validation', () => {
  it('accepts the values a new schedule starts with', () => {
    expect(isScheduleValid(initialScheduleValues('Europe/London', '2026-09-13'))).toBe(
      true
    );
  });

  it('needs at least one time', () => {
    expect(validateSchedule({ ...BASE, times: [] }).times).toBe('Add at least one time.');
  });

  it('refuses a time that is not a time', () => {
    expect(validateSchedule({ ...BASE, times: ['25:00'] }).times).toBeDefined();
    expect(validateSchedule({ ...BASE, times: ['8am'] }).times).toBeDefined();
  });

  it('refuses the same time twice', () => {
    const errors = validateSchedule({ ...BASE, times: ['08:00', '08:00'] });
    expect(errors.times).toBe('That time is already on this schedule.');
  });

  it('refuses more times than the server will store', () => {
    const times = Array.from(
      { length: MAX_TIMES + 1 },
      (_, index) => `${String(index).padStart(2, '0')}:00`
    );
    expect(validateSchedule({ ...BASE, times }).times).toBeDefined();
  });

  it('needs at least one weekday on a selected-days schedule', () => {
    const errors = validateSchedule({ ...BASE, scheduleType: 'specific_days' });
    expect(errors.weekdays).toBe('Choose which days this should repeat on.');
    expect(
      validateSchedule({ ...BASE, scheduleType: 'specific_days', weekdays: [0] }).weekdays
    ).toBeUndefined();
  });

  it('refuses an end date before the start', () => {
    expect(validateSchedule({ ...BASE, endDate: '2026-09-12' }).endDate).toBe(
      'The end date is before the start date.'
    );
    // The same day is fine: a one-day course is a real thing.
    expect(validateSchedule({ ...BASE, endDate: '2026-09-13' }).endDate).toBeUndefined();
  });

  it('treats a blank end date as no end date', () => {
    expect(isScheduleValid({ ...BASE, endDate: '' })).toBe(true);
    expect(buildSchedulePayload('medication-1', { ...BASE, endDate: '' }).endDate).toBe(
      null
    );
  });
});

describe('buildSchedulePayload', () => {
  it('sends an every-day schedule with no weekdays at all', () => {
    const payload = buildSchedulePayload('medication-1', {
      ...BASE,
      times: ['20:00', '08:00'],
    });

    expect(payload.scheduleType).toBe('daily');
    // Sorted, so the stored order matches the order the form shows.
    expect(payload.times).toEqual([
      { timeOfDay: '08:00:00', weekday: null },
      { timeOfDay: '20:00:00', weekday: null },
    ]);
  });

  it('expands selected days into one row per day per time', () => {
    const payload = buildSchedulePayload('medication-1', {
      ...BASE,
      scheduleType: 'specific_days',
      weekdays: [4, 0, 2],
      times: ['09:00'],
    });

    // "9am on Mon, Wed and Fri" is how people say it; three rows is how the
    // database stores it (PRD 5, section 8).
    expect(payload.times).toEqual([
      { timeOfDay: '09:00:00', weekday: 0 },
      { timeOfDay: '09:00:00', weekday: 2 },
      { timeOfDay: '09:00:00', weekday: 4 },
    ]);
  });

  it('carries the time zone the schedule was made in', () => {
    expect(buildSchedulePayload('medication-1', BASE).timezone).toBe('Europe/London');
  });

  it('never invents a medication to attach to', () => {
    expect(buildSchedulePayload('medication-7', BASE).medicationId).toBe('medication-7');
  });
});

describe('round trip', () => {
  it('reads a stored schedule back into the form it came from', () => {
    const stored = schedule({
      scheduleType: 'specific_days',
      times: [
        { id: 'a', timeOfDay: '09:00:00', weekday: 0 },
        { id: 'b', timeOfDay: '09:00:00', weekday: 2 },
        { id: 'c', timeOfDay: '09:00:00', weekday: 4 },
      ],
    });

    const values = valuesFromSchedule(stored);
    expect(values.times).toEqual(['09:00']);
    expect(values.weekdays).toEqual([0, 2, 4]);

    // And building from those values produces what was stored.
    expect(buildSchedulePayload('medication-1', values).times).toEqual([
      { timeOfDay: '09:00:00', weekday: 0 },
      { timeOfDay: '09:00:00', weekday: 2 },
      { timeOfDay: '09:00:00', weekday: 4 },
    ]);
  });
});

describe('describeSchedule', () => {
  it('reads an every-day schedule as a sentence', () => {
    expect(describeSchedule(schedule())).toBe('Every day at 8:00 AM');
    expect(
      describeSchedule(
        schedule({
          times: [
            { timeOfDay: '08:00:00', weekday: null },
            { timeOfDay: '14:00:00', weekday: null },
            { timeOfDay: '20:00:00', weekday: null },
          ],
        })
      )
    ).toBe('Every day at 8:00 AM, 2:00 PM and 8:00 PM');
  });

  it('names the days of a selected-days schedule', () => {
    expect(
      describeSchedule(
        schedule({
          scheduleType: 'specific_days',
          times: [
            { timeOfDay: '09:00:00', weekday: 0 },
            { timeOfDay: '09:00:00', weekday: 2 },
            { timeOfDay: '09:00:00', weekday: 4 },
          ],
        })
      )
    ).toBe('Mon, Wed and Fri at 9:00 AM');
  });

  it('says nothing about an end date when there is not one', () => {
    expect(describeEnd(schedule())).toBeNull();
    expect(describeEnd(schedule({ endDate: '2026-10-14' }))).toContain('Until');
  });
});
