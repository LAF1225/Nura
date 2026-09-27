/**
 * The words the guided flow recognises (PRD 6, sections 13-24, 27 and 75).
 *
 * PRD 6 section 27 is explicit: **no general-purpose LLM.** The guided
 * conversation is deterministic, and what it understands is what is written
 * down here. That has a real cost -- somebody can phrase something in a way
 * these lists miss -- and two things make that acceptable:
 *
 *   1. An answer the lists do not match is **kept verbatim** for whatever
 *      question was asked. Nothing is dropped because it was not recognised.
 *   2. Everything is shown on a review screen before it is saved, and every
 *      field can be corrected there (PRD 6, sections 30 and 76).
 *
 * So the vocabulary makes the conversation shorter when it works and harmless
 * when it does not. It is never the only thing standing between what somebody
 * said and what gets stored.
 *
 * **Nothing here maps to a diagnosis.** These are the words people use about
 * how they feel; not one of them is a condition, and no combination of them
 * means anything to Nura beyond the words themselves (PRD 6, sections 13, 16
 * and 81).
 */

/**
 * Symptoms people name directly.
 *
 * Longest first, because matching is a scan for the first hit: "shortness of
 * breath" has to win over "breath".
 */
export const SYMPTOM_TERMS: readonly string[] = [
  'shortness of breath',
  'difficulty breathing',
  'trouble breathing',
  'light sensitivity',
  'pins and needles',
  'loss of appetite',
  'blurred vision',
  'double vision',
  'palpitations',
  'constipation',
  'indigestion',
  'sore throat',
  'runny nose',
  'stiffness',
  'heartburn',
  'dizziness',
  'diarrhoea',
  'diarrhea',
  'breathless',
  'tightness',
  'headache',
  'migraine aura',
  'insomnia',
  'swelling',
  'vomiting',
  'wheezing',
  'bloating',
  'numbness',
  'weakness',
  'tiredness',
  'sweating',
  'shivers',
  'itching',
  'fatigue',
  'cramping',
  'bruising',
  'dizzy',
  'nausea',
  'chills',
  'fever',
  'cough',
  'rash',
  'cramp',
  'itchy',
];

/**
 * Words that mean something hurts.
 *
 * Used with a body part to build a name for a symptom nobody named: "my head
 * has been hurting" becomes "head pain", which the review screen then lets
 * them change (PRD 6, section 13).
 */
export const PAIN_WORDS: readonly string[] = [
  'hurting',
  'hurts',
  'hurt',
  'aching',
  'aches',
  'ache',
  'sore',
  'painful',
  'pain',
  'stinging',
  'throbbing',
];

/** Words suggesting radiation is a sensible thing to ask about (s12, s17). */
export const PAIN_LIKE: readonly string[] = [
  'pain',
  'ache',
  'aching',
  'sore',
  'hurt',
  'cramp',
  'cramping',
  'sharp',
  'stabbing',
  'burning',
  'throbbing',
  'pressure',
  'tight',
];

/** Body parts, longest first (PRD 6, section 14). */
export const BODY_PARTS: readonly string[] = [
  'whole body',
  'lower abdomen',
  'upper abdomen',
  'lower back',
  'upper back',
  'right side',
  'left side',
  'forehead',
  'shoulder',
  'shoulders',
  'stomach',
  'abdomen',
  'temples',
  'temple',
  'fingers',
  'finger',
  'throat',
  'ankles',
  'ankle',
  'elbow',
  'wrist',
  'thigh',
  'chest',
  'teeth',
  'tooth',
  'knees',
  'knee',
  'hands',
  'hand',
  'feet',
  'foot',
  'legs',
  'leg',
  'arms',
  'arm',
  'eyes',
  'eye',
  'ears',
  'ear',
  'neck',
  'back',
  'head',
  'hips',
  'hip',
  'jaw',
  'skin',
  'toes',
  'toe',
  'ribs',
  'calf',
  'shin',
  'groin',
  'belly',
];

/** Kept in front of a body part when building a location phrase. */
export const SITE_MODIFIERS: readonly string[] = [
  'left',
  'right',
  'both',
  'lower',
  'upper',
  'middle',
  'front',
  'back',
  'whole',
];

/** Prepositions that are part of a location -- "behind my eyes". */
export const SITE_PREPOSITIONS: readonly string[] = [
  'behind',
  'above',
  'below',
  'under',
  'around',
  'between',
  'across',
  'inside',
  'near',
  'along',
  'down',
];

/** How something feels (PRD 6, section 16). Never read diagnostically. */
export const CHARACTER_TERMS: readonly string[] = [
  'pins and needles',
  'like a tight band',
  'crushing',
  'throbbing',
  'stabbing',
  'cramping',
  'pressure',
  'squeezing',
  'shooting',
  'gnawing',
  'burning',
  'tingling',
  'prickling',
  'aching',
  'stinging',
  'pulsing',
  'spinning',
  'twisting',
  'sharp',
  'dull',
  'tight',
  'heavy',
  'itchy',
  'numb',
  'raw',
];

/** Patterns for how it comes and goes (PRD 6, section 19). */
export const TIMING_PHRASES: readonly string[] = [
  'comes and goes',
  'on and off',
  'all the time',
  'most of the time',
  'worse in the morning',
  'worse in the mornings',
  'worse in the evening',
  'worse at night',
  'worse at bedtime',
  'better at night',
  'after meals',
  'after eating',
  'before meals',
  'during exercise',
  'after exercise',
  'when i wake up',
  'first thing',
  'constant',
  'constantly',
  'intermittent',
  'in the morning',
  'at night',
];

/** How something began, as distinct from when (PRD 6, section 74). */
export const ONSET_CHARACTER: readonly string[] = [
  'all at once',
  'out of nowhere',
  'very suddenly',
  'suddenly',
  'gradually',
  'slowly',
  'over a few days',
  'overnight',
];

/**
 * Relative times, with how many days back each one means.
 *
 * `null` means the phrase locates the onset loosely enough that Nura should
 * still ask roughly when -- "a while ago" is wording worth keeping and a date
 * worth asking for (PRD 6, section 74).
 */
export const RELATIVE_ONSET: readonly { phrase: string; daysAgo: number | null }[] = [
  { phrase: 'this morning', daysAgo: 0 },
  { phrase: 'this afternoon', daysAgo: 0 },
  { phrase: 'this evening', daysAgo: 0 },
  { phrase: 'earlier today', daysAgo: 0 },
  { phrase: 'today', daysAgo: 0 },
  { phrase: 'last night', daysAgo: 1 },
  { phrase: 'yesterday', daysAgo: 1 },
  { phrase: 'the day before yesterday', daysAgo: 2 },
  { phrase: 'last week', daysAgo: 7 },
  { phrase: 'a week ago', daysAgo: 7 },
  { phrase: 'a fortnight ago', daysAgo: 14 },
  { phrase: 'last month', daysAgo: 30 },
  { phrase: 'a month ago', daysAgo: 30 },
  { phrase: 'a while ago', daysAgo: null },
  { phrase: 'a few days ago', daysAgo: 3 },
  { phrase: 'ages ago', daysAgo: null },
];

/** "three days ago", "2 weeks ago" -- a number and a unit. */
export const NUMBER_WORDS: Record<string, number> = {
  one: 1,
  two: 2,
  three: 3,
  four: 4,
  five: 5,
  six: 6,
  seven: 7,
  eight: 8,
  nine: 9,
  ten: 10,
  a: 1,
  an: 1,
  couple: 2,
  few: 3,
};

// --- hedging, denial and context --------------------------------------------

/**
 * Phrases that mean "I am not sure".
 *
 * Checked *before* negation, because "not sure" contains "not" and treating it
 * as a denial would be the exact opposite of what was said
 * (PRD 6, section 24).
 */
export const UNCERTAINTY_CUES: readonly string[] = [
  "i'm not sure",
  'im not sure',
  'i am not sure',
  'not sure',
  'not certain',
  "don't know",
  'dont know',
  'do not know',
  'might have',
  'might be',
  'might',
  'maybe',
  'perhaps',
  'possibly',
  'i think',
  'i guess',
  'could be',
  'kind of',
  'sort of',
  'hard to say',
  'i suppose',
];

/**
 * Phrases that deny something outright (PRD 6, section 24).
 *
 * Matched on word boundaries, not as substrings -- which is why none of these
 * carries a trailing space. "cannot breathe" contains the letters of "not" and
 * must never be read as a denial of breathing.
 */
export const NEGATION_CUES: readonly string[] = [
  'no',
  'not',
  'none',
  'never',
  'without',
  "haven't",
  'have not',
  "hasn't",
  'has not',
  "don't have",
  'do not have',
  "didn't",
  'did not',
  "isn't",
  'is not',
  'free of',
  'nothing',
];

/**
 * Phrases that make something true only sometimes (PRD 6, section 24).
 *
 * Deliberately narrow. A broader list -- "when i", "if i" -- swallows ordinary
 * descriptions of what makes a symptom worse ("it is worse when I walk"), which
 * belongs in `exacerbating_factors` rather than being filed as a conditional.
 * These are the phrases that genuinely qualify a claim rather than explain it.
 */
export const CONTEXT_CUES: readonly string[] = [
  'only when',
  'only if',
  'only after',
  'only while',
  'unless',
  'it depends',
];

// --- change state -----------------------------------------------------------

/** Explicit comparisons. Anything else is left to the question's choices. */
export const CHANGE_PATTERNS: readonly { pattern: RegExp; value: string }[] = [
  {
    pattern: /\b(getting|feels?|feeling|seems?|been|gone|got)\s+worse\b/,
    value: 'worsening',
  },
  { pattern: /\bworse than\b/, value: 'worsening' },
  {
    pattern: /\b(getting|feels?|feeling|seems?|been|gone|got)\s+better\b/,
    value: 'improving',
  },
  { pattern: /\bbetter than\b/, value: 'improving' },
  { pattern: /\bimproving\b/, value: 'improving' },
  { pattern: /\bworsening\b/, value: 'worsening' },
  { pattern: /\b(about the same|no change|unchanged|the same)\b/, value: 'same' },
];

// --- factors ----------------------------------------------------------------

/** "worse when I walk", "walking makes it worse". */
export const WORSE_PATTERNS: readonly RegExp[] = [
  /\bworse (?:when|with|if|after|on|by)\s+(?:i\s+)?([a-z][a-z\s]{1,40})/,
  /\b([a-z][a-z\s]{1,40}?)\s+makes? it worse\b/,
  /\bbrought on by\s+([a-z][a-z\s]{1,40})/,
];

/** "better when I rest", "rest helps". */
export const BETTER_PATTERNS: readonly RegExp[] = [
  /\bbetter (?:when|with|if|after|on|by)\s+(?:i\s+)?([a-z][a-z\s]{1,40})/,
  /\b([a-z][a-z\s]{1,40}?)\s+(?:makes? it better|helps|eases it|relieves it)\b/,
  /\b(?:eased|relieved|helped) by\s+([a-z][a-z\s]{1,40})/,
];

/** "spreads to my back", "stays in one place" (PRD 6, section 17). */
export const RADIATION_PATTERNS: readonly RegExp[] = [
  /\b(?:spreads?|radiates?|moves?|shoots?|goes|travels?)\s+(?:to|into|down|up|through|across)\s+(?:my |the )?([a-z][a-z\s]{1,30})/,
  /\b(stays in one place|stays put|does not move|doesn't move)\b/,
];

// --- concerning phrases -----------------------------------------------------

/**
 * Phrases Nura checks before anything follows from them
 * (PRD 6, sections 44 and 46).
 *
 * **These mirror `RED_FLAG_TERMS` in
 * `backend/app/services/symptoms/safety.py`.** The canonical phrase is what the
 * server's rules match on, so when the user confirms one it is written into the
 * entry exactly as spelled here. `symptomConversation.test.ts` asserts the two
 * lists still agree.
 *
 * Detecting one of these does **not** escalate anything. It asks a question.
 * The rules that would act on a confirmed answer are switched off until a
 * clinician has reviewed them, and until then a confirmation only makes the
 * description more accurate -- which is the point of the feature anyway.
 */
export const RED_FLAG_TERMS: readonly string[] = [
  'severe difficulty breathing',
  'cannot breathe',
  'loss of consciousness',
  'passed out',
  'new severe chest pain',
  'severe chest pain',
  'uncontrolled bleeding',
  'heavy bleeding that will not stop',
  'new severe weakness',
  'sudden weakness on one side',
];

/**
 * Looser phrases that suggest one of the canonical terms above.
 *
 * A person says "I can't catch my breath", not "severe difficulty breathing".
 * Matching the loose phrase is what prompts the confirmation question; the
 * canonical term is what gets stored if they say yes.
 */
export const RED_FLAG_HINTS: readonly { pattern: RegExp; term: string }[] = [
  {
    pattern:
      /\b(can'?t|cannot|struggling to|difficulty)\s+(catch my breath|breathe|breathing)\b/,
    term: 'severe difficulty breathing',
  },
  {
    pattern: /\b(passed out|blacked out|fainted|lost consciousness)\b/,
    term: 'passed out',
  },
  {
    pattern: /\b(crushing|severe|terrible|worst)\s+(chest pain|pain in my chest)\b/,
    term: 'severe chest pain',
  },
  {
    pattern: /\b(bleeding (?:that )?(?:won'?t|will not) stop|heavy bleeding)\b/,
    term: 'heavy bleeding that will not stop',
  },
  {
    pattern: /\b(weakness|numbness)\s+(?:down|on)\s+one side\b/,
    term: 'sudden weakness on one side',
  },
];
