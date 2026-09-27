/**
 * The shared symptom draft (PRD 6, sections 4, 29, 61 and 72).
 *
 * One draft representation, one validator, one payload builder -- used by the
 * manual form and by the guided conversation. That is what makes PRD 6
 * section 4's "both paths produce the same underlying structured record" a
 * property of the code rather than a promise in a comment: there is nowhere else
 * for either flow to put anything.
 *
 * Two decisions worth knowing.
 *
 * **A draft is not a record.** It lives on the phone until the user presses
 * Save on the review screen. Nothing incomplete is ever written to the backend
 * (PRD 6, section 29).
 *
 * **The id is generated when the draft starts, not when it is sent.** That is
 * what makes a retry safe: the same `clientEntryId` reaches the server however
 * many times the request is attempted, and the second one is answered with the
 * entry the first one created (PRD 6, section 61).
 */
import * as Crypto from 'expo-crypto';

import { localDateString } from '../../utils/date';
import { SEVERITY_MAX, SEVERITY_MIN } from './copy';
import type {
  ChangeState,
  EntryPayload,
  EpisodePayload,
  LocalPhotoDraft,
  SymptomDraft,
  SymptomSourceInput,
} from './types';

/** How many characters a single free-text answer may be. Mirrors the API. */
export const DESCRIPTOR_MAX_LENGTH = 200;
export const NAME_MAX_LENGTH = 120;
export const NOTE_MAX_LENGTH = 2000;
/** How many items one list field may hold. Mirrors `MAX_LIST_ITEMS`. */
export const MAX_LIST_ITEMS = 12;

function randomHex(byteCount: number): string {
  try {
    return Array.from(Crypto.getRandomBytes(byteCount), (byte) =>
      byte.toString(16).padStart(2, '0')
    ).join('');
  } catch {
    // No native crypto module, which happens under a test runner. An
    // idempotency key only has to be unique within one profile, so a
    // timestamp and a random suffix is a correct fallback -- it is not a
    // secret and nothing authenticates with it.
    return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
  }
}

/**
 * A fresh id for a draft.
 *
 * Prefixed so a value in a log or a database row is recognisable as a client
 * id rather than being mistaken for one of ours.
 */
export function newClientId(prefix = 'entry'): string {
  return `${prefix}-${randomHex(12)}`;
}

export function newDraft(options: {
  mode: SymptomSourceInput;
  /** Set for a follow-up on an existing episode. */
  episodeId?: string;
}): SymptomDraft {
  return {
    mode: options.mode,
    episodeId: options.episodeId,
    clientEntryId: newClientId(),
    associatedSymptoms: [],
    exacerbatingFactors: [],
    relievingFactors: [],
    negatedItems: [],
    uncertainItems: [],
    contextDependentItems: [],
    photos: [],
  };
}

/** True for a draft that is adding to an episode rather than starting one. */
export function isFollowUp(draft: SymptomDraft): boolean {
  return draft.episodeId !== undefined;
}

// --- text and lists ---------------------------------------------------------

/** Trims, and treats a blank answer as no answer. */
export function cleaned(value: string | undefined | null): string | undefined {
  if (value === undefined || value === null) return undefined;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

/**
 * "nausea, light sensitivity" -> two items.
 *
 * Splits on commas and the word "and", because people type both. Duplicates are
 * collapsed case-insensitively with the first spelling kept, which is the same
 * rule the server applies -- so what the review screen shows is what gets
 * stored.
 */
export function parseItems(value: string | undefined): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  const items: string[] = [];
  for (const raw of value.split(/,|\band\b/i)) {
    const item = raw.trim();
    if (item.length === 0) continue;
    const key = item.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    items.push(item.slice(0, DESCRIPTOR_MAX_LENGTH));
    if (items.length >= MAX_LIST_ITEMS) break;
  }
  return items;
}

export function formatItems(items: string[] | undefined): string {
  return (items ?? []).join(', ');
}

/** Adds items to a list field without duplicating what is already there. */
export function mergeItems(existing: string[] | undefined, added: string[]): string[] {
  return parseItems([...(existing ?? []), ...added].join(', '));
}

// --- validation -------------------------------------------------------------

export interface DraftErrors {
  mainSymptom?: string;
  severity?: string;
  note?: string;
}

/**
 * What stops a draft being saved.
 *
 * Deliberately almost nothing. A new symptom needs a name, because a record
 * with no name is not a record of anything; a follow-up needs not even that,
 * since the episode already has one. Everything else is optional, and PRD 6
 * sections 11 and 91 require a useful record to be savable without it.
 */
export function validateDraft(draft: SymptomDraft): DraftErrors {
  const errors: DraftErrors = {};

  if (!isFollowUp(draft) && cleaned(draft.mainSymptom) === undefined) {
    errors.mainSymptom = 'Add a few words for what you are experiencing.';
  }
  if (
    draft.severity !== undefined &&
    (!Number.isInteger(draft.severity) ||
      draft.severity < SEVERITY_MIN ||
      draft.severity > SEVERITY_MAX)
  ) {
    errors.severity = `Choose a number from ${SEVERITY_MIN} to ${SEVERITY_MAX}.`;
  }
  if ((draft.note ?? '').length > NOTE_MAX_LENGTH) {
    errors.note = 'That note is too long.';
  }
  return errors;
}

export function isSavable(draft: SymptomDraft): boolean {
  return Object.keys(validateDraft(draft)).length === 0;
}

/**
 * Whether the draft says anything at all.
 *
 * A follow-up with nothing in it would be a row recording that somebody opened
 * a screen, so the Save button waits until there is something to save.
 */
export function hasContent(draft: SymptomDraft): boolean {
  const text = [
    draft.mainSymptom,
    draft.site,
    draft.onset,
    draft.character,
    draft.radiation,
    draft.timing,
    draft.note,
    draft.onsetDate,
  ].some((value) => cleaned(value) !== undefined);

  const lists = [
    draft.associatedSymptoms,
    draft.exacerbatingFactors,
    draft.relievingFactors,
    draft.negatedItems,
    draft.uncertainItems,
    draft.contextDependentItems,
  ].some((items) => (items?.length ?? 0) > 0);

  return (
    text ||
    lists ||
    // Compared with undefined rather than tested for truthiness: a severity of
    // 0 means "no symptom", which is a real answer somebody chose
    // (PRD 6, section 22).
    draft.severity !== undefined ||
    draft.changeState !== undefined ||
    (draft.photos?.length ?? 0) > 0
  );
}

// --- payloads ---------------------------------------------------------------

function truncated(value: string | undefined, limit: number): string | null {
  const text = cleaned(value);
  return text === undefined ? null : text.slice(0, limit);
}

/**
 * The entry body.
 *
 * `recorded_at` is when the user saved it, not when the request goes out: a
 * draft saved offline may be hours old by the time it syncs, and the record has
 * to be about the moment it describes (PRD 6, section 59).
 */
export function entryPayload(
  draft: SymptomDraft,
  savedAt: Date = new Date()
): EntryPayload {
  return {
    client_entry_id: draft.clientEntryId,
    source: draft.mode,
    recorded_at: savedAt.toISOString(),
    main_symptom: truncated(draft.mainSymptom, NAME_MAX_LENGTH),
    site: truncated(draft.site, DESCRIPTOR_MAX_LENGTH),
    onset_text: truncated(draft.onset, DESCRIPTOR_MAX_LENGTH),
    onset_date: draft.onsetDate ?? null,
    character: truncated(draft.character, DESCRIPTOR_MAX_LENGTH),
    radiation: truncated(draft.radiation, DESCRIPTOR_MAX_LENGTH),
    timing: truncated(draft.timing, DESCRIPTOR_MAX_LENGTH),
    severity: draft.severity ?? null,
    change_state: draft.changeState ?? null,
    free_text_note: truncated(draft.note, NOTE_MAX_LENGTH),
    associated_symptoms: draft.associatedSymptoms ?? [],
    exacerbating_factors: draft.exacerbatingFactors ?? [],
    relieving_factors: draft.relievingFactors ?? [],
    negated_items: draft.negatedItems ?? [],
    uncertain_items: draft.uncertainItems ?? [],
    context_dependent_items: draft.contextDependentItems ?? [],
  };
}

/**
 * The episode body, for a draft that is starting a new symptom.
 *
 * The episode carries the name, where it is and when it began; the entry
 * carries the observation. Both go in one request, because both flows end at one
 * Save and splitting them would leave an episode with no description behind it
 * whenever the second call failed (PRD 6, section 30).
 */
export function episodePayload(
  draft: SymptomDraft,
  savedAt: Date = new Date()
): EpisodePayload {
  const name = truncated(draft.mainSymptom, NAME_MAX_LENGTH);
  return {
    // `validateDraft` refuses a nameless new symptom, so this is only ever a
    // fallback against a caller that skipped validation.
    name: name ?? 'Symptom',
    body_site: truncated(draft.site, NAME_MAX_LENGTH),
    first_noticed_date: draft.onsetDate ?? null,
    first_noticed_text: truncated(draft.onset, DESCRIPTOR_MAX_LENGTH),
    source: draft.mode,
    first_entry: entryPayload(draft, savedAt),
  };
}

// --- photos -----------------------------------------------------------------

export function withPhoto(
  draft: SymptomDraft,
  photo: LocalPhotoDraft
): LocalPhotoDraft[] {
  return [...(draft.photos ?? []), photo];
}

export function withoutPhoto(draft: SymptomDraft, clientPhotoId: string) {
  return (draft.photos ?? []).filter((photo) => photo.clientPhotoId !== clientPhotoId);
}

// --- onset ------------------------------------------------------------------

/**
 * Today, as the local calendar day, for the onset date picker's default.
 *
 * The same helper Today and the medication screens use, so one definition of
 * "the day the user is in" runs through the whole app.
 */
export function todayLocalDate(): string {
  return localDateString();
}

export const CHANGE_VALUES: ChangeState[] = ['improving', 'same', 'worsening', 'unsure'];
