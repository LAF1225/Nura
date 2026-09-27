/**
 * Everything the symptom screens say, and the small functions that word it.
 *
 * (PRD 6, sections 7, 22, 23, 30, 36, 49 and 76.)
 *
 * One file, for the same reason the medication wording is one file: it is what
 * keeps eight screens feeling like one product rather than eight forms, and it
 * makes the tone requirements testable. A few tests in
 * `symptomCopy.test.ts` assert things about the sentences here -- that nothing
 * grades anybody, that severity is anchored rather than labelled, and that the
 * only clinician-pointing sentence appears once.
 *
 * Two tone rules run through all of it.
 *
 * **Nura describes, it does not assess.** "6 out of 10" is a number the user
 * chose; "moderate" would be Nura's interpretation of it, so severity is never
 * given a word (PRD 6, section 22).
 *
 * **A symptom is not a failure.** Nothing here congratulates somebody for
 * improving or worries at them for worsening. "You recorded this as worsening"
 * states a fact about what they did.
 */
import type {
  ChangeState,
  EpisodeStatus,
  SymptomDraft,
  SymptomEntry,
  SymptomEpisode,
} from './types';

// --- the severity scale -----------------------------------------------------

/** 0-10 inclusive (PRD 6, section 22). */
export const SEVERITY_MIN = 0;
export const SEVERITY_MAX = 10;

/**
 * The anchors, and only the anchors.
 *
 * PRD 6 section 22 asks for the scale to be anchored clearly. It deliberately
 * does *not* ask for the middle to be labelled, and labelling it would turn the
 * user's number into Nura's judgement of how bad things are.
 */
export const SEVERITY_ANCHOR_LOW = '0 — no symptom';
export const SEVERITY_ANCHOR_HIGH = '10 — the worst you can imagine';

export function severityLabel(severity: number | null | undefined): string | null {
  return severity === null || severity === undefined ? null : `${severity}/10`;
}

/** What a screen reader says for one point on the scale. */
export function severityAccessibilityLabel(value: number): string {
  if (value === SEVERITY_MIN) return '0, no symptom';
  if (value === SEVERITY_MAX) return '10, the worst you can imagine';
  return `${value} out of 10`;
}

// --- change state -----------------------------------------------------------

export const CHANGE_STATES: { value: ChangeState; label: string }[] = [
  { value: 'improving', label: 'Getting better' },
  { value: 'same', label: 'About the same' },
  { value: 'worsening', label: 'Getting worse' },
  // A real answer, stored as one: "I don't know" and "I didn't say" are
  // different things (PRD 6, section 23).
  { value: 'unsure', label: 'Not sure' },
];

export function changeLabel(state: ChangeState | null | undefined): string | null {
  if (!state) return null;
  return CHANGE_STATES.find((entry) => entry.value === state)?.label ?? null;
}

/**
 * A short marker that does not rely on colour (PRD 6, section 66).
 *
 * Arrows rather than a red/green dot: somebody who cannot distinguish the two
 * still reads the direction, and a screen reader reads the label beside it.
 */
export const CHANGE_MARKER: Record<ChangeState, string> = {
  improving: '↓',
  same: '=',
  worsening: '↑',
  unsure: '?',
};

// --- statuses ---------------------------------------------------------------

export const STATUS_LABEL: Record<EpisodeStatus, string> = {
  active: 'Ongoing',
  // Named for what the user did, not for an outcome: "resolved" in the data,
  // "ended" on screen, because Nura has no idea whether anything was cured.
  resolved: 'Ended',
  recurring: 'Come back',
  historical: 'Past',
};

export function isActiveStatus(status: EpisodeStatus): boolean {
  return status === 'active' || status === 'recurring';
}

// --- headings and empty states ----------------------------------------------

export const OVERVIEW_TITLE = 'Symptoms';
export const OVERVIEW_DESCRIPTION =
  'What you are experiencing, in your own words. A symptom is not the same as ' +
  'a diagnosed condition, so these are kept separately.';

export const TALK_ACTION = 'Talk to Nura';
export const MANUAL_ACTION = 'Log manually';

export const EMPTY_ACTIVE = 'Nothing active right now.';
export const EMPTY_HISTORY = 'Nothing logged yet.';
export const EMPTY_TODAY_CARD = 'No active symptoms logged.';

export const ACTIVE_HEADING = 'Active and recent';
export const HISTORY_HEADING = 'History';
export const REVIEW_TITLE = 'Review symptom';
export const REVIEW_HINT = 'Check this over. You can change anything before saving.';

// --- the questions, as the manual form asks them ----------------------------

/**
 * The manual form's wording, in PRD 6 section 25's order.
 *
 * The guided conversation asks the same things in the same order through
 * `conversation/questions.ts`, and the two share this wording so the flows
 * cannot end up asking the same question two different ways.
 */
export const FIELD_LABELS = {
  mainSymptom: 'What are you experiencing?',
  onset: 'When did it start?',
  site: 'Where do you feel it?',
  severity: 'How bad is it right now?',
  character: 'What does it feel like?',
  radiation: 'Does it move anywhere?',
  associatedSymptoms: 'Anything else along with it?',
  timing: 'When is it worse?',
  exacerbatingFactors: 'What makes it worse?',
  relievingFactors: 'What makes it better?',
  changeState: 'How is it compared with last time?',
  note: 'Anything else you want to remember?',
  photos: 'Photos',
} as const;

export const FIELD_HINTS = {
  mainSymptom: 'For example, headache, dizziness, or a rash.',
  onset: 'In your own words is fine — "this morning", "three days ago".',
  site: 'For example, behind both eyes, or my left knee.',
  character: 'For example, sharp, dull, burning, throbbing.',
  radiation: 'Leave this out if it does not apply.',
  associatedSymptoms: 'Separate several with a comma.',
  timing: 'For example, comes and goes, or worse at night.',
  note: 'Nura keeps this exactly as you write it.',
} as const;

/** The label every optional field carries, so nothing feels compulsory. */
export const OPTIONAL = '(optional)';

// --- summarising ------------------------------------------------------------

/** "Headache — 6/10", or just the name. Used on cards and in Today. */
export function episodeTitle(name: string, severity: number | null | undefined): string {
  const label = severityLabel(severity);
  return label ? `${name} — ${label}` : name;
}

/** Joins the parts of a second line, skipping the ones with nothing in them. */
export function joined(parts: (string | null | undefined)[]): string | null {
  const present = parts.filter((part): part is string => Boolean(part));
  return present.length > 0 ? present.join(' · ') : null;
}

/** A day as a person reads it, from a `YYYY-MM-DD` or an ISO instant. */
export function formatDay(value: string): string {
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'long' });
}

/** "14:30" on the user's own clock. */
export function formatTime(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/**
 * When an episode began, however precisely that is known.
 *
 * Reads back whatever precision was recorded and never invents one: a year
 * stays a year (PRD 6, section 15).
 */
export function onsetSentence(episode: SymptomEpisode): string | null {
  const wording = episode.firstNoticedText;
  const exact =
    episode.firstNoticedDate ??
    (episode.firstNoticedAt ? formatDay(episode.firstNoticedAt) : null);
  const structured = episode.firstNoticedDate
    ? formatDay(episode.firstNoticedDate)
    : exact;
  const year = episode.firstNoticedYear ? String(episode.firstNoticedYear) : null;

  // Both pieces survive: "suddenly, on 26 September" (PRD 6, section 74).
  const parts = [wording, structured ?? year].filter(Boolean);
  return parts.length > 0 ? `Started ${parts.join(', ')}` : null;
}

/** "Last logged today · 6/10 · Getting worse" -- the overview's second line. */
export function episodeSubtitle(episode: SymptomEpisode, today: string): string | null {
  const entry = episode.latestEntry;
  if (entry === null) return 'Nothing logged about it yet';

  const day = entry.recordedAt.slice(0, 10);
  const when = day === today ? 'Last logged today' : `Last logged ${formatDay(day)}`;
  return joined([when, severityLabel(entry.severity), changeLabel(entry.changeState)]);
}

/** "27 September, 14:30 — 6/10 — Getting worse" -- one history row. */
export function entryLine(entry: SymptomEntry): string {
  const when = `${formatDay(entry.recordedAt)}, ${formatTime(entry.recordedAt)}`;
  return (
    joined([when, severityLabel(entry.severity), changeLabel(entry.changeState)]) ?? when
  );
}

/** "2 active · 1 recorded as worsening", for the Health overview. */
export function summarySentence(activeCount: number, worseningCount: number): string {
  const active =
    activeCount === 1 ? '1 active symptom' : `${activeCount} active symptoms`;
  if (worseningCount === 0) return active;
  const worse =
    worseningCount === 1
      ? '1 recorded as worsening'
      : `${worseningCount} recorded as worsening`;
  return `${active} · ${worse}`;
}

// --- the review summary -----------------------------------------------------

export interface SummaryRow {
  label: string;
  value: string;
}

/**
 * The draft as a patient-friendly summary (PRD 6, sections 30 and 76).
 *
 * Only rows with something in them, so a sparse description reads as a short
 * summary rather than a form full of blanks -- which is what makes "you can
 * leave things out" feel true rather than merely permitted.
 *
 * Negated and uncertain items get their own rows. Showing "No nausea" back is
 * the whole point of keeping them: a summary that dropped them would be
 * claiming more certainty than the person expressed (PRD 6, section 24).
 */
export function summaryRows(draft: SymptomDraft): SummaryRow[] {
  const list = (values: string[] | undefined): string | null =>
    values && values.length > 0 ? values.join(', ') : null;

  const candidates: [string, string | null][] = [
    ['Symptom', draft.mainSymptom ?? null],
    [
      'Started',
      joined([draft.onset, draft.onsetDate ? formatDay(draft.onsetDate) : null]),
    ],
    ['Where', draft.site ?? null],
    ['How bad', severityLabel(draft.severity)],
    ['What it feels like', draft.character ?? null],
    ['Does it move', draft.radiation ?? null],
    ['Along with it', list(draft.associatedSymptoms)],
    ['When it is worse', draft.timing ?? null],
    ['Makes it worse', list(draft.exacerbatingFactors)],
    ['Makes it better', list(draft.relievingFactors)],
    ['Compared with last time', changeLabel(draft.changeState)],
    ['Not present', list(draft.negatedItems)],
    ['Not sure about', list(draft.uncertainItems)],
    ['Only sometimes', list(draft.contextDependentItems)],
    ['Note', draft.note ?? null],
  ];

  const rows = candidates
    .filter((pair): pair is [string, string] => Boolean(pair[1]))
    .map(([label, value]) => ({ label, value }));

  const photos = draft.photos?.length ?? 0;
  if (photos > 0) {
    rows.push({ label: 'Photos', value: photos === 1 ? '1 photo' : `${photos} photos` });
  }
  return rows;
}

// --- offline ----------------------------------------------------------------

export const PENDING_LABEL = 'Saved on this phone';
export const SAVE_OFFLINE_HINT =
  'If you have no signal, this is kept on your phone and sent when you are back ' +
  'online.';
export const PENDING_EXPLANATION =
  'This is saved here and will be sent when you are back online.';
export const PENDING_PHOTO_LABEL = 'Pending upload';

// --- destructive confirmations ----------------------------------------------

export const RESOLVE_TITLE = 'Mark this as ended?';
export const RESOLVE_BODY =
  'It will move out of your active list. Everything you have logged is kept.';

export const DELETE_EPISODE_TITLE = 'Delete this symptom?';
export const DELETE_EPISODE_BODY =
  'Everything you logged about it, including any photos, will be removed. ' +
  'If it has ended, mark it as ended instead — that keeps the history.';

export const DELETE_PHOTO_TITLE = 'Remove this photo?';
export const DELETE_PHOTO_BODY = 'It will be deleted from Nura. This cannot be undone.';

export const RECUR_TITLE = 'Has this come back?';
export const RECUR_BODY =
  'Nura will start a new record for this time round and keep the old one, so ' +
  'you can see both.';
