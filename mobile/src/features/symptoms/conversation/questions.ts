/**
 * Which question to ask next, and how to word it (PRD 6, ss12, 25, 28, 47, 73).
 *
 * All of it in one file, because PRD 6 section 73 asks for exactly that:
 * next-question logic centralised rather than scattered through the screens. The
 * conversation screen renders whatever this returns and knows nothing about the
 * order.
 *
 * **Non-repetition is a hard acceptance criterion** (PRD 6, section 28), and it
 * falls out of one rule here: a field with a value is never a candidate. So a
 * first message of "a sharp pain in my left knee that started yesterday and is
 * 6/10" leaves nothing to ask about the symptom, the site, the character, the
 * onset or the severity, and the conversation moves straight on.
 *
 * **Relevance is the other half.** PRD 6 section 12 forbids forcing every
 * symptom through pain-specific fields: radiation is not asked about fatigue,
 * and neither a site nor a texture is asked about a fever. Skipping a question
 * that makes no sense is how the flow stays short enough that people finish it.
 */
import { CHANGE_STATES, FIELD_LABELS, SEVERITY_MAX, SEVERITY_MIN } from '../copy';
import type {
  ConversationChoice,
  ConversationQuestion,
  SymptomDraft,
  SymptomField,
} from '../types';
import { isPainLike } from './extract';

/**
 * The order questions are offered in, which is PRD 6 section 25's flow with
 * radiation and timing slotted beside the fields they belong with.
 */
export const FIELD_ORDER: readonly SymptomField[] = [
  'mainSymptom',
  'onset',
  'site',
  'severity',
  'character',
  'radiation',
  'associatedSymptoms',
  'timing',
  'factors',
  'changeState',
];

/** What a follow-up asks about, and nothing more (PRD 6, section 47). */
export const FOLLOW_UP_FIELDS: readonly SymptomField[] = [
  'severity',
  'changeState',
  'associatedSymptoms',
];

/**
 * Symptoms where "where do you feel it?" is the wrong question.
 *
 * A fever is not somewhere. Asking anyway is how a guided flow starts feeling
 * like a form (PRD 6, section 12).
 */
const WITHOUT_A_SITE: readonly string[] = [
  'fatigue',
  'tiredness',
  'fever',
  'chills',
  'sweating',
  'insomnia',
  'loss of appetite',
  'nausea',
  'vomiting',
];

/** Symptoms where "what does it feel like?" is the wrong question. */
const WITHOUT_A_TEXTURE: readonly string[] = [
  'fatigue',
  'tiredness',
  'fever',
  'chills',
  'sweating',
  'insomnia',
  'loss of appetite',
];

function matchesAny(value: string | undefined, terms: readonly string[]): boolean {
  if (value === undefined) return false;
  const lowered = value.toLowerCase();
  return terms.some((term) => lowered.includes(term));
}

/** Whether the draft already has an answer for this field. */
export function isCaptured(draft: SymptomDraft, field: SymptomField): boolean {
  switch (field) {
    case 'mainSymptom':
      return Boolean(draft.mainSymptom);
    // Onset counts as captured only when a *time* is known. "It started
    // suddenly" is how, not when, so the question still gets asked -- and both
    // answers are kept (PRD 6, section 74).
    case 'onset':
      return Boolean(draft.onsetDate);
    case 'site':
      return Boolean(draft.site);
    case 'severity':
      return draft.severity !== undefined;
    case 'character':
      return Boolean(draft.character);
    case 'radiation':
      return Boolean(draft.radiation);
    case 'associatedSymptoms':
      return (
        (draft.associatedSymptoms?.length ?? 0) > 0 ||
        (draft.negatedItems?.length ?? 0) > 0
      );
    case 'timing':
      return Boolean(draft.timing);
    case 'factors':
      return (
        (draft.exacerbatingFactors?.length ?? 0) > 0 ||
        (draft.relievingFactors?.length ?? 0) > 0
      );
    case 'changeState':
      return draft.changeState !== undefined;
  }
}

/** Whether this field makes sense for what is being described. */
export function isRelevant(draft: SymptomDraft, field: SymptomField): boolean {
  if (field === 'radiation') {
    return isPainLike(draft.mainSymptom, draft.character);
  }
  if (field === 'site') {
    return !matchesAny(draft.mainSymptom, WITHOUT_A_SITE);
  }
  if (field === 'character') {
    return !matchesAny(draft.mainSymptom, WITHOUT_A_TEXTURE);
  }
  return true;
}

/**
 * The next thing worth asking, or null when there is nothing left.
 *
 * Skips anything already answered, anything already asked -- a question the
 * user chose to skip is not asked twice -- and anything irrelevant to this
 * symptom.
 */
export function nextField(
  draft: SymptomDraft,
  asked: readonly SymptomField[]
): SymptomField | null {
  const candidates = draft.episodeId === undefined ? FIELD_ORDER : FOLLOW_UP_FIELDS;
  for (const field of candidates) {
    if (asked.includes(field)) continue;
    if (isCaptured(draft, field)) continue;
    if (!isRelevant(draft, field)) continue;
    return field;
  }
  return null;
}

// --- wording ----------------------------------------------------------------

/** Offered on every question, because nothing is compulsory (s25, s67). */
const SKIP: ConversationChoice = { label: 'Skip this' };

const SEVERITY_CHOICES: ConversationChoice[] = Array.from(
  { length: SEVERITY_MAX - SEVERITY_MIN + 1 },
  (_, index) => ({
    label: String(index + SEVERITY_MIN),
    value: String(index + SEVERITY_MIN),
  })
);

const CHARACTER_CHOICES: ConversationChoice[] = [
  'sharp',
  'dull',
  'burning',
  'throbbing',
  'pressure',
  'cramping',
].map((term) => ({ label: term, value: term }));

const TIMING_CHOICES: ConversationChoice[] = [
  'constant',
  'comes and goes',
  'worse in the morning',
  'worse at night',
].map((term) => ({ label: term, value: term }));

/**
 * The question for a field, worded for this draft.
 *
 * The prompts reuse `FIELD_LABELS`, so the guided flow and the manual form ask
 * the same thing in the same words -- two wordings for one question is how a
 * product starts feeling like two products.
 */
export function questionFor(
  field: SymptomField,
  draft: SymptomDraft
): ConversationQuestion {
  switch (field) {
    case 'mainSymptom':
      return {
        field,
        prompt: FIELD_LABELS.mainSymptom,
        choices: [SKIP],
        freeText: true,
      };
    case 'onset':
      return {
        field,
        // Asked this way on purpose when a *how* is already known: somebody who
        // said "it started suddenly" has told Nura something real, and being
        // asked "when did it start?" flatly would read as not having listened
        // (PRD 6, section 74).
        prompt: draft.onset ? 'About when did it start?' : FIELD_LABELS.onset,
        choices: [
          { label: 'Today', value: 'today' },
          { label: 'Yesterday', value: 'yesterday' },
          { label: 'A few days ago', value: 'a few days ago' },
          { label: 'Longer ago', value: 'a while ago' },
          SKIP,
        ],
        freeText: true,
      };
    case 'site':
      return { field, prompt: FIELD_LABELS.site, choices: [SKIP], freeText: true };
    case 'severity':
      return {
        field,
        prompt: `${FIELD_LABELS.severity} ${SEVERITY_MIN} is none and ${SEVERITY_MAX} is the worst you can imagine.`,
        choices: [...SEVERITY_CHOICES, SKIP],
        freeText: true,
      };
    case 'character':
      return {
        field,
        // The choices are examples, never a closed set: PRD 6 section 75 says
        // not to force somebody into a category Nura offered.
        prompt: `${FIELD_LABELS.character} For example, ${CHARACTER_CHOICES.slice(0, 5)
          .map((choice) => choice.label)
          .join(', ')} — or something else entirely.`,
        choices: [...CHARACTER_CHOICES, SKIP],
        freeText: true,
      };
    case 'radiation':
      return {
        field,
        prompt: FIELD_LABELS.radiation,
        choices: [{ label: 'Stays in one place', value: 'stays in one place' }, SKIP],
        freeText: true,
      };
    case 'associatedSymptoms':
      return {
        field,
        prompt: FIELD_LABELS.associatedSymptoms,
        choices: [{ label: 'Nothing else', value: '' }, SKIP],
        freeText: true,
      };
    case 'timing':
      return {
        field,
        prompt: FIELD_LABELS.timing,
        choices: [...TIMING_CHOICES, SKIP],
        freeText: true,
      };
    case 'factors':
      return {
        field,
        prompt: `${FIELD_LABELS.exacerbatingFactors} And is there anything that helps?`,
        choices: [{ label: 'Nothing I have noticed', value: '' }, SKIP],
        freeText: true,
      };
    case 'changeState':
      return {
        field,
        prompt:
          draft.episodeId === undefined
            ? 'Has it changed since it started?'
            : FIELD_LABELS.changeState,
        choices: [
          ...CHANGE_STATES.map((entry) => ({ label: entry.label, value: entry.value })),
          SKIP,
        ],
        // Four answers and nothing in between. A typed answer is still read for
        // a comparison, but there is nothing verbatim to keep here.
        freeText: false,
      };
  }
}

/** The opening line, which is also the first question (PRD 6, section 26). */
export function openingQuestion(draft: SymptomDraft): ConversationQuestion {
  const field = nextField(draft, []);
  return field === null ? questionFor('severity', draft) : questionFor(field, draft);
}
