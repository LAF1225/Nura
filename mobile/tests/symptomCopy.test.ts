/**
 * What the symptom screens say (PRD 6, sections 3, 22, 23, 42, 45, 66 and 81).
 *
 * Testing wording is unusual, and deliberate here for the same reason it is in
 * the medication suite: PRD 6 asks for specific things about tone and forbids
 * others outright, and a rule nobody asserts is a rule the next person to edit a
 * string will break without noticing.
 *
 * The strongest of these is the medical safety boundary. Every sentence Nura may
 * say back about a symptom lives in `safetyMessages.ts`, so all of it can be
 * checked at once for a named condition, a likelihood or an attribution of cause.
 */
import {
  CHANGE_MARKER,
  CHANGE_STATES,
  changeLabel,
  entryLine,
  episodeSubtitle,
  episodeTitle,
  formatDay,
  isActiveStatus,
  onsetSentence,
  SEVERITY_ANCHOR_HIGH,
  SEVERITY_ANCHOR_LOW,
  severityAccessibilityLabel,
  severityLabel,
  STATUS_LABEL,
  summarySentence,
} from '../src/features/symptoms/copy';
import * as safety from '../src/features/symptoms/safetyMessages';
import type { SymptomEntry, SymptomEpisode } from '../src/features/symptoms/types';

function entry(overrides: Partial<SymptomEntry> = {}): SymptomEntry {
  return {
    id: 'entry-1',
    episodeId: 'episode-1',
    recordedAt: '2026-09-27T14:30:00Z',
    mainSymptom: 'headache',
    site: 'behind both eyes',
    onsetText: null,
    onsetAt: null,
    onsetDate: null,
    character: 'throbbing',
    radiation: null,
    timing: null,
    severity: 6,
    changeState: 'worsening',
    freeTextNote: null,
    associatedSymptoms: ['nausea'],
    exacerbatingFactors: [],
    relievingFactors: [],
    negatedItems: [],
    uncertainItems: [],
    contextDependentItems: [],
    source: 'manual_app',
    photos: [],
    createdAt: '2026-09-27T14:30:00Z',
    ...overrides,
  };
}

function episode(overrides: Partial<SymptomEpisode> = {}): SymptomEpisode {
  return {
    id: 'episode-1',
    profileId: 'profile-1',
    name: 'Headache',
    bodySite: 'behind both eyes',
    status: 'active',
    firstNoticedAt: null,
    firstNoticedDate: '2026-09-25',
    firstNoticedYear: null,
    firstNoticedText: 'suddenly',
    resolvedAt: null,
    previousEpisodeId: null,
    source: 'manual_app',
    entryCount: 1,
    latestEntry: entry(),
    safety: { worsening: false, reasons: [], notice: null, urgent: false },
    createdAt: '2026-09-25T09:00:00Z',
    updatedAt: '2026-09-27T14:30:00Z',
    ...overrides,
  };
}

describe('the medical safety boundary (PRD 6, section 81)', () => {
  /**
   * The phrases a user must never read from Nura about their own symptoms: a
   * named condition, a likelihood, an attribution of cause, or an instruction
   * about medication.
   *
   * "You have recorded this as worsening" is allowed and is the reviewed
   * wording, because it states what the *user* did rather than what is wrong
   * with them.
   */
  const FORBIDDEN = [
    'migraine',
    'appendicitis',
    'pneumonia',
    'infection',
    'diagnos',
    'probably',
    'likely',
    'sounds like',
    'you have a',
    'you have an',
    'you may have',
    'stop taking',
    'caused by',
  ];

  const sentences = Object.entries(safety).filter(
    (pair): pair is [string, string] => typeof pair[1] === 'string'
  );

  it('has wording to check', () => {
    expect(sentences.length).toBeGreaterThan(4);
  });

  it.each(sentences)('%s says nothing diagnostic', (_name, sentence) => {
    const lowered = sentence.toLowerCase();
    for (const phrase of FORBIDDEN) {
      expect(lowered).not.toContain(phrase);
    }
  });

  it('points at a person rather than giving advice', () => {
    expect(safety.WORSENING_NOTICE).toContain('healthcare professional');
    expect(safety.NOT_ADVICE).toContain('does not work out what is causing it');
  });

  it('says plainly that photos are not looked at (PRD 6, section 32)', () => {
    expect(safety.PHOTO_NOTICE).toContain('does not look at them');
  });

  it('asks about a concerning statement rather than asserting it (s46)', () => {
    const prompt = safety.confirmationPrompt('severe chest pain');
    expect(prompt).toContain('Just to confirm');
    expect(prompt).toContain('severe chest pain');
    expect(prompt.endsWith('?')).toBe(true);
  });
});

describe('severity (PRD 6, section 22)', () => {
  it('is anchored at both ends', () => {
    expect(SEVERITY_ANCHOR_LOW).toContain('0');
    expect(SEVERITY_ANCHOR_LOW).toContain('no symptom');
    expect(SEVERITY_ANCHOR_HIGH).toContain('10');
  });

  it('never labels a number', () => {
    // "moderate" would be Nura's judgement of the user's own number.
    for (let value = 0; value <= 10; value += 1) {
      expect(severityLabel(value)).toBe(`${value}/10`);
    }
    for (const word of ['mild', 'moderate', 'severe', 'bad', 'serious']) {
      expect(SEVERITY_ANCHOR_LOW.toLowerCase()).not.toContain(word);
      expect(SEVERITY_ANCHOR_HIGH.toLowerCase()).not.toContain(word);
    }
  });

  it('is absent rather than zero when no number was given', () => {
    expect(severityLabel(null)).toBeNull();
    expect(severityLabel(undefined)).toBeNull();
  });

  it('reads every point aloud sensibly', () => {
    expect(severityAccessibilityLabel(0)).toContain('no symptom');
    expect(severityAccessibilityLabel(5)).toBe('5 out of 10');
    expect(severityAccessibilityLabel(10)).toContain('worst');
  });
});

describe('change state (PRD 6, sections 23 and 66)', () => {
  it('offers "not sure" as an equal option', () => {
    expect(CHANGE_STATES.map((option) => option.value)).toEqual([
      'improving',
      'same',
      'worsening',
      'unsure',
    ]);
    expect(changeLabel('unsure')).toBe('Not sure');
  });

  it('has a non-colour marker for each state', () => {
    for (const option of CHANGE_STATES) {
      expect(CHANGE_MARKER[option.value].length).toBeGreaterThan(0);
    }
    // Direction is distinguishable without colour.
    expect(CHANGE_MARKER.improving).not.toBe(CHANGE_MARKER.worsening);
  });

  it('never scolds or congratulates', () => {
    for (const option of CHANGE_STATES) {
      const label = option.label.toLowerCase();
      for (const word of ['well done', 'unfortunately', 'sadly', 'good', 'bad']) {
        expect(label).not.toContain(word);
      }
    }
  });
});

describe('statuses', () => {
  it('describes what the user did, not an outcome', () => {
    // Nura has no idea whether anything was cured.
    expect(STATUS_LABEL.resolved).toBe('Ended');
    expect(STATUS_LABEL.resolved.toLowerCase()).not.toContain('cured');
    expect(STATUS_LABEL.resolved.toLowerCase()).not.toContain('better');
  });

  it('counts a recurrence as active', () => {
    expect(isActiveStatus('active')).toBe(true);
    expect(isActiveStatus('recurring')).toBe(true);
    expect(isActiveStatus('resolved')).toBe(false);
    expect(isActiveStatus('historical')).toBe(false);
  });
});

describe('summarising an episode', () => {
  it('titles it with the user’s own number', () => {
    expect(episodeTitle('Headache', 6)).toBe('Headache — 6/10');
    expect(episodeTitle('Fatigue', null)).toBe('Fatigue');
  });

  it('says when it was last written about', () => {
    expect(episodeSubtitle(episode(), '2026-09-27')).toContain('Last logged today');
    // The day is locale-formatted, so either order is correct.
    expect(episodeSubtitle(episode(), '2026-09-28')).toMatch(/27 September|September 27/);
  });

  it('says so plainly when nothing has been logged about it yet', () => {
    expect(episodeSubtitle(episode({ latestEntry: null }), '2026-09-27')).toBe(
      'Nothing logged about it yet'
    );
  });

  it('keeps both halves of the onset (PRD 6, section 74)', () => {
    const sentence = onsetSentence(episode());
    expect(sentence).toContain('suddenly');
    expect(sentence).toMatch(/25 September|September 25/);
  });

  it('reads a year-only onset back as a year (PRD 6, section 15)', () => {
    const sentence = onsetSentence(
      episode({ firstNoticedDate: null, firstNoticedText: null, firstNoticedYear: 2019 })
    );
    expect(sentence).toBe('Started 2019');
  });

  it('says nothing when the onset is unknown', () => {
    expect(
      onsetSentence(
        episode({
          firstNoticedDate: null,
          firstNoticedText: null,
          firstNoticedYear: null,
        })
      )
    ).toBeNull();
  });

  it('builds a history line the way PRD 6 section 36 lays it out', () => {
    const line = entryLine(entry());
    expect(line).toMatch(/27 September|September 27/);
    expect(line).toContain('6/10');
    expect(line).toContain('Getting worse');
  });

  it('counts active symptoms without mixing in anything else', () => {
    expect(summarySentence(1, 0)).toBe('1 active symptom');
    expect(summarySentence(2, 1)).toBe('2 active symptoms · 1 recorded as worsening');
  });
});

describe('formatDay', () => {
  it('reads a plain date and an instant the same way', () => {
    expect(formatDay('2026-09-27')).toContain('27');
    expect(formatDay('2026-09-27T14:30:00Z')).toContain('27');
  });

  it('hands back anything it cannot parse rather than showing "Invalid Date"', () => {
    expect(formatDay('not a date')).toBe('not a date');
  });
});
