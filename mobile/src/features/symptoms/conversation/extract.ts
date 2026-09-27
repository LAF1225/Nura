/**
 * Turning what somebody typed into structured fields (PRD 6, ss24, 27, 28, 74).
 *
 * Pure functions over a string. No network, no model, no state -- which is what
 * makes the non-repetition rule testable: PRD 6 section 28 is a hard acceptance
 * criterion, and the way to be sure of it is to be able to assert directly that
 * one sentence fills four fields.
 *
 * Three rules shape everything here.
 *
 * **Nothing is invented.** A field is filled only when a phrase actually
 * matched. Where extraction finds nothing, the value stays empty and the
 * question gets asked -- which is the correct outcome, not a failure.
 *
 * **Nothing is lost.** When a question was asked and the answer matches no
 * pattern, the answer is kept verbatim for that question. "It feels like a
 * tight band" becomes the character whether or not "tight band" is in a list
 * (PRD 6, section 75).
 *
 * **Hedging and denial win over detection.** A symptom word inside "no nausea"
 * or "I might have felt dizzy" never becomes a symptom the person has. It goes
 * to `negatedItems` or `uncertainItems`, because losing the difference is the
 * false certainty PRD 6 section 24 forbids.
 */
import type { ChangeState, SymptomField } from '../types';
import {
  BETTER_PATTERNS,
  BODY_PARTS,
  CHANGE_PATTERNS,
  CHARACTER_TERMS,
  CONTEXT_CUES,
  NEGATION_CUES,
  NUMBER_WORDS,
  ONSET_CHARACTER,
  PAIN_WORDS,
  PAIN_LIKE,
  RADIATION_PATTERNS,
  RED_FLAG_HINTS,
  RED_FLAG_TERMS,
  RELATIVE_ONSET,
  SITE_MODIFIERS,
  SITE_PREPOSITIONS,
  SYMPTOM_TERMS,
  TIMING_PHRASES,
  UNCERTAINTY_CUES,
  WORSE_PATTERNS,
} from './vocabulary';

export interface Extraction {
  mainSymptom?: string;
  site?: string;
  /** The user's own wording for onset, including how it began. */
  onset?: string;
  /** `YYYY-MM-DD`, only when a phrase pinned it to a day. */
  onsetDate?: string;
  character?: string;
  radiation?: string;
  timing?: string;
  severity?: number;
  changeState?: ChangeState;
  associatedSymptoms: string[];
  exacerbatingFactors: string[];
  relievingFactors: string[];
  negatedItems: string[];
  uncertainItems: string[];
  contextDependentItems: string[];
  /** Canonical concerning phrases to check before anything follows (s46). */
  redFlags: string[];
}

export interface ExtractOptions {
  /** The question that was asked, if any. Decides where a bare answer goes. */
  expecting?: SymptomField | null;
  /** Fields that already have a value, so nothing is overwritten. */
  known?: Partial<Record<SymptomField, boolean>>;
  /** The user's local day, for resolving "yesterday". */
  today?: string;
}

function empty(): Extraction {
  return {
    associatedSymptoms: [],
    exacerbatingFactors: [],
    relievingFactors: [],
    negatedItems: [],
    uncertainItems: [],
    contextDependentItems: [],
    redFlags: [],
  };
}

function normalise(text: string): string {
  return text.toLowerCase().replace(/[’']/g, "'").replace(/\s+/g, ' ').trim();
}

/** Splits a message into the clauses hedging and denial apply to. */
function clauses(text: string): string[] {
  return text
    .split(/[,;.!?]|\bbut\b|\balthough\b|\bthough\b/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

function firstMatch(text: string, terms: readonly string[]): string | undefined {
  for (const term of terms) {
    if (new RegExp(`\\b${escapeRegExp(term)}\\b`).test(text)) return term;
  }
  return undefined;
}

function allMatches(text: string, terms: readonly string[]): string[] {
  return terms.filter((term) => new RegExp(`\\b${escapeRegExp(term)}\\b`).test(text));
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// --- clause classification --------------------------------------------------

type Tone = 'plain' | 'uncertain' | 'negated' | 'contextual';

/**
 * How certain a clause is.
 *
 * Uncertainty is checked first on purpose: "I'm not sure if it spreads"
 * contains "not", and reading it as a denial would record the opposite of what
 * was said (PRD 6, section 24).
 */
export function toneOf(clause: string): Tone {
  if (UNCERTAINTY_CUES.some((cue) => hasPhrase(clause, cue))) return 'uncertain';
  if (CONTEXT_CUES.some((cue) => hasPhrase(clause, cue))) return 'contextual';
  if (NEGATION_CUES.some((cue) => hasPhrase(clause, cue))) return 'negated';
  return 'plain';
}

/**
 * Whether a phrase appears as whole words.
 *
 * A substring test is not good enough here: "cannot breathe" contains the
 * letters of "not", and reading that as a denial would record the opposite of
 * what somebody said -- about breathing, of all things (PRD 6, section 24).
 */
function hasPhrase(text: string, phrase: string): boolean {
  return new RegExp(`(^|[^a-z0-9'])${escapeRegExp(phrase)}($|[^a-z0-9'])`).test(text);
}

// --- sites ------------------------------------------------------------------

/**
 * A location phrase, keeping whatever qualifies the body part.
 *
 * "mostly behind my eyes" -> "behind my eyes"; "a sharp pain in my left knee"
 * -> "left knee". The bare part is returned separately, because it is what
 * names the symptom while the phrase is what describes where it is.
 */
export function findSite(
  text: string
): { phrase: string; part: string; index: number } | undefined {
  for (const part of BODY_PARTS) {
    const match = new RegExp(`\\b${escapeRegExp(part)}\\b`).exec(text);
    if (match === null) continue;

    const before = text.slice(0, match.index).trim().split(' ');
    const kept: string[] = [];
    // Walk backwards while the words still belong to the location.
    for (let index = before.length - 1; index >= 0 && kept.length < 3; index -= 1) {
      const word = before[index] ?? '';
      if (
        SITE_MODIFIERS.includes(word) ||
        SITE_PREPOSITIONS.includes(word) ||
        word === 'my' ||
        word === 'the'
      ) {
        kept.unshift(word);
        if (SITE_PREPOSITIONS.includes(word)) break;
      } else {
        break;
      }
    }

    // "my knee" reads better as "knee"; "behind my eyes" needs the "my".
    while (
      kept.length > 0 &&
      (kept[0] === 'my' || kept[0] === 'the') &&
      !SITE_PREPOSITIONS.includes(kept[0] ?? '')
    ) {
      kept.shift();
    }

    return { phrase: [...kept, part].join(' '), part, index: match.index };
  }
  return undefined;
}

// --- onset ------------------------------------------------------------------

function shiftDays(today: string, days: number): string {
  const date = new Date(`${today}T00:00:00`);
  if (Number.isNaN(date.getTime())) return today;
  date.setDate(date.getDate() - days);
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * When and how something started.
 *
 * Both are returned, because they are two different facts and PRD 6 section 74
 * asks for both: "it started suddenly" is how, "three days ago" is when, and
 * somebody who says only the first should still be asked the second.
 */
export function findOnset(
  text: string,
  today: string
): { wording: string; date?: string } | undefined {
  const parts: string[] = [];
  let date: string | undefined;

  const character = firstMatch(text, ONSET_CHARACTER);
  if (character !== undefined) parts.push(character);

  // "three days ago", "2 weeks ago".
  const counted =
    /\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|couple|few)\s+(hour|day|week|month)s?\s+ago\b/.exec(
      text
    );
  if (counted !== null) {
    const raw = counted[1] ?? '';
    const count = /^\d+$/.test(raw) ? Number(raw) : (NUMBER_WORDS[raw] ?? 1);
    const unit = counted[2] ?? 'day';
    const days =
      unit === 'hour'
        ? 0
        : unit === 'week'
          ? count * 7
          : unit === 'month'
            ? count * 30
            : count;
    parts.push(counted[0]);
    date = shiftDays(today, days);
  } else {
    const relative = RELATIVE_ONSET.find((entry) =>
      new RegExp(`\\b${escapeRegExp(entry.phrase)}\\b`).test(text)
    );
    if (relative !== undefined) {
      parts.push(relative.phrase);
      if (relative.daysAgo !== null) date = shiftDays(today, relative.daysAgo);
    }
  }

  // "after exercise", "since the weekend" -- wording worth keeping even when
  // it pins nothing down.
  const trigger = /\b(?:after|since|following)\s+([a-z][a-z\s]{2,30})/.exec(text);
  if (trigger !== null && parts.length === 0) {
    parts.push(trigger[0].trim());
  }

  if (parts.length === 0) return undefined;
  return { wording: parts.join(', '), date };
}

// --- severity ---------------------------------------------------------------

/**
 * A number on the 0-10 scale.
 *
 * "6/10" and "6 out of 10" count anywhere. A bare number counts **only** when
 * severity is what was asked, so "it started 3 days ago" does not become a
 * severity of 3.
 */
export function findSeverity(
  text: string,
  expecting?: SymptomField | null
): number | undefined {
  const scaled = /\b(10|[0-9])\s*(?:\/|out of)\s*10\b/.exec(text);
  if (scaled !== null) return Number(scaled[1]);

  if (expecting === 'severity') {
    const bare = /\b(10|[0-9])\b/.exec(text);
    if (bare !== null) return Number(bare[1]);
    const word = Object.entries(NUMBER_WORDS).find(
      ([name]) => name.length > 1 && new RegExp(`\\b${name}\\b`).test(text)
    );
    if (word !== undefined && word[1] <= 10) return word[1];
  }
  return undefined;
}

// --- factors and patterns ---------------------------------------------------

function capture(text: string, patterns: readonly RegExp[]): string[] {
  const found: string[] = [];
  for (const pattern of patterns) {
    const match = pattern.exec(text);
    if (match !== null) {
      const value = (match[1] ?? '').trim();
      if (value.length > 0) found.push(value);
    }
  }
  return found;
}

// --- the whole message ------------------------------------------------------

/**
 * Everything one message says.
 *
 * `known` stops an answer to one question from quietly rewriting a field the
 * user already gave: somebody answering "how bad is it?" with "about a 5, in my
 * knee" should not have their site replaced if they already said where it is.
 */
export function extract(message: string, options: ExtractOptions = {}): Extraction {
  const result = empty();
  const text = normalise(message);
  if (text.length === 0) return result;

  const today = options.today ?? new Date().toISOString().slice(0, 10);
  const expecting = options.expecting ?? null;
  const known = options.known ?? {};

  // --- hedged, denied and conditional clauses first -------------------------
  const plainParts: string[] = [];
  for (const clause of clauses(text)) {
    const tone = toneOf(clause);
    if (tone === 'plain') {
      plainParts.push(clause);
      continue;
    }
    // Whatever the clause is about is recorded with its hedge intact. The
    // symptom word if there is one, otherwise the clause as written -- because
    // "I'm not sure if it spreads" is worth keeping even though "spreads" is
    // not a symptom.
    const named = allMatches(clause, SYMPTOM_TERMS);
    const items = named.length > 0 ? named : [clause];
    if (tone === 'uncertain') result.uncertainItems.push(...items);
    if (tone === 'negated') result.negatedItems.push(...items);
    if (tone === 'contextual') result.contextDependentItems.push(...items);
  }
  const plain = plainParts.join(', ');

  // --- concerning phrases, for confirmation only ---------------------------
  const hedged = new Set(
    [...result.uncertainItems, ...result.negatedItems].map((item) => item.toLowerCase())
  );
  for (const term of RED_FLAG_TERMS) {
    if (new RegExp(`\\b${escapeRegExp(term)}\\b`).test(plain)) result.redFlags.push(term);
  }
  for (const hint of RED_FLAG_HINTS) {
    if (hint.pattern.test(plain) && !result.redFlags.includes(hint.term)) {
      result.redFlags.push(hint.term);
    }
  }
  // A phrase the user has already hedged or denied is not asked about again.
  result.redFlags = result.redFlags.filter((term) => !hedged.has(term.toLowerCase()));

  // --- site ---------------------------------------------------------------
  const site = findSite(plain);
  if (site !== undefined && known.site !== true) {
    result.site = site.phrase;
  }

  // --- what it is ---------------------------------------------------------
  const named = allMatches(plain, SYMPTOM_TERMS);
  if (known.mainSymptom !== true && expecting !== 'associatedSymptoms') {
    if (named.length > 0) {
      result.mainSymptom = named[0];
      result.associatedSymptoms.push(...named.slice(1));
    } else if (site !== undefined && PAIN_WORDS.some((word) => plain.includes(word))) {
      // Nobody named it, but they said a part of them hurts. "head pain" is a
      // faithful rendering of "my head has been hurting", and the review screen
      // is where they can call it something else (PRD 6, sections 13 and 30).
      result.mainSymptom = `${site.part} pain`;
    }
  } else {
    result.associatedSymptoms.push(...named);
  }

  // --- character ---------------------------------------------------------
  const character = firstMatch(plain, CHARACTER_TERMS);
  if (character !== undefined && known.character !== true) result.character = character;

  // --- timing ------------------------------------------------------------
  const timing = firstMatch(plain, TIMING_PHRASES);
  if (timing !== undefined && known.timing !== true) result.timing = timing;

  // --- onset -------------------------------------------------------------
  const onset = findOnset(plain, today);
  if (onset !== undefined) {
    if (known.onset !== true) result.onset = onset.wording;
    if (onset.date !== undefined) result.onsetDate = onset.date;
  }

  // --- severity ----------------------------------------------------------
  const severity = findSeverity(plain, expecting);
  if (severity !== undefined) result.severity = severity;

  // --- change ------------------------------------------------------------
  for (const entry of CHANGE_PATTERNS) {
    if (entry.pattern.test(plain)) {
      result.changeState = entry.value as ChangeState;
      break;
    }
  }

  // --- radiation ---------------------------------------------------------
  const radiation = capture(plain, RADIATION_PATTERNS);
  if (radiation.length > 0 && known.radiation !== true) {
    result.radiation = radiation[0];
  }

  // --- factors -----------------------------------------------------------
  result.exacerbatingFactors.push(...capture(plain, WORSE_PATTERNS));
  result.relievingFactors.push(...capture(plain, BETTER_PATTERNS));

  // --- the verbatim fallback ---------------------------------------------
  // A question was asked and nothing above matched it. The answer is what it
  // is, so it is kept exactly as typed (PRD 6, section 75).
  applyVerbatim(result, plain, message.trim(), expecting);

  return result;
}

function applyVerbatim(
  result: Extraction,
  plain: string,
  original: string,
  expecting: SymptomField | null
): void {
  if (expecting === null || original.length === 0) return;

  // A message that was entirely a denial has already been recorded as one;
  // taking it verbatim as the answer would store "no pain in my knee" as the
  // location. The symptom's own name is the exception: having nothing at all
  // there leaves the record unsavable, and the hedge is kept alongside it.
  const onlyHedged =
    plain.length === 0 &&
    (result.negatedItems.length > 0 || result.contextDependentItems.length > 0);
  if (onlyHedged && expecting !== 'mainSymptom') return;

  switch (expecting) {
    case 'mainSymptom':
      if (result.mainSymptom === undefined) result.mainSymptom = original;
      break;
    case 'site':
      if (result.site === undefined) result.site = original;
      break;
    case 'character':
      if (result.character === undefined) result.character = original;
      break;
    case 'radiation':
      if (result.radiation === undefined) result.radiation = original;
      break;
    case 'timing':
      if (result.timing === undefined) result.timing = original;
      break;
    case 'onset':
      if (result.onset === undefined) result.onset = original;
      break;
    case 'associatedSymptoms':
      if (result.associatedSymptoms.length === 0 && result.negatedItems.length === 0) {
        result.associatedSymptoms.push(...splitList(original));
      }
      break;
    case 'factors':
      if (
        result.exacerbatingFactors.length === 0 &&
        result.relievingFactors.length === 0
      ) {
        // The factors question asks what makes it worse, so an unqualified
        // answer to it is about what makes it worse.
        result.exacerbatingFactors.push(...splitList(original));
      }
      break;
    // Severity and change state are answered by tapping, and a free-text
    // answer to either is already handled above. Nothing verbatim would be
    // meaningful in a numeric or four-way field.
    case 'severity':
    case 'changeState':
      break;
  }
}

function splitList(value: string): string[] {
  return value
    .split(/,|\band\b/i)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/** Whether radiation is worth asking about for this description (s12, s17). */
export function isPainLike(
  mainSymptom: string | undefined,
  character: string | undefined
): boolean {
  const text = `${mainSymptom ?? ''} ${character ?? ''}`.toLowerCase();
  return PAIN_LIKE.some((word) => text.includes(word));
}
