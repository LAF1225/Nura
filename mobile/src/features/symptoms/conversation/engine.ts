/**
 * The guided conversation (PRD 6, sections 26-29, 46, 67 and 74).
 *
 * Pure functions from (state, draft, message) to (state, draft). No component
 * state, no effects, no network. The screen renders what comes out and sends
 * what goes in, which is what makes a conversation testable without rendering
 * anything -- and what makes PRD 6 section 28's non-repetition rule something
 * a test can assert in three lines.
 *
 * What the conversation is, and is not:
 *
 * **It is deterministic** (PRD 6, section 27). Rule-based extraction, rule-based
 * next question, and a review screen at the end. There is no model, no external
 * service, and nothing that could produce a different answer twice.
 *
 * **It never concludes anything.** A concerning phrase produces a *question*
 * (PRD 6, section 46), and the answer to that question is stored as structured
 * data. Nothing escalates, nothing is diagnosed, and the safety rules that would
 * act on a confirmed answer live on the server and are switched off
 * (section 44).
 *
 * **It writes into the same draft the manual form writes into** (section 4).
 * Both end on the same review screen and save through the same request.
 */
import { newClientId, mergeItems, parseItems } from '../draft';
import { confirmationPrompt } from '../safetyMessages';
import type {
  ChangeState,
  ConversationState,
  ConversationTurn,
  PendingConfirmation,
  SymptomDraft,
  SymptomField,
} from '../types';
import { extract, type Extraction } from './extract';
import { nextField, openingQuestion, questionFor } from './questions';

/** What Nura says when there is nothing left to ask (PRD 6, section 30). */
export const CLOSING_LINE =
  'Thank you. Here is what I have — have a look and change anything that is not right.';

/** The opening line of a follow-up, which already knows what it is about. */
export function followUpOpening(episodeName: string): string {
  return `How is your ${episodeName.toLowerCase()} doing?`;
}

export interface Advance {
  state: ConversationState;
  draft: SymptomDraft;
}

function turn(speaker: 'nura' | 'user', text: string): ConversationTurn {
  return { id: newClientId('turn'), speaker, text };
}

/**
 * Starts a conversation.
 *
 * An opening line, then the first question worth asking -- which for a
 * follow-up is about how things are going rather than what is wrong, because
 * Nura already knows what it is about (PRD 6, section 47).
 */
export function startConversation(
  draft: SymptomDraft,
  options: { episodeName?: string } = {}
): ConversationState {
  const question = openingQuestion(draft);
  const opening =
    draft.episodeId !== undefined && options.episodeName
      ? [
          turn('nura', followUpOpening(options.episodeName)),
          turn('nura', question.prompt),
        ]
      : [turn('nura', question.prompt)];

  return {
    turns: opening,
    asked: [question.field],
    current: question,
    pendingConfirmation: null,
    finished: false,
  };
}

/**
 * What the draft already knows, so an answer cannot overwrite it.
 *
 * Somebody answering "how bad is it?" with "about a 5, still in my knee" has
 * repeated where it is, not changed it (PRD 6, section 28).
 */
function knownFields(draft: SymptomDraft): Partial<Record<SymptomField, boolean>> {
  return {
    mainSymptom: Boolean(draft.mainSymptom),
    site: Boolean(draft.site),
    onset: Boolean(draft.onset),
    character: Boolean(draft.character),
    radiation: Boolean(draft.radiation),
    timing: Boolean(draft.timing),
  };
}

/** Folds an extraction into the draft, never replacing what is already there. */
export function applyExtraction(draft: SymptomDraft, found: Extraction): SymptomDraft {
  const next: SymptomDraft = { ...draft };

  if (found.mainSymptom !== undefined && !next.mainSymptom) {
    next.mainSymptom = found.mainSymptom;
  }
  if (found.site !== undefined && !next.site) next.site = found.site;
  if (found.character !== undefined && !next.character) next.character = found.character;
  if (found.radiation !== undefined && !next.radiation) next.radiation = found.radiation;
  if (found.timing !== undefined && !next.timing) next.timing = found.timing;

  // Onset keeps both halves: the wording accumulates, and a date fills in the
  // first time one is understood (PRD 6, section 74).
  if (found.onset !== undefined) {
    next.onset =
      next.onset && !next.onset.includes(found.onset)
        ? `${next.onset}, ${found.onset}`
        : (next.onset ?? found.onset);
  }
  if (found.onsetDate !== undefined && next.onsetDate === undefined) {
    next.onsetDate = found.onsetDate;
  }

  // A number the user gave later replaces an earlier one: they are answering
  // "how bad is it *right now*", and the most recent answer is the current one.
  if (found.severity !== undefined) next.severity = found.severity;
  if (found.changeState !== undefined)
    next.changeState = found.changeState as ChangeState;

  if (found.associatedSymptoms.length > 0) {
    next.associatedSymptoms = mergeItems(
      next.associatedSymptoms,
      found.associatedSymptoms
    );
  }
  if (found.exacerbatingFactors.length > 0) {
    next.exacerbatingFactors = mergeItems(
      next.exacerbatingFactors,
      found.exacerbatingFactors
    );
  }
  if (found.relievingFactors.length > 0) {
    next.relievingFactors = mergeItems(next.relievingFactors, found.relievingFactors);
  }
  if (found.negatedItems.length > 0) {
    next.negatedItems = mergeItems(next.negatedItems, found.negatedItems);
  }
  if (found.uncertainItems.length > 0) {
    next.uncertainItems = mergeItems(next.uncertainItems, found.uncertainItems);
  }
  if (found.contextDependentItems.length > 0) {
    next.contextDependentItems = mergeItems(
      next.contextDependentItems,
      found.contextDependentItems
    );
  }
  return next;
}

/** Moves the conversation on to whatever is worth asking next. */
function withNextQuestion(
  state: ConversationState,
  draft: SymptomDraft,
  turns: ConversationTurn[]
): Advance {
  const field = nextField(draft, state.asked);

  if (field === null) {
    return {
      draft,
      state: {
        ...state,
        turns: [...turns, turn('nura', CLOSING_LINE)],
        current: null,
        pendingConfirmation: null,
        finished: true,
      },
    };
  }

  const question = questionFor(field, draft);
  return {
    draft,
    state: {
      ...state,
      turns: [...turns, turn('nura', question.prompt)],
      asked: [...state.asked, field],
      current: question,
      pendingConfirmation: null,
      finished: false,
    },
  };
}

/**
 * The user typed something.
 *
 * Everything the message says is read, not only the answer to the question that
 * was asked -- which is what makes the non-repetition rule actually save the
 * user time rather than just avoid an obvious repeat.
 */
export function answer(
  state: ConversationState,
  draft: SymptomDraft,
  message: string,
  options: { today?: string } = {}
): Advance {
  const text = message.trim();
  if (text.length === 0) return { state, draft };

  const turns = [...state.turns, turn('user', text)];

  // A pending confirmation is answered before anything else is read: Nura asked
  // a direct question and has to hear the answer to it (PRD 6, section 46).
  if (state.pendingConfirmation !== null) {
    return resolveConfirmation(state, draft, text, turns);
  }

  const found = extract(text, {
    expecting: state.current?.field ?? null,
    known: knownFields(draft),
    today: options.today,
  });
  const updated = applyExtraction(draft, found);

  // Something concerning, and Nura is not sure it understood. Ask, and follow
  // nothing from the guess (PRD 6, section 46).
  const term = found.redFlags[0];
  if (term !== undefined && !alreadySettled(updated, term)) {
    const confirmation: PendingConfirmation = { term, prompt: confirmationPrompt(term) };
    return {
      draft: updated,
      state: {
        ...state,
        turns: [...turns, turn('nura', confirmation.prompt)],
        pendingConfirmation: confirmation,
        finished: false,
      },
    };
  }

  return withNextQuestion(state, updated, turns);
}

/** Whether a concerning phrase has already been confirmed or ruled out. */
function alreadySettled(draft: SymptomDraft, term: string): boolean {
  const lowered = term.toLowerCase();
  const settled = [
    ...(draft.associatedSymptoms ?? []),
    ...(draft.negatedItems ?? []),
    ...(draft.uncertainItems ?? []),
  ].map((item) => item.toLowerCase());
  return settled.includes(lowered);
}

/**
 * A yes or no to "just to confirm…".
 *
 * A yes records the canonical phrase, which is what the server's rules match
 * on. A no records it as *denied* rather than dropping it, because "no, I can
 * breathe fine" is information and losing it would let the same phrase be
 * queried again (PRD 6, sections 24 and 46).
 */
function resolveConfirmation(
  state: ConversationState,
  draft: SymptomDraft,
  text: string,
  turns: ConversationTurn[]
): Advance {
  const confirmation = state.pendingConfirmation;
  if (confirmation === null) return { state, draft };

  const said = text.toLowerCase();
  const yes = /\b(yes|yeah|yep|correct|that'?s right|i am|i do)\b/.test(said);
  const no = /\b(no|nope|not really|i'?m not|i am not|i don'?t)\b/.test(said);

  const updated: SymptomDraft = { ...draft };
  if (yes && !no) {
    updated.associatedSymptoms = mergeItems(updated.associatedSymptoms, [
      confirmation.term,
    ]);
  } else if (no) {
    updated.negatedItems = mergeItems(updated.negatedItems, [confirmation.term]);
  } else {
    // Neither, so it stays a maybe -- which is exactly what it is, and is the
    // one thing that must never turn into a conclusion (PRD 6, section 24).
    updated.uncertainItems = mergeItems(updated.uncertainItems, [confirmation.term]);
  }

  return withNextQuestion({ ...state, pendingConfirmation: null }, updated, turns);
}

/**
 * The user tapped one of the offered answers.
 *
 * A choice with no value is "skip this": the question is marked asked so it does
 * not come back, and nothing is written (PRD 6, section 25).
 */
export function choose(
  state: ConversationState,
  draft: SymptomDraft,
  choice: { label: string; value?: string },
  options: { today?: string } = {}
): Advance {
  const turns = [...state.turns, turn('user', choice.label)];

  if (state.pendingConfirmation !== null) {
    return resolveConfirmation(state, draft, choice.value ?? choice.label, turns);
  }

  // "Nothing else" and "Nothing I have noticed" are answers, not skips: they
  // say the question has been considered, so nothing is written and it is not
  // asked again.
  if (choice.value === undefined || choice.value === '') {
    return withNextQuestion(state, draft, turns);
  }

  const field = state.current?.field ?? null;
  const updated = applyChoice(draft, field, choice.value, options.today);
  return withNextQuestion(state, updated, turns);
}

function applyChoice(
  draft: SymptomDraft,
  field: SymptomField | null,
  value: string,
  today?: string
): SymptomDraft {
  if (field === null) return draft;

  // A tapped severity or change state is unambiguous and goes straight in. A
  // tapped word for any other field is read the same way a typed one would be,
  // so "yesterday" resolves to a date exactly as it does when typed.
  if (field === 'severity') {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? { ...draft, severity: parsed } : draft;
  }
  if (field === 'changeState') {
    return { ...draft, changeState: value as ChangeState };
  }
  if (field === 'associatedSymptoms') {
    return {
      ...draft,
      associatedSymptoms: mergeItems(draft.associatedSymptoms, parseItems(value)),
    };
  }

  const found = extract(value, { expecting: field, known: knownFields(draft), today });
  return applyExtraction(draft, found);
}

/**
 * Ends the conversation early.
 *
 * Offered throughout: somebody who has said what they want to say should not
 * have to answer four more questions to reach the review screen.
 */
export function finish(state: ConversationState): ConversationState {
  if (state.finished) return state;
  return {
    ...state,
    turns: [...state.turns, turn('nura', CLOSING_LINE)],
    current: null,
    pendingConfirmation: null,
    finished: true,
  };
}

/**
 * How many of Nura's questions have been answered, for the progress line.
 *
 * Counts questions rather than fields, because that is what the person
 * experiences.
 */
export function answeredCount(state: ConversationState): number {
  return state.turns.filter((entry) => entry.speaker === 'user').length;
}
