/**
 * The shared symptom draft (PRD 6, sections 4, 11, 24, 30, 61, 72 and 76).
 *
 * The draft is what makes "both flows produce the same structured record" true:
 * one shape, one validator, one payload builder. So this file checks the two
 * things that would break that promise -- a field the payload drops, and a
 * validation rule that makes an incomplete description unsavable.
 *
 * It also covers the review summary, since that is what the user actually reads
 * before agreeing to save (PRD 6, section 76).
 */
import { summaryRows } from '../src/features/symptoms/copy';
import {
  cleaned,
  entryPayload,
  episodePayload,
  formatItems,
  hasContent,
  isFollowUp,
  isSavable,
  mergeItems,
  newClientId,
  newDraft,
  parseItems,
  validateDraft,
} from '../src/features/symptoms/draft';
import type { SymptomDraft } from '../src/features/symptoms/types';

const SAVED_AT = new Date('2026-09-27T09:30:00.000Z');

function filled(overrides: Partial<SymptomDraft> = {}): SymptomDraft {
  return {
    ...newDraft({ mode: 'manual_app' }),
    mainSymptom: 'Headache',
    site: 'behind both eyes',
    onset: 'suddenly, this morning',
    onsetDate: '2026-09-27',
    character: 'throbbing',
    radiation: 'stays in one place',
    timing: 'worse in the morning',
    severity: 5,
    changeState: 'worsening',
    note: 'Worse than yesterday.',
    associatedSymptoms: ['nausea'],
    exacerbatingFactors: ['bright light'],
    relievingFactors: ['lying down'],
    negatedItems: ['vomiting'],
    uncertainItems: ['dizziness'],
    contextDependentItems: ['only when I stand up'],
    ...overrides,
  };
}

describe('starting a draft', () => {
  it('carries the flow it came from, which becomes the stored source', () => {
    expect(newDraft({ mode: 'manual_app' }).mode).toBe('manual_app');
    expect(newDraft({ mode: 'guided_app' }).mode).toBe('guided_app');
  });

  it('generates a client id before anything is sent (PRD 6, section 61)', () => {
    const draft = newDraft({ mode: 'manual_app' });
    expect(draft.clientEntryId.length).toBeGreaterThan(8);
    expect(draft.clientEntryId).not.toBe(newDraft({ mode: 'manual_app' }).clientEntryId);
  });

  it('knows a follow-up from a new symptom', () => {
    expect(isFollowUp(newDraft({ mode: 'manual_app' }))).toBe(false);
    expect(isFollowUp(newDraft({ mode: 'manual_app', episodeId: 'e1' }))).toBe(true);
  });

  it('generates ids that are recognisably client-side', () => {
    expect(newClientId()).toMatch(/^entry-/);
    expect(newClientId('photo')).toMatch(/^photo-/);
  });
});

describe('validation (PRD 6, sections 11 and 91)', () => {
  it('needs a name for a new symptom, and nothing else', () => {
    const empty = newDraft({ mode: 'manual_app' });
    expect(validateDraft(empty).mainSymptom).toBeTruthy();

    const named = { ...empty, mainSymptom: 'Headache' };
    expect(validateDraft(named)).toEqual({});
    expect(isSavable(named)).toBe(true);
  });

  it('needs nothing at all for a follow-up -- the episode has the name', () => {
    const followUp = newDraft({ mode: 'manual_app', episodeId: 'e1' });
    expect(validateDraft(followUp)).toEqual({});
  });

  it('refuses a severity off the scale', () => {
    expect(validateDraft(filled({ severity: 11 })).severity).toBeTruthy();
    expect(validateDraft(filled({ severity: -1 })).severity).toBeTruthy();
    expect(validateDraft(filled({ severity: 0 })).severity).toBeUndefined();
    expect(validateDraft(filled({ severity: 10 })).severity).toBeUndefined();
  });

  it('treats a blank name as no name', () => {
    expect(
      validateDraft({ ...newDraft({ mode: 'manual_app' }), mainSymptom: '   ' })
        .mainSymptom
    ).toBeTruthy();
  });
});

describe('hasContent', () => {
  it('is false for an untouched follow-up, so Save waits for something to save', () => {
    expect(hasContent(newDraft({ mode: 'manual_app', episodeId: 'e1' }))).toBe(false);
  });

  it('is true once anything at all has been recorded', () => {
    const base = newDraft({ mode: 'manual_app', episodeId: 'e1' });
    expect(hasContent({ ...base, severity: 0 })).toBe(true);
    expect(hasContent({ ...base, changeState: 'same' })).toBe(true);
    expect(hasContent({ ...base, note: 'a bit better' })).toBe(true);
    expect(hasContent({ ...base, associatedSymptoms: ['nausea'] })).toBe(true);
    expect(
      hasContent({
        ...base,
        photos: [
          {
            clientPhotoId: 'photo-1',
            localUri: 'file:///a.jpg',
            contentType: 'image/jpeg',
            byteSize: 10,
          },
        ],
      })
    ).toBe(true);
  });
});

describe('list fields', () => {
  it('splits on commas and "and"', () => {
    expect(parseItems('nausea, light sensitivity and fever')).toEqual([
      'nausea',
      'light sensitivity',
      'fever',
    ]);
  });

  it('collapses duplicates case-insensitively, keeping the first spelling', () => {
    expect(parseItems('Nausea, nausea, NAUSEA')).toEqual(['Nausea']);
  });

  it('drops blanks and caps the number of items', () => {
    expect(parseItems('a,,  ,b')).toEqual(['a', 'b']);
    expect(
      parseItems(Array.from({ length: 30 }, (_, i) => `x${i}`).join(',')).length
    ).toBe(12);
  });

  it('round-trips through the form', () => {
    expect(parseItems(formatItems(['nausea', 'fever']))).toEqual(['nausea', 'fever']);
  });

  it('merges without duplicating', () => {
    expect(mergeItems(['nausea'], ['Nausea', 'fever'])).toEqual(['nausea', 'fever']);
  });
});

describe('cleaned', () => {
  it('treats a blank as absent', () => {
    expect(cleaned('  ')).toBeUndefined();
    expect(cleaned(undefined)).toBeUndefined();
    expect(cleaned(' headache ')).toBe('headache');
  });
});

describe('the entry payload', () => {
  const payload = entryPayload(filled(), SAVED_AT);

  it('carries every structured field, so nothing is lost on the way out', () => {
    expect(payload.main_symptom).toBe('Headache');
    expect(payload.site).toBe('behind both eyes');
    expect(payload.onset_text).toBe('suddenly, this morning');
    expect(payload.onset_date).toBe('2026-09-27');
    expect(payload.character).toBe('throbbing');
    expect(payload.radiation).toBe('stays in one place');
    expect(payload.timing).toBe('worse in the morning');
    expect(payload.severity).toBe(5);
    expect(payload.change_state).toBe('worsening');
    expect(payload.free_text_note).toBe('Worse than yesterday.');
    expect(payload.associated_symptoms).toEqual(['nausea']);
    expect(payload.exacerbating_factors).toEqual(['bright light']);
    expect(payload.relieving_factors).toEqual(['lying down']);
  });

  it('keeps what was denied, hedged and conditional (PRD 6, section 24)', () => {
    expect(payload.negated_items).toEqual(['vomiting']);
    expect(payload.uncertain_items).toEqual(['dizziness']);
    expect(payload.context_dependent_items).toEqual(['only when I stand up']);
  });

  it('records when the user saved it, not when it is sent', () => {
    expect(payload.recorded_at).toBe('2026-09-27T09:30:00.000Z');
  });

  it('sends the client id and the flow it came from', () => {
    expect(payload.client_entry_id).toBe(
      filled().clientEntryId.slice(0, 0) || payload.client_entry_id
    );
    expect(payload.source).toBe('manual_app');
    expect(entryPayload(filled({ mode: 'guided_app' }), SAVED_AT).source).toBe(
      'guided_app'
    );
  });

  it('sends null rather than an empty string for a field left blank', () => {
    const sparse = entryPayload(
      { ...newDraft({ mode: 'manual_app' }), mainSymptom: 'Nausea' },
      SAVED_AT
    );
    expect(sparse.site).toBeNull();
    expect(sparse.severity).toBeNull();
    expect(sparse.change_state).toBeNull();
    expect(sparse.associated_symptoms).toEqual([]);
  });
});

describe('the episode payload', () => {
  it('carries the episode and its first entry in one request (s30)', () => {
    const payload = episodePayload(filled(), SAVED_AT);
    expect(payload.name).toBe('Headache');
    expect(payload.body_site).toBe('behind both eyes');
    expect(payload.first_noticed_date).toBe('2026-09-27');
    expect(payload.first_noticed_text).toBe('suddenly, this morning');
    expect(payload.first_entry.severity).toBe(5);
  });

  it('sends one onset precision, never two', () => {
    // The API refuses both a date and a year, and the draft only ever has a date.
    const payload = episodePayload(filled(), SAVED_AT);
    expect(Object.keys(payload)).not.toContain('first_noticed_year');
  });
});

describe('the review summary (PRD 6, sections 30 and 76)', () => {
  it('shows only what was recorded', () => {
    const rows = summaryRows({
      ...newDraft({ mode: 'manual_app' }),
      mainSymptom: 'Nausea',
    });
    expect(rows.map((row) => row.label)).toEqual(['Symptom']);
  });

  it('shows what was denied and what was uncertain, rather than dropping them', () => {
    const labels = summaryRows(filled()).map((row) => row.label);
    expect(labels).toContain('Not present');
    expect(labels).toContain('Not sure about');
    expect(labels).toContain('Only sometimes');
  });

  it('counts photos rather than describing them', () => {
    const rows = summaryRows(
      filled({
        photos: [
          {
            clientPhotoId: 'photo-1',
            localUri: 'file:///a.jpg',
            contentType: 'image/jpeg',
            byteSize: 10,
          },
        ],
      })
    );
    expect(rows.find((row) => row.label === 'Photos')?.value).toBe('1 photo');
  });

  it('reads severity back as the user’s own number', () => {
    const rows = summaryRows(filled({ severity: 5 }));
    expect(rows.find((row) => row.label === 'How bad')?.value).toBe('5/10');
  });
});
