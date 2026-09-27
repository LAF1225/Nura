/**
 * The symptom system, as the app sees it (PRD 6, sections 8-11, 29 and 72).
 *
 * Three shapes are worth reading carefully.
 *
 * `SymptomEpisode` and `SymptomEntry` mirror the two-level model: an episode is
 * one *bout* of one symptom, and an entry is one observation about it. A
 * follow-up is a new entry, never an edit of the episode (PRD 6, section 8).
 *
 * `SymptomDraft` is the one representation both entry flows use. The manual
 * form writes into it and so does the guided conversation, which is what makes
 * PRD 6 section 4's "same underlying structured record" true rather than
 * aspirational. There is deliberately no second draft type for chat.
 *
 * `LocalPhotoDraft` is a photo that exists only on this phone so far. It keeps
 * the local file URI until the upload is confirmed, because PRD 6 section 60
 * forbids reporting success before the backend has said so.
 */

export type EpisodeStatus = 'active' | 'resolved' | 'recurring' | 'historical';
export type ChangeState = 'improving' | 'same' | 'worsening' | 'unsure';
export type SymptomSource =
  | 'manual_app'
  | 'guided_app'
  | 'robot_voice_future'
  | 'caregiver_future'
  | 'import_future';
/** The two the app may write. The rest are readable but reserved. */
export type SymptomSourceInput = 'manual_app' | 'guided_app';
export type PhotoContentType = 'image/jpeg' | 'image/png' | 'image/heic' | 'image/heif';
export type WorseningReason =
  'reported_worsening' | 'severity_increase' | 'new_associated_symptom';

/** Whether something the user saved has reached the backend yet. */
export type SyncStatus = 'synced' | 'pending';

export interface SymptomPhoto {
  id: string;
  entryId: string;
  contentType: PhotoContentType;
  byteSize: number;
  createdAt: string;
  /** Client-only: `pending` while it is still queued for upload. */
  syncStatus?: SyncStatus;
  /** Client-only: where the file is on this phone, before it has uploaded. */
  localUri?: string;
}

export interface SymptomEntry {
  id: string;
  episodeId: string;
  /** When the observation is about, not when it was sent. */
  recordedAt: string;
  mainSymptom: string | null;
  site: string | null;
  onsetText: string | null;
  onsetAt: string | null;
  onsetDate: string | null;
  character: string | null;
  radiation: string | null;
  timing: string | null;
  severity: number | null;
  changeState: ChangeState | null;
  freeTextNote: string | null;
  associatedSymptoms: string[];
  exacerbatingFactors: string[];
  relievingFactors: string[];
  /** Preserved so nothing reads as more certain than the user was (s24). */
  negatedItems: string[];
  uncertainItems: string[];
  contextDependentItems: string[];
  source: SymptomSource;
  photos: SymptomPhoto[];
  createdAt: string;
  syncStatus?: SyncStatus;
}

/**
 * Cautious, non-diagnostic guidance, and why it is being shown.
 *
 * `urgent` is false in every shipped build: the red-flag rules exist on the
 * server, are tested, and are switched off until a clinician has reviewed them
 * (PRD 6, section 44).
 */
export interface SymptomSafety {
  worsening: boolean;
  reasons: WorseningReason[];
  notice: string | null;
  urgent: boolean;
}

export interface SymptomEpisode {
  id: string;
  profileId: string;
  name: string;
  bodySite: string | null;
  status: EpisodeStatus;
  firstNoticedAt: string | null;
  firstNoticedDate: string | null;
  firstNoticedYear: number | null;
  firstNoticedText: string | null;
  resolvedAt: string | null;
  /** The earlier bout this one follows, for a symptom that came back. */
  previousEpisodeId: string | null;
  source: SymptomSource;
  entryCount: number;
  latestEntry: SymptomEntry | null;
  safety: SymptomSafety;
  createdAt: string;
  updatedAt: string;
  /** Present on a detail read; absent on a list row. */
  entries?: SymptomEntry[];
}

export interface SymptomSummary {
  activeCount: number;
  worseningCount: number;
  recentUpdatesCount: number;
  hasEpisodes: boolean;
}

/** The symptom block of `/api/v1/today` (PRD 6, section 52). */
export interface TodaySymptoms {
  activeCount: number;
  worseningCount: number;
  mostRecent: {
    episodeId: string;
    name: string;
    severity: number | null;
    changeState: ChangeState | null;
    updatedAt: string;
  } | null;
  hasEpisodes: boolean;
}

// --- the shared draft -------------------------------------------------------

/**
 * A photo chosen on this phone, before it is anywhere else.
 *
 * `clientPhotoId` is generated when the photo is picked, so the id survives a
 * failed upload and a retry replaces nothing (PRD 6, section 61).
 */
export interface LocalPhotoDraft {
  clientPhotoId: string;
  localUri: string;
  contentType: PhotoContentType;
  byteSize: number;
}

/**
 * One symptom description, part-way through being written.
 *
 * Shared by the manual form and the guided conversation (PRD 6, section 72).
 * Every field is optional: a draft is something somebody is in the middle of,
 * and a type that demanded completeness would make an incomplete one
 * unrepresentable.
 */
export interface SymptomDraft {
  /** Set on a follow-up. Absent when this is a new symptom. */
  episodeId?: string;
  /** Which flow is filling this in, which becomes the stored `source`. */
  mode: SymptomSourceInput;
  /**
   * Generated when the draft starts, sent with the save, and kept until the
   * save is confirmed. This is the idempotency key (PRD 6, section 61).
   */
  clientEntryId: string;
  mainSymptom?: string;
  site?: string;
  /** The user's own wording -- "suddenly", "after exercise" (section 74). */
  onset?: string;
  /** `YYYY-MM-DD`, when a relative phrase could be resolved to a day. */
  onsetDate?: string;
  character?: string;
  radiation?: string;
  timing?: string;
  associatedSymptoms?: string[];
  exacerbatingFactors?: string[];
  relievingFactors?: string[];
  severity?: number;
  changeState?: ChangeState;
  note?: string;
  photos?: LocalPhotoDraft[];
  /** Explicitly denied, hedged, or true only in a context (section 24). */
  negatedItems?: string[];
  uncertainItems?: string[];
  contextDependentItems?: string[];
}

/** Every field the flows can capture. Used by the question engine. */
export type SymptomField =
  | 'mainSymptom'
  | 'onset'
  | 'site'
  | 'severity'
  | 'character'
  | 'radiation'
  | 'associatedSymptoms'
  | 'timing'
  | 'factors'
  | 'changeState';

// --- the guided conversation ------------------------------------------------

export interface ConversationTurn {
  id: string;
  speaker: 'nura' | 'user';
  text: string;
}

/** A tappable answer offered alongside the text box (PRD 6, section 67). */
export interface ConversationChoice {
  label: string;
  /** What gets written into the draft. Absent for "skip this". */
  value?: string;
}

export interface ConversationQuestion {
  field: SymptomField;
  prompt: string;
  choices: ConversationChoice[];
  /** True when the question can be answered by typing as well as tapping. */
  freeText: boolean;
}

/**
 * A concerning phrase Nura noticed but is not sure about (PRD 6, section 46).
 *
 * Confirmation is asked *before* anything follows from it, and a "no" records
 * the phrase as denied rather than leaving it as a maybe.
 */
export interface PendingConfirmation {
  /** The canonical phrase, which is what a safety rule matches on. */
  term: string;
  prompt: string;
}

export interface ConversationState {
  turns: ConversationTurn[];
  /** Fields already asked about, so nothing is asked twice (section 28). */
  asked: SymptomField[];
  /** What Nura is waiting for, or null once there is nothing left to ask. */
  current: ConversationQuestion | null;
  pendingConfirmation: PendingConfirmation | null;
  /** True once the conversation has nothing more to ask. */
  finished: boolean;
}

// --- writing ----------------------------------------------------------------

/** The body of a create-or-follow-up, as the API expects it. */
export interface EntryPayload {
  client_entry_id: string;
  source: SymptomSourceInput;
  recorded_at: string;
  main_symptom: string | null;
  site: string | null;
  onset_text: string | null;
  onset_date: string | null;
  character: string | null;
  radiation: string | null;
  timing: string | null;
  severity: number | null;
  change_state: ChangeState | null;
  free_text_note: string | null;
  associated_symptoms: string[];
  exacerbating_factors: string[];
  relieving_factors: string[];
  negated_items: string[];
  uncertain_items: string[];
  context_dependent_items: string[];
}

export interface EpisodePayload {
  name: string;
  body_site: string | null;
  first_noticed_date: string | null;
  first_noticed_text: string | null;
  source: SymptomSourceInput;
  first_entry: EntryPayload;
}

/**
 * A saved draft that has not reached the backend yet (PRD 6, sections 59-61).
 *
 * Holds everything needed to finish the job later: which episode it belongs to
 * (or that it starts a new one), the entry body, and the photos still to
 * upload. Keyed by `clientEntryId`, so a retry can never duplicate it.
 */
export interface PendingSymptomEntry {
  clientEntryId: string;
  /** Absent when this pending record would create a new episode. */
  episodeId?: string;
  episode?: EpisodePayload;
  /**
   * The resolved episode this one follows, when the save is a recurrence
   * (PRD 6, section 38). Set instead of `episodeId`, so a symptom that came back
   * while the phone was offline still lands as a *linked* new episode rather
   * than an unrelated one.
   */
  recurOf?: string;
  entry: EntryPayload;
  photos: LocalPhotoDraft[];
  /** For the "saved on this phone" line, and for ordering the queue. */
  savedAt: string;
  /** What the row should say it is about, without a server round trip. */
  displayName: string;
}
