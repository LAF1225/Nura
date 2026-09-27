/**
 * The guided conversation (PRD 6, sections 26-29, 46, 67 and 91).
 *
 * The engine is pure, so a whole conversation can be driven in a test without
 * rendering anything. That is what makes PRD 6 section 28's **hard acceptance
 * criterion** -- do not ask again for a clearly volunteered field -- something
 * this file can assert directly rather than infer from a screenshot.
 *
 * Also asserted here: the flow does not force a field that makes no sense for the
 * symptom (section 12), a concerning phrase produces a *question* rather than a
 * conclusion (section 46), and the canonical phrase written after a confirmation
 * is one the server's rules can actually match.
 */
import {
  answer,
  applyExtraction,
  choose,
  CLOSING_LINE,
  finish,
  startConversation,
} from '../src/features/symptoms/conversation/engine';
import { extract } from '../src/features/symptoms/conversation/extract';
import {
  FIELD_ORDER,
  FOLLOW_UP_FIELDS,
  isCaptured,
  isRelevant,
  nextField,
  questionFor,
} from '../src/features/symptoms/conversation/questions';
import { RED_FLAG_TERMS } from '../src/features/symptoms/conversation/vocabulary';
import { newDraft } from '../src/features/symptoms/draft';
import { FIELD_LABELS } from '../src/features/symptoms/copy';
import type { ConversationState, SymptomDraft } from '../src/features/symptoms/types';

const TODAY = '2026-09-27';

function guided(episodeId?: string): SymptomDraft {
  return newDraft({ mode: 'guided_app', episodeId });
}

/** Everything Nura has said so far, as one lowercase string. */
function saidByNura(state: ConversationState): string {
  return state.turns
    .filter((turn) => turn.speaker === 'nura')
    .map((turn) => turn.text.toLowerCase())
    .join(' | ');
}

describe('starting a conversation', () => {
  it('opens by asking what is happening', () => {
    const state = startConversation(guided());

    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]?.speaker).toBe('nura');
    expect(state.turns[0]?.text).toBe(FIELD_LABELS.mainSymptom);
    expect(state.current?.field).toBe('mainSymptom');
  });

  it('opens a follow-up by asking how it is going', () => {
    const state = startConversation(guided('episode-1'), { episodeName: 'Headache' });

    expect(state.turns[0]?.text).toContain('headache');
    // A follow-up never re-asks for the description (PRD 6, section 47).
    expect(state.current?.field).not.toBe('mainSymptom');
    expect(FOLLOW_UP_FIELDS).toContain(state.current?.field);
  });
});

describe('the non-repetition rule (PRD 6, section 28)', () => {
  it('asks nothing again after one detailed first message', () => {
    let state = startConversation(guided());
    const result = answer(
      state,
      guided(),
      'I have a sharp pain in my left knee that started yesterday and is 6/10',
      { today: TODAY }
    );
    state = result.state;

    const asked = saidByNura(state);
    expect(asked).not.toContain('where do you feel it');
    expect(asked).not.toContain('when did it start');
    expect(asked).not.toContain('what does it feel like');
    expect(asked).not.toContain('how bad is it');

    // And the draft has all of it.
    expect(result.draft.mainSymptom).toBe('knee pain');
    expect(result.draft.site).toBe('left knee');
    expect(result.draft.character).toBe('sharp');
    expect(result.draft.severity).toBe(6);
    expect(result.draft.onsetDate).toBe('2026-09-26');
  });

  it('asks only what is still missing', () => {
    const state = startConversation(guided());
    const result = answer(state, guided(), 'a throbbing headache since this morning', {
      today: TODAY,
    });

    // The symptom, its character and when it started are all known, so the next
    // question is about something else.
    expect(result.state.current?.field).not.toBe('mainSymptom');
    expect(result.state.current?.field).not.toBe('character');
    expect(result.state.current?.field).not.toBe('onset');
  });

  it('never asks the same question twice, even when it was skipped', () => {
    let draft = guided();
    let state = startConversation(draft);

    // Answer the first, then skip everything offered after it.
    const first = answer(state, draft, 'a headache', { today: TODAY });
    state = first.state;
    draft = first.draft;

    const seen: string[] = [];
    for (let step = 0; step < FIELD_ORDER.length + 2; step += 1) {
      if (state.current === null) break;
      seen.push(state.current.field);
      const next = choose(state, draft, { label: 'Skip this' }, { today: TODAY });
      state = next.state;
      draft = next.draft;
    }

    expect(new Set(seen).size).toBe(seen.length);
    expect(state.finished).toBe(true);
    expect(saidByNura(state)).toContain(CLOSING_LINE.toLowerCase());
  });

  it('does not overwrite a field when a later answer repeats it', () => {
    let draft = guided();
    let state = startConversation(draft);
    const first = answer(state, draft, 'pain in my left knee', { today: TODAY });
    state = first.state;
    draft = first.draft;

    const second = answer(state, draft, 'about a 5, still the left knee', {
      today: TODAY,
    });
    expect(second.draft.site).toBe('left knee');
  });
});

describe('relevance (PRD 6, section 12)', () => {
  it('does not ask about radiation for a symptom that cannot radiate', () => {
    const draft = { ...guided(), mainSymptom: 'nausea' };
    expect(isRelevant(draft, 'radiation')).toBe(false);
    expect(nextField(draft, [])).not.toBe('radiation');
  });

  it('asks about radiation for a pain', () => {
    const draft = { ...guided(), mainSymptom: 'knee pain' };
    expect(isRelevant(draft, 'radiation')).toBe(true);
  });

  it('does not ask where a fever is, or what it feels like', () => {
    const draft = { ...guided(), mainSymptom: 'fever' };
    expect(isRelevant(draft, 'site')).toBe(false);
    expect(isRelevant(draft, 'character')).toBe(false);
  });

  it('counts onset as still missing when only *how* it began is known', () => {
    // PRD 6 section 74: "suddenly" is not a time, so the time is still asked.
    const draft = { ...guided(), onset: 'suddenly' };
    expect(isCaptured(draft, 'onset')).toBe(false);
    expect(questionFor('onset', draft).prompt).toBe('About when did it start?');
  });
});

describe('tapping instead of typing (PRD 6, section 67)', () => {
  it('every question offers choices and a way to skip', () => {
    const draft = guided();
    for (const field of FIELD_ORDER) {
      const question = questionFor(field, draft);
      expect(question.choices.length).toBeGreaterThan(0);
      expect(question.choices.some((choice) => choice.value === undefined)).toBe(true);
    }
  });

  it('a tapped severity lands in the draft', () => {
    const draft = { ...guided(), mainSymptom: 'headache' };
    const state: ConversationState = {
      turns: [],
      asked: ['severity'],
      current: questionFor('severity', draft),
      pendingConfirmation: null,
      finished: false,
    };

    const result = choose(state, draft, { label: '7', value: '7' }, { today: TODAY });
    expect(result.draft.severity).toBe(7);
  });

  it('a tapped relative day resolves to a date, exactly as typing it would', () => {
    const draft = { ...guided(), mainSymptom: 'headache' };
    const state: ConversationState = {
      turns: [],
      asked: ['onset'],
      current: questionFor('onset', draft),
      pendingConfirmation: null,
      finished: false,
    };

    const result = choose(
      state,
      draft,
      { label: 'Yesterday', value: 'yesterday' },
      { today: TODAY }
    );
    expect(result.draft.onsetDate).toBe('2026-09-26');
  });

  it('"nothing else" answers the question without recording anything', () => {
    const draft = { ...guided(), mainSymptom: 'headache' };
    const state: ConversationState = {
      turns: [],
      asked: ['associatedSymptoms'],
      current: questionFor('associatedSymptoms', draft),
      pendingConfirmation: null,
      finished: false,
    };

    const result = choose(state, draft, { label: 'Nothing else', value: '' });
    expect(result.draft.associatedSymptoms ?? []).toEqual([]);
    // Answered rather than left open, so it is not asked again.
    expect(result.state.asked).toContain('associatedSymptoms');
    expect(result.state.current?.field).not.toBe('associatedSymptoms');
  });
});

describe('checking a concerning statement (PRD 6, section 46)', () => {
  it('asks rather than concluding', () => {
    const draft = guided();
    const state = startConversation(draft);
    const result = answer(state, draft, "I can't catch my breath", { today: TODAY });

    expect(result.state.pendingConfirmation?.term).toBe('severe difficulty breathing');
    expect(saidByNura(result.state)).toContain('just to confirm');
    // Nothing has been recorded as present yet.
    expect(result.draft.associatedSymptoms ?? []).not.toContain(
      'severe difficulty breathing'
    );
  });

  it('records a yes as the canonical phrase a server rule can match', () => {
    const draft = guided();
    let state = startConversation(draft);
    const asked = answer(state, draft, "I can't catch my breath", { today: TODAY });
    state = asked.state;

    const confirmed = answer(state, asked.draft, 'yes', { today: TODAY });
    expect(confirmed.draft.associatedSymptoms).toContain('severe difficulty breathing');
    expect(RED_FLAG_TERMS).toContain('severe difficulty breathing');
    expect(confirmed.state.pendingConfirmation).toBeNull();
  });

  it('records a no as a denial rather than dropping it', () => {
    const draft = guided();
    const asked = answer(startConversation(draft), draft, 'I cannot breathe properly', {
      today: TODAY,
    });
    // Whichever canonical phrase Nura asked about is the one that gets stored,
    // so a rule on the server can see the answer either way.
    const term = asked.state.pendingConfirmation?.term ?? '';
    expect(RED_FLAG_TERMS).toContain(term);

    const denied = answer(asked.state, asked.draft, 'no, I can breathe fine', {
      today: TODAY,
    });
    expect(denied.draft.negatedItems).toContain(term);
    expect(denied.draft.associatedSymptoms ?? []).not.toContain(term);
  });

  it('leaves an unclear answer as unclear', () => {
    const draft = guided();
    const asked = answer(startConversation(draft), draft, 'I cannot breathe properly', {
      today: TODAY,
    });
    const term = asked.state.pendingConfirmation?.term ?? '';

    const unsure = answer(asked.state, asked.draft, 'I honestly could not say', {
      today: TODAY,
    });
    expect(unsure.draft.uncertainItems).toContain(term);
    expect(unsure.draft.associatedSymptoms ?? []).not.toContain(term);
  });

  it('does not ask about the same phrase twice', () => {
    const draft = guided();
    const asked = answer(startConversation(draft), draft, 'I cannot breathe properly', {
      today: TODAY,
    });
    const confirmed = answer(asked.state, asked.draft, 'yes', { today: TODAY });
    const again = answer(confirmed.state, confirmed.draft, 'I cannot breathe properly', {
      today: TODAY,
    });

    expect(again.state.pendingConfirmation).toBeNull();
  });
});

describe('ending the conversation', () => {
  it('can be finished early', () => {
    const state = finish(startConversation(guided()));
    expect(state.finished).toBe(true);
    expect(state.current).toBeNull();
    expect(saidByNura(state)).toContain(CLOSING_LINE.toLowerCase());
  });

  it('ignores an empty message', () => {
    const draft = guided();
    const state = startConversation(draft);
    const result = answer(state, draft, '   ', { today: TODAY });
    expect(result.state).toBe(state);
    expect(result.draft).toBe(draft);
  });
});

describe('applyExtraction', () => {
  it('keeps both halves of an onset described over two turns', () => {
    const first = applyExtraction(
      guided(),
      extract('it started suddenly', { today: TODAY })
    );
    const second = applyExtraction(
      first,
      extract('about three days ago', { expecting: 'onset', today: TODAY })
    );

    expect(second.onset).toContain('suddenly');
    expect(second.onsetDate).toBe('2026-09-24');
  });

  it('lets a newer severity replace an older one', () => {
    const first = applyExtraction(guided(), extract('it was 8/10', { today: TODAY }));
    const second = applyExtraction(first, extract('now it is 4/10', { today: TODAY }));
    expect(second.severity).toBe(4);
  });

  it('merges list fields without duplicating', () => {
    const first = applyExtraction(
      guided(),
      extract('nausea', { expecting: 'associatedSymptoms', today: TODAY })
    );
    const second = applyExtraction(
      first,
      extract('nausea and fever', { expecting: 'associatedSymptoms', today: TODAY })
    );
    expect(second.associatedSymptoms).toEqual(['nausea', 'fever']);
  });
});
