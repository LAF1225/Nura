/**
 * What the daily-life forms check (PRD 12, sections 5, 7, 10, 35, 48 and 68).
 *
 * Section 68 asks for reminder-form and alarm-form validation; this is where
 * both live, because the rules are pure functions rather than something buried
 * in a component. That is deliberate: a controlled `TextInput` cannot be
 * driven from a test in this stack, so a form whose rules lived inside it
 * would be a form whose rules were untested.
 *
 * Two things these tests are really about.
 *
 * **Nothing is guessed.** A missing time is an error, not nine o'clock; a
 * missing day is an error, not today. The one default in the module is named
 * and is for a *task* given a day and no time, which has to land somewhere.
 *
 * **A date that matches the pattern is not necessarily a day.** 2026-02-30
 * passes a regex and is not a date, and a form that accepted it would send an
 * instant nobody chose.
 */
import {
  DEFAULT_DUE_TIME,
  hasErrors,
  instantFrom,
  isValidDate,
  moveStep,
  taskDueAt,
  usableSteps,
  validateAlarm,
  validateReminder,
  validateRoutine,
  validateTask,
} from '../src/features/productivity/validation';

describe('dates', () => {
  it('accepts a real day', () => {
    expect(isValidDate('2026-09-13')).toBe(true);
    expect(isValidDate('2028-02-29')).toBe(true);
  });

  it('refuses a day that does not exist', () => {
    // Matches the pattern, is not a date. A form that accepted it would send
    // an instant nobody chose.
    expect(isValidDate('2026-02-30')).toBe(false);
    expect(isValidDate('2026-13-01')).toBe(false);
    expect(isValidDate('2027-02-29')).toBe(false);
  });

  it('refuses anything that is not a date at all', () => {
    for (const value of ['', 'tomorrow', '13/09/2026', '2026-9-13']) {
      expect(isValidDate(value)).toBe(false);
    }
  });
});

describe('instants', () => {
  it('builds one from a local date and time', () => {
    const instant = instantFrom('2026-09-13', '16:00');
    expect(instant).not.toBeNull();
    // Built in the phone's own zone, so the parts round-trip locally rather
    // than being reinterpreted as UTC.
    const local = new Date(instant as string);
    expect(local.getHours()).toBe(16);
    expect(local.getDate()).toBe(13);
  });

  it('falls back to the one named default when no time was given', () => {
    const instant = instantFrom('2026-09-13');
    expect(new Date(instant as string).getHours()).toBe(
      Number(DEFAULT_DUE_TIME.split(':')[0])
    );
  });

  it('returns null for a date that is not one', () => {
    expect(instantFrom('2026-02-30', '16:00')).toBeNull();
    expect(instantFrom('nonsense')).toBeNull();
  });
});

describe('tasks (section 5)', () => {
  const draft = { title: 'Call the chemist', dueDate: '', dueTime: '' };

  it('needs only a title', () => {
    expect(validateTask(draft)).toEqual({});
    expect(taskDueAt(draft)).toBeNull();
  });

  it('refuses a blank title', () => {
    expect(validateTask({ ...draft, title: '   ' }).title).toBeTruthy();
  });

  it('accepts a due date with no time', () => {
    const dated = { ...draft, dueDate: '2026-09-13' };
    expect(validateTask(dated)).toEqual({});
    expect(taskDueAt(dated)).not.toBeNull();
  });

  it('refuses a time with no day', () => {
    // The one combination that cannot mean anything.
    expect(validateTask({ ...draft, dueTime: '16:00' }).dueDate).toBeTruthy();
  });

  it('refuses a malformed date or time', () => {
    expect(validateTask({ ...draft, dueDate: '13-09-2026' }).dueDate).toBeTruthy();
    expect(
      validateTask({ ...draft, dueDate: '2026-09-13', dueTime: '25:00' }).dueTime
    ).toBeTruthy();
  });
});

describe('reminders (section 7)', () => {
  const draft = {
    title: 'Ring the bank',
    time: '18:00',
    recurrence: 'one_time' as const,
    weekdays: [] as number[],
    dayOfMonth: '',
  };

  it('accepts a one-off with a title and a time', () => {
    expect(validateReminder(draft)).toEqual({});
  });

  it('**refuses a reminder with no time**', () => {
    // Section 22's clarification rule, as a form: a reminder with no time is
    // not a reminder, and nothing guesses one.
    expect(validateReminder({ ...draft, time: '' }).time).toBe('Choose a time.');
  });

  it('refuses a malformed time', () => {
    expect(validateReminder({ ...draft, time: 'half four' }).time).toBeTruthy();
    expect(validateReminder({ ...draft, time: '7:30' }).time).toBeTruthy();
  });

  it('needs days for a chosen-days repeat', () => {
    const chosen = { ...draft, recurrence: 'selected_days' as const };
    expect(validateReminder(chosen).weekdays).toBeTruthy();
    expect(validateReminder({ ...chosen, weekdays: [0, 2] })).toEqual({});
  });

  it('allows exactly one day for a weekly repeat', () => {
    const weekly = { ...draft, recurrence: 'weekly' as const };
    expect(validateReminder({ ...weekly, weekdays: [0] })).toEqual({});
    expect(validateReminder({ ...weekly, weekdays: [0, 3] }).weekdays).toBeTruthy();
    expect(validateReminder(weekly).weekdays).toBeTruthy();
  });

  it('needs a day of the month for a monthly repeat', () => {
    const monthly = { ...draft, recurrence: 'monthly' as const };
    expect(validateReminder(monthly).dayOfMonth).toBeTruthy();
    expect(validateReminder({ ...monthly, dayOfMonth: '0' }).dayOfMonth).toBeTruthy();
    expect(validateReminder({ ...monthly, dayOfMonth: '32' }).dayOfMonth).toBeTruthy();
    // 31 is allowed: section 35's answer is that a short month uses its last
    // day, decided on the server, and the form says so beside the field.
    expect(validateReminder({ ...monthly, dayOfMonth: '31' })).toEqual({});
  });
});

describe('alarms (section 10)', () => {
  const draft = {
    label: 'Wake up',
    time: '07:00',
    recurrence: 'daily' as const,
    weekdays: [] as number[],
  };

  it('accepts a daily alarm', () => {
    expect(validateAlarm(draft)).toEqual({});
  });

  it('needs a label and a time', () => {
    expect(validateAlarm({ ...draft, label: ' ' }).label).toBeTruthy();
    expect(validateAlarm({ ...draft, time: '' }).time).toBeTruthy();
  });

  it('needs days for a chosen-days alarm', () => {
    const chosen = { ...draft, recurrence: 'selected_days' as const };
    expect(validateAlarm(chosen).weekdays).toBeTruthy();
    expect(validateAlarm({ ...chosen, weekdays: [0, 1, 2, 3, 4] })).toEqual({});
  });
});

describe('routines (sections 12, 13)', () => {
  const draft = {
    title: 'Morning routine',
    time: '07:30',
    scheduleType: 'daily' as const,
    weekdays: [] as number[],
    steps: [{ title: 'Drink water' }, { title: 'Stretch' }],
  };

  it('accepts a routine with steps', () => {
    expect(validateRoutine(draft)).toEqual({});
  });

  it('needs at least one step', () => {
    expect(validateRoutine({ ...draft, steps: [] }).steps).toBeTruthy();
    // A row somebody left blank is not a step.
    expect(validateRoutine({ ...draft, steps: [{ title: '  ' }] }).steps).toBeTruthy();
  });

  it('drops blank rows and trims the rest', () => {
    expect(
      usableSteps([{ title: '  Drink water ' }, { title: '' }, { title: 'Stretch' }])
    ).toEqual([{ title: 'Drink water' }, { title: 'Stretch' }]);
  });

  it('keeps the optional flag', () => {
    expect(usableSteps([{ title: 'Walk', optional: true }])).toEqual([
      { title: 'Walk', optional: true },
    ]);
  });

  it('needs days for a chosen-days routine', () => {
    const chosen = { ...draft, scheduleType: 'selected_days' as const };
    expect(validateRoutine(chosen).weekdays).toBeTruthy();
  });
});

describe('reordering (section 48)', () => {
  it('moves a step one place', () => {
    expect(moveStep(['a', 'b', 'c'], 1, -1)).toEqual(['b', 'a', 'c']);
    expect(moveStep(['a', 'b', 'c'], 1, 1)).toEqual(['a', 'c', 'b']);
  });

  it('does nothing at either end', () => {
    const steps = ['a', 'b', 'c'];
    expect(moveStep(steps, 0, -1)).toBe(steps);
    expect(moveStep(steps, 2, 1)).toBe(steps);
  });

  it('leaves the list the same length', () => {
    for (let index = 0; index < 3; index += 1) {
      expect(moveStep(['a', 'b', 'c'], index, 1)).toHaveLength(3);
      expect(moveStep(['a', 'b', 'c'], index, -1)).toHaveLength(3);
    }
  });
});

describe('hasErrors', () => {
  it('is false for nothing wrong', () => {
    expect(hasErrors({})).toBe(false);
    expect(hasErrors({ title: 'x' })).toBe(true);
  });
});
