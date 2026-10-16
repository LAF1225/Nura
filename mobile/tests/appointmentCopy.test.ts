/**
 * Everything the appointment screens say (PRD 7, sections 3, 10, 18, 20 and 45).
 *
 * Two kinds of test here. The first checks the sentences read correctly -- plurals,
 * counts, the pieces that exist. The second is the one that matters: it reads
 * *every* string the module can produce and fails on a diagnosis, a likelihood, an
 * attributed cause, a treatment suggestion, a graded adherence figure, or an
 * emergency framing.
 *
 * The report's own sentences are not here: they are built by the backend and
 * frozen into the snapshot (PRD 7, section 30), and `backend/tests/test_reports.py`
 * holds the equivalent guard for them. What this covers is the wording of the
 * screens around the report.
 */
import * as copy from '../src/features/appointments/copy';
import type {
  AdherenceReview,
  CheckInReview,
  SymptomReview,
} from '../src/features/appointments/types';

function symptom(overrides: Partial<SymptomReview> = {}): SymptomReview {
  return {
    episodeId: 'episode-1',
    name: 'Headache',
    bodySite: null,
    status: 'active',
    isOngoing: true,
    entryCount: 6,
    firstNoticedLabel: '20 September 2026',
    latestSeverity: 6,
    severityMin: 3,
    severityMax: 6,
    latestChangeState: 'worsening',
    associatedSymptoms: [],
    exacerbatingFactors: [],
    relievingFactors: [],
    negatedItems: [],
    uncertainItems: [],
    contextDependentItems: [],
    notes: [],
    photoCount: 0,
    ...overrides,
  };
}

function adherence(overrides: Partial<AdherenceReview> = {}): AdherenceReview {
  return {
    fromDate: '2026-08-30',
    toDate: '2026-09-28',
    taken: 13,
    skipped: 1,
    missed: 0,
    total: 14,
    percent: 92,
    skipNotes: [],
    ...overrides,
  };
}

function checkins(overrides: Partial<CheckInReview> = {}): CheckInReview {
  return {
    good: 8,
    okay: 11,
    notGreat: 4,
    total: 23,
    daysInPeriod: 30,
    notes: [],
    ...overrides,
  };
}

describe('the sentences read correctly', () => {
  it('joins a clinician and a specialty, or whichever exists', () => {
    expect(copy.clinicianLine('Dr Ahmed Khan', 'Cardiology')).toBe(
      'Dr Ahmed Khan · Cardiology'
    );
    expect(copy.clinicianLine('Dr Ahmed Khan', null)).toBe('Dr Ahmed Khan');
    expect(copy.clinicianLine(null, 'Cardiology')).toBe('Cardiology');
    expect(copy.clinicianLine(null, null)).toBeNull();
  });

  it('counts appointments, questions and summaries without a bare number', () => {
    expect(copy.upcomingCountSentence(0)).toBe('No upcoming appointments.');
    expect(copy.upcomingCountSentence(1)).toBe('1 upcoming appointment');
    expect(copy.upcomingCountSentence(3)).toBe('3 upcoming appointments');

    expect(copy.questionCountSentence(0)).toBe('No questions added');
    expect(copy.questionCountSentence(1)).toBe('1 question added');
    expect(copy.questionCountSentence(3)).toBe('3 questions added');

    expect(copy.reportCountSentence(0)).toBe('No summary generated');
    expect(copy.reportCountSentence(1)).toBe('1 summary generated');
    expect(copy.reportCountSentence(2)).toBe('2 summaries generated');
  });

  it('names a report version with when it was made', () => {
    // PRD 7 section 31's own example metadata.
    expect(copy.reportVersionLine(2, '2 Oct 2026, 09:15')).toBe(
      'Report v2 · 2 Oct 2026, 09:15'
    );
  });

  it('says nothing about pages when the server did not say', () => {
    expect(copy.pageCountSentence(null)).toBeNull();
    expect(copy.pageCountSentence(0)).toBeNull();
    expect(copy.pageCountSentence(1)).toBe('1 page');
    expect(copy.pageCountSentence(2)).toBe('2 pages');
  });

  it('describes a symptom in counts and the user’s own answer', () => {
    expect(copy.symptomReviewLines(symptom())).toEqual([
      'Logged 6 times',
      'Latest severity: 6/10',
      'Change: worsening',
    ]);
  });

  it('says when an ongoing symptom has nothing in the period', () => {
    // Silence would read as "it stopped".
    expect(copy.symptomReviewLines(symptom({ entryCount: 0 }))[0]).toBe(
      'Still ongoing · no entries in this period'
    );
  });

  it('leaves out a severity nobody recorded', () => {
    const lines = copy.symptomReviewLines(
      symptom({ latestSeverity: null, latestChangeState: null })
    );
    expect(lines).toEqual(['Logged 6 times']);
  });

  it('states the dose counts with their denominator', () => {
    expect(copy.adherenceSentence(adherence())).toBe(
      '13 of 14 scheduled doses marked taken'
    );
    expect(copy.adherenceSentence(adherence({ total: 0, taken: 0, skipped: 0 }))).toBe(
      'No doses were scheduled in this period.'
    );
  });

  it('never puts a percentage on the review screen', () => {
    // PRD 7 section 18 prefers counts; the percentage lives in the report's own
    // appendix, with its period stated beside it.
    expect(copy.adherenceSentence(adherence())).not.toContain('%');
    expect(copy.adherenceSentence(adherence())).not.toContain('92');
  });

  it('counts skipped and unmarked doses separately', () => {
    expect(copy.skippedSentence(adherence())).toBe('1 dose skipped');
    expect(copy.skippedSentence(adherence({ skipped: 2, missed: 1 }))).toBe(
      '2 doses skipped · 1 dose not marked taken'
    );
    expect(copy.skippedSentence(adherence({ skipped: 0, missed: 0 }))).toBeNull();
  });

  it('gives the wellbeing counts PRD 7 section 20 asks for', () => {
    expect(copy.checkinSentence(checkins())).toBe(
      'Good: 8 days · Okay: 11 days · Not great: 4 days'
    );
    expect(copy.checkinSentence(checkins({ good: 1, okay: 0, notGreat: 0 }))).toBe(
      'Good: 1 day'
    );
    expect(copy.checkinSentence(checkins({ total: 0 }))).toBe(
      'No check-ins recorded in this period.'
    );
  });

  it('builds the Today subtitle from what exists', () => {
    expect(copy.todayCardSubtitle('Tomorrow at 3:30 PM', 'Dr Ahmed Khan')).toBe(
      'Tomorrow at 3:30 PM · Dr Ahmed Khan'
    );
    expect(copy.todayCardSubtitle('Tomorrow at 3:30 PM', null)).toBe(
      'Tomorrow at 3:30 PM'
    );
  });
});

/**
 * Every sentence the module can produce, collected once.
 *
 * The functions are called with values chosen to make each branch fire, so a
 * phrase added to any of them is included here without the test being changed.
 */
function everySentence(): string[] {
  const strings: string[] = [];

  for (const value of Object.values(copy)) {
    if (typeof value === 'string') strings.push(value);
    if (Array.isArray(value)) {
      strings.push(
        ...value.filter((entry): entry is string => typeof entry === 'string')
      );
    }
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      strings.push(
        ...Object.values(value).filter(
          (entry): entry is string => typeof entry === 'string'
        )
      );
    }
  }

  strings.push(
    copy.clinicianLine('Dr Ahmed Khan', 'Cardiology') ?? '',
    copy.upcomingCountSentence(0),
    copy.upcomingCountSentence(1),
    copy.upcomingCountSentence(4),
    copy.questionCountSentence(0),
    copy.questionCountSentence(1),
    copy.questionCountSentence(4),
    copy.reportCountSentence(0),
    copy.reportCountSentence(1),
    copy.reportCountSentence(4),
    copy.reportVersionLine(2, '2 Oct 2026, 09:15'),
    copy.pageCountSentence(1) ?? '',
    copy.pageCountSentence(2) ?? '',
    ...copy.symptomReviewLines(symptom()),
    ...copy.symptomReviewLines(
      symptom({ entryCount: 0, latestChangeState: 'improving' })
    ),
    ...copy.symptomReviewLines(symptom({ entryCount: 1, latestChangeState: 'same' })),
    ...copy.symptomReviewLines(symptom({ latestChangeState: 'unsure' })),
    copy.adherenceSentence(adherence()),
    copy.adherenceSentence(adherence({ total: 0, taken: 0, skipped: 0 })),
    copy.skippedSentence(adherence({ skipped: 2, missed: 1 })) ?? '',
    copy.checkinSentence(checkins()),
    copy.checkinSentence(checkins({ total: 0 })),
    copy.todayCardSubtitle('Tomorrow at 3:30 PM', 'Dr Ahmed Khan')
  );

  return strings.filter((entry) => entry.length > 0);
}

describe('no wording implies a diagnosis, a cause or a judgement', () => {
  const FORBIDDEN = [
    // Diagnosis and likelihood (PRD 7, section 45).
    'diagnos',
    'likely',
    'probably',
    'probable',
    'you may have',
    'you have a',
    'suggests',
    'consistent with',
    'impression',
    // Cause (sections 3 and 45).
    'caused by',
    'is causing',
    'because of your',
    'side effect',
    // Treatment (sections 3 and 45).
    'you should take',
    'you should stop',
    'we recommend',
    'recommended dose',
    // Graded adherence (section 18) and interpreted wellbeing (section 20).
    'poor adherence',
    'good adherence',
    'well controlled',
    'getting worse overall',
    'deteriorat',
    // Emergency framing (section 10).
    'urgent',
    'emergency',
    'immediately',
    'call 999',
    'call 911',
  ];

  it.each(FORBIDDEN)('never says %s', (phrase) => {
    for (const sentence of everySentence()) {
      expect(sentence.toLowerCase()).not.toContain(phrase);
    }
  });

  it('collects a real number of sentences, so the guard is not vacuous', () => {
    expect(everySentence().length).toBeGreaterThan(60);
  });

  it('says plainly that a summary is not shared until it is exported', () => {
    expect(copy.PREPARE_INTRO).toContain('Nothing is shared until you export it');
  });

  it('says a regeneration keeps the earlier versions', () => {
    // PRD 7 section 31's promise, in the user's own words.
    expect(copy.REGENERATE_HINT).toContain('Earlier versions are kept');
  });

  it('says deleting a report leaves the health records alone', () => {
    expect(copy.DELETE_REPORT_CONFIRM).toContain('health records are not affected');
  });

  it('does not pretend a report can be made offline', () => {
    expect(copy.OFFLINE_REPORT).toContain('needs a connection');
    expect(copy.OFFLINE_REPORT).toContain('selections are saved');
  });
});
