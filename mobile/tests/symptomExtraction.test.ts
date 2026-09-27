/**
 * Reading a symptom description out of a sentence (PRD 6, ss24, 27, 28 and 74).
 *
 * `extract` is a pure function, so the interesting behaviour is testable
 * directly -- which matters most for PRD 6 section 28's non-repetition rule: the
 * cheapest way to be sure a question is not asked twice is to assert that one
 * sentence filled the field.
 *
 * The negative assertions carry as much weight as the positive ones. A symptom
 * word inside "no nausea" must not become a symptom the person has, and a hedge
 * must not become a fact (PRD 6, section 24).
 */
import {
  extract,
  findOnset,
  findSeverity,
  findSite,
  isPainLike,
} from '../src/features/symptoms/conversation/extract';
import { RED_FLAG_TERMS } from '../src/features/symptoms/conversation/vocabulary';

const TODAY = '2026-09-27';

describe('the sentence PRD 6 section 28 uses as its example', () => {
  const message =
    'I have a sharp pain in my left knee that started yesterday and is 6/10';

  it('fills the symptom, the site, the character, the onset and the severity at once', () => {
    const found = extract(message, { today: TODAY });

    expect(found.mainSymptom).toBe('knee pain');
    expect(found.site).toBe('left knee');
    expect(found.character).toBe('sharp');
    expect(found.onset).toContain('yesterday');
    expect(found.onsetDate).toBe('2026-09-26');
    expect(found.severity).toBe(6);
  });
});

describe('naming the symptom', () => {
  it('uses a symptom the person named', () => {
    expect(extract('I have a headache', { today: TODAY }).mainSymptom).toBe('headache');
  });

  it('builds a name from a body part that hurts', () => {
    const found = extract('My head has been hurting since this morning', {
      today: TODAY,
    });
    expect(found.mainSymptom).toBe('head pain');
    expect(found.onset).toContain('this morning');
    expect(found.onsetDate).toBe(TODAY);
  });

  it('treats further symptom words as things alongside it', () => {
    const found = extract('I have a headache and nausea', { today: TODAY });
    expect(found.mainSymptom).toBe('headache');
    expect(found.associatedSymptoms).toContain('nausea');
  });

  it('does not overwrite a symptom that is already known', () => {
    const found = extract('it is nausea now', {
      today: TODAY,
      known: { mainSymptom: true },
    });
    expect(found.mainSymptom).toBeUndefined();
  });

  it('keeps an unrecognised answer verbatim for the question that was asked', () => {
    // PRD 6 section 75: nothing is dropped for not being in a vocabulary.
    const found = extract('a sort of wobbly feeling in my chest', {
      expecting: 'mainSymptom',
      today: TODAY,
    });
    expect(found.mainSymptom).toBe('a sort of wobbly feeling in my chest');
  });
});

describe('locations', () => {
  it('keeps a preposition that is part of the location', () => {
    expect(findSite('mostly behind my eyes')?.phrase).toBe('behind my eyes');
  });

  it('keeps which side, and drops a bare "my"', () => {
    expect(findSite('a pain in my left knee')?.phrase).toBe('left knee');
    expect(findSite('my knee hurts')?.phrase).toBe('knee');
  });

  it('handles a two-word part', () => {
    expect(findSite('my lower back is sore')?.phrase).toBe('lower back');
  });

  it('finds nothing where there is no body part', () => {
    expect(findSite('I feel exhausted')).toBeUndefined();
  });
});

describe('onset', () => {
  it('resolves a relative day', () => {
    expect(findOnset('it started yesterday', TODAY)?.date).toBe('2026-09-26');
    expect(findOnset('three days ago', TODAY)?.date).toBe('2026-09-24');
    expect(findOnset('2 weeks ago', TODAY)?.date).toBe('2026-09-13');
  });

  it('keeps how it began as well as when', () => {
    // PRD 6 section 74: both facts, not one.
    const found = findOnset('it started suddenly, about three days ago', TODAY);
    expect(found?.wording).toContain('suddenly');
    expect(found?.wording).toContain('three days ago');
    expect(found?.date).toBe('2026-09-24');
  });

  it('keeps wording that pins nothing down, and resolves no date', () => {
    const found = findOnset('it came on suddenly', TODAY);
    expect(found?.wording).toBe('suddenly');
    expect(found?.date).toBeUndefined();
  });

  it('keeps a trigger the person described', () => {
    expect(findOnset('it started after exercise', TODAY)?.wording).toContain('exercise');
  });
});

describe('severity', () => {
  it('reads a number on the scale wherever it appears', () => {
    expect(findSeverity('it is about 6/10')).toBe(6);
    expect(findSeverity('maybe 8 out of 10')).toBe(8);
    expect(findSeverity('10/10')).toBe(10);
  });

  it('reads a bare number only when severity was asked for', () => {
    // Otherwise "it started 3 days ago" becomes a severity of 3.
    expect(findSeverity('it started 3 days ago')).toBeUndefined();
    expect(findSeverity('about a 5', 'severity')).toBe(5);
    expect(findSeverity('three', 'severity')).toBe(3);
  });

  it('does not read a number out of an onset answer', () => {
    const found = extract('it started 3 days ago', { expecting: 'onset', today: TODAY });
    expect(found.severity).toBeUndefined();
    expect(found.onsetDate).toBe('2026-09-24');
  });
});

describe('negation, uncertainty and context (PRD 6, section 24)', () => {
  it('records a denied symptom as denied, not as present', () => {
    const found = extract('I have a headache but no nausea', { today: TODAY });
    expect(found.mainSymptom).toBe('headache');
    expect(found.negatedItems).toContain('nausea');
    expect(found.associatedSymptoms).not.toContain('nausea');
  });

  it('records a hedge as uncertain, not as present', () => {
    const found = extract('I might have felt dizzy', { today: TODAY });
    expect(found.uncertainItems.join(' ')).toContain('dizzy');
    expect(found.associatedSymptoms).not.toContain('dizzy');
    expect(found.mainSymptom).toBeUndefined();
  });

  it('does not read "not sure" as a denial', () => {
    const found = extract("I'm not sure if it spreads", { today: TODAY });
    expect(found.uncertainItems.length).toBeGreaterThan(0);
    expect(found.negatedItems).toEqual([]);
  });

  it('records something that is only true sometimes', () => {
    const found = extract('it hurts only when I stand up', { today: TODAY });
    expect(found.contextDependentItems.length).toBeGreaterThan(0);
  });
});

describe('the rest of the structured fields', () => {
  it('reads timing', () => {
    expect(extract('it comes and goes', { today: TODAY }).timing).toBe('comes and goes');
  });

  it('reads radiation both ways round', () => {
    expect(extract('it spreads to my back', { today: TODAY }).radiation).toBe('back');
    expect(extract('it stays in one place', { today: TODAY }).radiation).toBe(
      'stays in one place'
    );
  });

  it('reads what makes it worse and what helps', () => {
    const found = extract('it is worse when I walk and better with rest', {
      today: TODAY,
    });
    expect(found.exacerbatingFactors.join(' ')).toContain('walk');
    expect(found.relievingFactors.join(' ')).toContain('rest');
  });

  it('reads an explicit comparison as a change state', () => {
    expect(extract('it is getting worse', { today: TODAY }).changeState).toBe(
      'worsening'
    );
    expect(extract('it feels better than yesterday', { today: TODAY }).changeState).toBe(
      'improving'
    );
    expect(extract('about the same', { today: TODAY }).changeState).toBe('same');
  });

  it('does not read "worse at night" as a change state', () => {
    // That is when it is worse, not that it is worsening.
    const found = extract('it is worse at night', { today: TODAY });
    expect(found.changeState).toBeUndefined();
    expect(found.timing).toBe('worse at night');
  });
});

describe('concerning phrases (PRD 6, sections 44 and 46)', () => {
  it('notices a loose phrase and offers the canonical term for confirmation', () => {
    const found = extract("I can't catch my breath", { today: TODAY });
    expect(found.redFlags).toEqual(['severe difficulty breathing']);
    // Noticing is not concluding: nothing has been recorded as present.
    expect(found.associatedSymptoms).not.toContain('severe difficulty breathing');
  });

  it('does not raise one from a hedged statement', () => {
    const found = extract('I might have severe chest pain', { today: TODAY });
    expect(found.redFlags).toEqual([]);
  });

  it('does not raise one from a denial', () => {
    const found = extract('no severe chest pain', { today: TODAY });
    expect(found.redFlags).toEqual([]);
    expect(found.negatedItems.join(' ')).toContain('chest pain');
  });

  it('offers only terms a server rule could match', () => {
    // The canonical vocabulary is shared with
    // `backend/app/services/symptoms/safety.py`; a term this side that the
    // server does not know would confirm something no rule can see.
    const found = extract('I passed out this morning', { today: TODAY });
    for (const term of found.redFlags) {
      expect(RED_FLAG_TERMS).toContain(term);
    }
  });
});

describe('isPainLike', () => {
  it('is true for pain-shaped descriptions, so radiation is worth asking about', () => {
    expect(isPainLike('knee pain', undefined)).toBe(true);
    expect(isPainLike('headache', 'throbbing')).toBe(true);
  });

  it('is false for symptoms radiation makes no sense for (PRD 6, section 12)', () => {
    expect(isPainLike('nausea', undefined)).toBe(false);
    expect(isPainLike('fatigue', undefined)).toBe(false);
  });
});

describe('an empty message', () => {
  it('changes nothing', () => {
    const found = extract('   ', { expecting: 'mainSymptom', today: TODAY });
    expect(found.mainSymptom).toBeUndefined();
    expect(found.associatedSymptoms).toEqual([]);
  });
});
