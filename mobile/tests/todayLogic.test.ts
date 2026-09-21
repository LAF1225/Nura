/**
 * The small decisions Today makes before anything is rendered
 * (PRD 3, sections 8, 39, 40 and 64).
 *
 * Pure functions, so they can be checked at every boundary that matters --
 * midnight, 4:59am, a missing name -- without mounting a screen.
 */
import { checkInSentence, wellbeingLabel } from '../src/components/today/wellbeing';
import {
  greetingFor,
  greetingForHour,
  initialsFor,
  localDateString,
} from '../src/utils/date';

describe('greetingForHour', () => {
  it('uses the buckets PRD 3 section 40 specifies', () => {
    expect(greetingForHour(5)).toBe('Good morning');
    expect(greetingForHour(11)).toBe('Good morning');
    expect(greetingForHour(12)).toBe('Good afternoon');
    expect(greetingForHour(16)).toBe('Good afternoon');
    expect(greetingForHour(17)).toBe('Good evening');
    expect(greetingForHour(23)).toBe('Good evening');
  });

  it('treats the small hours as evening, not morning', () => {
    // Someone awake at 2am is still in their night. "Good morning" at that
    // hour reads as a machine that has not noticed.
    expect(greetingForHour(0)).toBe('Good evening');
    expect(greetingForHour(4)).toBe('Good evening');
  });
});

describe('greetingFor', () => {
  const morning = new Date(2026, 8, 21, 9, 0);

  it('uses the preferred name', () => {
    expect(greetingFor('Safdar', morning)).toBe('Good morning, Safdar');
  });

  it('falls back to the bare greeting when there is no name', () => {
    // Never an email address or a user id in its place (PRD 3, section 8).
    expect(greetingFor(null, morning)).toBe('Good morning');
    expect(greetingFor('   ', morning)).toBe('Good morning');
    expect(greetingFor(undefined, morning)).toBe('Good morning');
  });
});

describe('initialsFor', () => {
  it('takes at most two initials', () => {
    expect(initialsFor('Safdar')).toBe('S');
    expect(initialsFor('Safdar Ali')).toBe('SA');
    expect(initialsFor('Safdar Ali Khan')).toBe('SA');
  });

  it('is empty when there is no name, so no avatar is drawn', () => {
    expect(initialsFor(null)).toBe('');
    expect(initialsFor('  ')).toBe('');
  });
});

describe('localDateString', () => {
  it('reports the local calendar day, not the UTC one', () => {
    // 11pm on the 21st. In any time zone east of UTC this is the 22nd in UTC,
    // and sending that date would file the check-in under the wrong day --
    // the bug PRD 3 section 39 exists to prevent.
    const lateEvening = new Date(2026, 8, 21, 23, 30);
    expect(localDateString(lateEvening)).toBe('2026-09-21');
  });

  it('pads months and days', () => {
    expect(localDateString(new Date(2026, 0, 5, 12, 0))).toBe('2026-01-05');
  });
});

describe('check-in wording', () => {
  it('names the level the user chose', () => {
    expect(wellbeingLabel('good')).toBe('Good');
    expect(wellbeingLabel('okay')).toBe('Okay');
    expect(wellbeingLabel('not_great')).toBe('Not great');
  });

  it('says plainly when an answer is only saved on this phone', () => {
    expect(checkInSentence('okay', false)).toBe('You checked in as “Okay” today.');
    expect(checkInSentence('okay', true)).toContain('Saved on this phone');
  });

  it('never interprets the answer', () => {
    // PRD 3, section 45: "Not great" is acknowledged, never assessed.
    const sentence = checkInSentence('not_great', false).toLowerCase();
    for (const word of ['symptom', 'doctor', 'serious', 'condition', 'worse']) {
      expect(sentence).not.toContain(word);
    }
  });
});
