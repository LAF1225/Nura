/**
 * The daily-life copy (PRD 12, sections 6, 9, 11, 18, 42 and 48).
 *
 * Wording tests, which in this codebase means tests about claims. Four of
 * them matter more than the rest.
 *
 * **The alarm note never says an alarm works.** Section 11 asks for honest
 * labelling, and the honest position is further back than that: the app has
 * never been run on a physical phone.
 *
 * **Nothing about a task is urgent.** Section 18 keeps daily life below
 * anything safety-critical, so no sentence here warns, alerts or hurries.
 *
 * **Every state is in a label, not only in a colour** (section 48). A done
 * task and a skipped step read as done and skipped to a screen reader.
 *
 * **The caregiver note says where the edge is** (section 42).
 */
import {
  ALARM_FORM_NOTE,
  CAPABILITY_STATE_LABELS,
  CAREGIVER_ROUTINES_ONLY,
  EXTERNAL_NOTE,
  MONTH_END_NOTE,
  NOTIFICATIONS_BLOCKED,
  PENDING_BADGE,
  PRIORITY_LABELS,
  alarmCountSentence,
  reminderCountSentence,
  routineCountSentence,
  stepAccessibilityLabel,
  taskAccessibilityLabel,
  taskCountSentence,
  weekdaySentence,
  DAYS_REQUIRED,
  STEPS_REQUIRED,
  TIME_INVALID,
  TIME_REQUIRED,
  TITLE_REQUIRED,
} from '../src/features/productivity/copy';

describe('the alarm note', () => {
  it('says an alarm is a notification and has never been tested', () => {
    expect(ALARM_FORM_NOTE).toContain('phone notifications');
    expect(ALARM_FORM_NOTE).toContain('never been tested on a physical phone');
  });

  it('never claims an alarm will wake anybody', () => {
    for (const claim of ['will wake', 'reliable', 'guaranteed', 'like your clock']) {
      expect(ALARM_FORM_NOTE.toLowerCase()).not.toContain(claim);
    }
  });
});

describe('the notification note', () => {
  it('says the reminder is still saved (section 9)', () => {
    expect(NOTIFICATIONS_BLOCKED).toContain('still saved');
    expect(NOTIFICATIONS_BLOCKED).toContain('Today screen');
  });
});

describe('what nothing says', () => {
  const sentences = [
    ALARM_FORM_NOTE,
    EXTERNAL_NOTE,
    MONTH_END_NOTE,
    NOTIFICATIONS_BLOCKED,
    PENDING_BADGE,
    CAREGIVER_ROUTINES_ONLY,
    taskCountSentence(3, 1),
    routineCountSentence(2),
    reminderCountSentence(2),
    alarmCountSentence(1),
  ];

  it('never hurries anybody', () => {
    for (const sentence of sentences) {
      for (const word of ['urgent', 'immediately', 'warning', 'alert', 'failed']) {
        expect(sentence.toLowerCase()).not.toContain(word);
      }
    }
  });

  it('never praises or scolds', () => {
    for (const sentence of sentences) {
      for (const word of ['well done', 'great', 'streak', 'behind', 'should have']) {
        expect(sentence.toLowerCase()).not.toContain(word);
      }
    }
  });

  it('never says anything medical', () => {
    for (const sentence of sentences) {
      for (const word of ['dose', 'medication', 'symptom', 'diagnos']) {
        expect(sentence.toLowerCase()).not.toContain(word);
      }
    }
  });
});

describe('counts', () => {
  it('states an overdue task without warning about it', () => {
    expect(taskCountSentence(3, 1)).toBe('3 tasks, 1 past its due time');
    expect(taskCountSentence(1, 0)).toBe('1 task');
    expect(taskCountSentence(0, 0)).toBe('Nothing on your list.');
  });

  it('counts routines, reminders and alarms in words', () => {
    expect(routineCountSentence(1)).toBe('1 routine');
    expect(routineCountSentence(3)).toBe('3 routines');
    expect(reminderCountSentence(0)).toBe('No reminders set up.');
    expect(alarmCountSentence(2)).toBe('2 alarms');
  });
});

describe('weekdays', () => {
  it('reads as days, never as numbers', () => {
    expect(weekdaySentence([0])).toBe('Mon');
    expect(weekdaySentence([0, 4])).toBe('Mon and Fri');
    expect(weekdaySentence([0, 2, 4])).toBe('Mon, Wed and Fri');
  });

  it('calls seven days every day', () => {
    expect(weekdaySentence([0, 1, 2, 3, 4, 5, 6])).toBe('Every day');
    expect(weekdaySentence(null)).toBe('Every day');
    expect(weekdaySentence([])).toBe('Every day');
  });
});

describe('accessible labels (section 48)', () => {
  it('announces a task state rather than relying on a colour', () => {
    expect(taskAccessibilityLabel('Call the chemist', false, false)).toBe(
      'Call the chemist. Not done.'
    );
    expect(taskAccessibilityLabel('Call the chemist', true, false)).toBe(
      'Call the chemist. Done.'
    );
    expect(taskAccessibilityLabel('Call the chemist', false, true)).toBe(
      'Call the chemist. Past its due time.'
    );
  });

  it('announces a step state, including skipped', () => {
    expect(stepAccessibilityLabel('Stretch', null)).toBe('Stretch. Not done yet.');
    expect(stepAccessibilityLabel('Stretch', 'completed')).toBe('Stretch. Done.');
    expect(stepAccessibilityLabel('Stretch', 'skipped')).toBe('Stretch. Skipped.');
  });

  it('describes a priority without implying an alert', () => {
    expect(PRIORITY_LABELS.important).toBe('Important');
    expect(PRIORITY_LABELS.normal).toBe('Normal');
  });
});

describe('capability labels', () => {
  it('says "not set up in this build" rather than "unavailable"', () => {
    // The distinction section 25 draws: nothing is broken, the integration
    // does not exist.
    expect(CAPABILITY_STATE_LABELS.not_configured).toBe('Not set up in this build');
    expect(CAPABILITY_STATE_LABELS.available).toBe('Available');
  });

  it('says Nura cannot look anything up', () => {
    expect(EXTERNAL_NOTE).toContain('cannot look anything up on the internet');
    expect(EXTERNAL_NOTE).toContain('any calendar outside Nura');
  });
});

describe('the caregiver note (section 42)', () => {
  it('names what stays private', () => {
    expect(CAREGIVER_ROUTINES_ONLY).toContain('Tasks');
    expect(CAREGIVER_ROUTINES_ONLY).toContain('alarms');
    expect(CAREGIVER_ROUTINES_ONLY).toContain('stay private');
  });
});

describe('validation wording', () => {
  it('says what is wrong in plain words', () => {
    // Asserted here rather than in a screen test: React 19 with this testing
    // library does not flush a component's own `useState` update from a
    // `fireEvent`, so a rendered error message is not observable there.
    expect(TITLE_REQUIRED).toBe('Give this a title.');
    expect(TIME_REQUIRED).toBe('Choose a time.');
    expect(TIME_INVALID).toContain('24-hour time');
    expect(DAYS_REQUIRED).toBe('Choose at least one day.');
    expect(STEPS_REQUIRED).toContain('at least one step');
  });

  it('never blames anybody', () => {
    for (const sentence of [TITLE_REQUIRED, TIME_REQUIRED, DAYS_REQUIRED]) {
      expect(sentence.toLowerCase()).not.toContain('you must');
      expect(sentence.toLowerCase()).not.toContain('error');
      expect(sentence.toLowerCase()).not.toContain('invalid');
    }
  });
});

describe('the month-end note (section 35)', () => {
  it('says what happens in February rather than leaving it to be found out', () => {
    expect(MONTH_END_NOTE).toContain('last day');
    expect(MONTH_END_NOTE).toContain('February');
  });
});
