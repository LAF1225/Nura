/**
 * How a dose reads on screen (PRD 5, sections 19, 24, 27, 34 and 57).
 *
 * Most of this file is about *wording*, which is unusual for a test suite and
 * deliberate here. PRD 5 asks for neutral, non-judgemental copy and forbids
 * anything that could be read as medical advice; those are requirements, so
 * they are asserted rather than left to whoever edits the strings next.
 */
import {
  adherenceSentence,
  doseStatusLine,
  doseTitle,
  dueAt,
  groupByDay,
  isWaiting,
  lowSupplySentence,
  MISSED_DOSE_GUIDANCE,
  skipReasonLabel,
  SKIP_REASONS,
  SNOOZE_OPTIONS,
  windowLabel,
} from '../src/features/medications/doses';
import type { MedicationDose } from '../src/features/medications/types';

function dose(overrides: Partial<MedicationDose> = {}): MedicationDose {
  return {
    id: 'dose-1',
    medicationId: 'medication-1',
    medicationName: 'Metformin',
    medicationDose: '500 mg',
    scheduleId: 'schedule-1',
    scheduledFor: '2026-09-13T08:00:00Z',
    localDate: '2026-09-13',
    status: 'scheduled',
    window: 'due',
    actionAt: null,
    source: null,
    skipReasonCode: null,
    skipReasonText: null,
    snoozedUntil: null,
    snoozeCount: 0,
    late: false,
    canSnooze: true,
    ...overrides,
  };
}

describe('doseTitle', () => {
  it('names the medication and its dose', () => {
    expect(doseTitle(dose())).toBe('Metformin — 500 mg');
  });

  it('leaves out a dose nobody recorded rather than showing an empty dash', () => {
    expect(doseTitle(dose({ medicationDose: null }))).toBe('Metformin');
  });
});

describe('doseStatusLine', () => {
  it('states an unrecorded dose without scolding about it', () => {
    const line = doseStatusLine(dose({ status: 'missed' }));
    expect(line).toBe('Wasn’t marked as taken');
    // PRD 5, section 24: no guilt-oriented wording anywhere near a missed dose.
    expect(line.toLowerCase()).not.toMatch(/missed|failed|forgot|should/);
  });

  it('shows a skip reason back exactly as it was chosen', () => {
    expect(
      doseStatusLine(dose({ status: 'skipped', skipReasonCode: 'feeling_unwell' }))
    ).toBe('Skipped — feeling unwell');
    expect(doseStatusLine(dose({ status: 'skipped', skipReasonCode: 'none' }))).toBe(
      'Skipped'
    );
  });

  it('says when a late dose was actually taken, and nothing more', () => {
    const line = doseStatusLine(
      dose({ status: 'taken', late: true, actionAt: '2026-09-13T11:30:00Z' })
    );
    expect(line).toMatch(/^Taken at /);
    expect(line.toLowerCase()).not.toContain('late');
  });

  it('says what a snoozed dose is now waiting for', () => {
    const snoozed = dose({ status: 'snoozed', snoozedUntil: '2026-09-13T08:30:00Z' });
    expect(doseStatusLine(snoozed)).toMatch(/^Snoozed until /);
    expect(dueAt(snoozed)).toBe('2026-09-13T08:30:00Z');
    // Still unrecorded: a snooze is not an answer (PRD 5, section 18).
    expect(isWaiting(snoozed)).toBe(true);
  });
});

describe('windowLabel', () => {
  it('describes an overdue dose as unrecorded rather than as an alert', () => {
    expect(windowLabel('overdue')).toBe('Not marked as taken');
    expect(windowLabel('due')).toBe('Due now');
    expect(windowLabel('upcoming')).toBe('Coming up');
    // A recorded dose needs no window phrase at all.
    expect(windowLabel('completed')).toBeNull();
  });
});

describe('the skip reasons', () => {
  it('offers the codes the backend accepts, and no others', () => {
    expect(SKIP_REASONS.map((reason) => reason.code).sort()).toEqual([
      'clinician_advised',
      'feeling_unwell',
      'none',
      'other',
      'ran_out',
      'too_late',
    ]);
  });

  it('treats "no reason" as no reason rather than as a label', () => {
    expect(skipReasonLabel('none')).toBeNull();
    expect(skipReasonLabel(null)).toBeNull();
    expect(skipReasonLabel('ran_out')).toBe('Ran out');
  });
});

describe('the snooze durations', () => {
  it('offers exactly what the server accepts (PRD 5, section 18)', () => {
    // Mirrors `SNOOZE_OPTIONS_MINUTES` in app/services/medications/doses.py.
    // Offering a duration the server refuses would be a button that fails.
    expect(SNOOZE_OPTIONS.map((option) => option.minutes)).toEqual([10, 30, 60]);
  });
});

describe('adherenceSentence', () => {
  it('states the window and never grades the number', () => {
    const sentence = adherenceSentence(
      {
        fromDate: '2026-09-07',
        toDate: '2026-09-13',
        taken: 6,
        skipped: 1,
        missed: 0,
        total: 7,
        percent: 86,
      },
      7
    );
    expect(sentence).toBe('86% of scheduled doses were marked taken in the last 7 days.');
    // PRD 5, section 27: not labelled adequate or inadequate.
    expect(sentence.toLowerCase()).not.toMatch(/good|poor|bad|target|should|adequate/);
  });

  it('says nothing was scheduled rather than showing 0%', () => {
    const sentence = adherenceSentence(
      {
        fromDate: '2026-09-07',
        toDate: '2026-09-13',
        taken: 0,
        skipped: 0,
        missed: 0,
        total: 0,
        percent: null,
      },
      7
    );
    expect(sentence).toBe('No doses were scheduled in the last 7 days.');
    expect(sentence).not.toContain('0%');
  });
});

describe('lowSupplySentence', () => {
  it('is cautious, because the count came from the user', () => {
    expect(lowSupplySentence('Metformin', 5)).toBe(
      'You have about 5 doses of Metformin left.'
    );
    expect(lowSupplySentence('Metformin', 1)).toBe(
      'You have about 1 dose of Metformin left.'
    );
  });
});

describe('the one piece of guidance', () => {
  it('points at a clinician and gives no advice of its own', () => {
    // PRD 5, section 57 permits exactly this shape of sentence and no more.
    expect(MISSED_DOSE_GUIDANCE).toContain('clinician or pharmacist');
    expect(MISSED_DOSE_GUIDANCE.toLowerCase()).not.toMatch(
      /take another|double|skip it|stop taking|wait until/
    );
  });
});

describe('groupByDay', () => {
  it('groups history by the user’s own day, newest day first', () => {
    const grouped = groupByDay([
      dose({ id: 'a', localDate: '2026-09-12', scheduledFor: '2026-09-12T20:00:00Z' }),
      dose({ id: 'b', localDate: '2026-09-13', scheduledFor: '2026-09-13T20:00:00Z' }),
      dose({ id: 'c', localDate: '2026-09-13', scheduledFor: '2026-09-13T08:00:00Z' }),
    ]);

    expect(grouped.map((day) => day.localDate)).toEqual(['2026-09-13', '2026-09-12']);
    // Within a day, earliest first: that is the order the day happened in.
    expect(grouped[0]!.doses.map((entry) => entry.id)).toEqual(['c', 'b']);
  });

  it('returns nothing for nothing', () => {
    expect(groupByDay([])).toEqual([]);
  });
});
