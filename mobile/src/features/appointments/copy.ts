/**
 * Everything the appointment screens say (PRD 7, sections 3, 9-12, 18 and 45).
 *
 * Collected in one file so the whole voice of the feature can be read at once,
 * and so a test can assert what it never says: no diagnosis, no likelihood, no
 * cause, no treatment, no judgement of how well somebody is doing.
 *
 * Two rules run through all of it.
 *
 * **An appointment is not an alert.** PRD 7 section 10 says so outright. Nothing
 * here is urgent, nothing is a warning, and the strongest thing any sentence does
 * is offer to help somebody get ready.
 *
 * **Report wording belongs to the server.** The report's own sentences are built
 * by the backend and frozen into the snapshot (PRD 7, section 30), so a report
 * cannot be worded one way in the preview and another in the PDF. What is here is
 * the wording of the *screens around* it.
 */
import type {
  AdherenceReview,
  AppointmentStatus,
  AppointmentType,
  ChangeState,
  CheckInReview,
  PreparationStatus,
  ReportPeriodPreset,
  SymptomReview,
} from './types';

/** How each appointment type is written on screen (PRD 7, section 6). */
export const TYPE_LABELS: Record<AppointmentType, string> = {
  primary_care: 'GP or primary care',
  specialist: 'Specialist',
  therapy: 'Therapy',
  physiotherapy: 'Physiotherapy',
  dentist: 'Dentist',
  lab: 'Blood test or lab',
  imaging: 'Scan or imaging',
  other: 'Other',
};

/** The order the type chooser offers them in: commonest first. */
export const TYPE_ORDER: readonly AppointmentType[] = [
  'primary_care',
  'specialist',
  'physiotherapy',
  'therapy',
  'dentist',
  'lab',
  'imaging',
  'other',
];

export const STATUS_LABELS: Record<AppointmentStatus, string> = {
  scheduled: 'Scheduled',
  completed: 'Completed',
  cancelled: 'Cancelled',
  missed: 'Not attended',
};

/**
 * What the preparation state is called.
 *
 * "Not started" rather than "incomplete": an appointment nobody has prepared for
 * is a perfectly normal state and should not read as a failing.
 */
export const PREPARATION_LABELS: Record<PreparationStatus, string> = {
  not_started: 'Not prepared yet',
  in_progress: 'Preparation started',
  complete: 'Summary ready',
};

export const PERIOD_LABELS: Record<ReportPeriodPreset, string> = {
  since_last_visit: 'Since my last visit',
  '7_days': 'Last 7 days',
  '30_days': 'Last 30 days',
  '90_days': 'Last 90 days',
  custom: 'Choose dates',
};

export const PERIOD_ORDER: readonly ReportPeriodPreset[] = [
  'since_last_visit',
  '7_days',
  '30_days',
  '90_days',
  'custom',
];

/** What each report section switch is called (PRD 7, section 25). */
export const SECTION_LABELS: Record<string, string> = {
  conditions: 'Active conditions',
  allergies: 'Allergies',
  procedures: 'Recent procedures',
  blood_type: 'Blood type',
  medications: 'Current medications',
  adherence: 'Medication doses',
  daily_checkins: 'Daily check-ins',
  medical_notes: 'Medical notes',
  questions: 'Questions for the clinician',
};

export const CHANGE_LABELS: Record<ChangeState, string> = {
  improving: 'Improving',
  same: 'Unchanged',
  worsening: 'Worsening',
  unsure: 'Not sure',
};

// --- screen copy ------------------------------------------------------------

export const EMPTY_UPCOMING = 'No upcoming appointments.';
export const EMPTY_PAST = 'No past appointments yet.';
export const EMPTY_CANCELLED = 'No cancelled appointments.';

export const TODAY_CARD_TITLE = 'Next appointment';
export const ADD_APPOINTMENT = 'Add appointment';
export const PREPARE_ACTION = 'Prepare for appointment';

/**
 * The prompt PRD 7 section 12 suggests. An offer with a way to decline, and no
 * consequence attached to declining.
 */
export const PREPARE_PROMPT = 'Would you like to prepare your Nura health summary?';
export const PREPARE_LATER = 'Later';

/** Said above the review steps (PRD 7, section 3). */
export const PREPARE_INTRO =
  'Nura will show you what you have recorded so you can choose what to bring. ' +
  'Nothing is shared until you export it.';

/** Said above the content switches (PRD 7, section 25). */
export const SELECTION_INTRO = 'Only what you tick will appear in the summary.';

/** Said on the preview screen (PRD 7, sections 32 and 45). */
export const PREVIEW_INTRO =
  'This is exactly what the PDF will say. You can go back and change it.';

export const NO_HEALTH_DATA =
  'There is nothing recorded for this period yet. You can still add questions ' +
  'and make a summary with just those.';

/** Shown when generation is attempted with no connection (PRD 7, section 53). */
export const OFFLINE_REPORT =
  'Nura needs a connection to make the summary. Your selections are saved, so ' +
  'you can try again when you are back online.';

export const QUESTIONS_INTRO = 'Questions for your doctor';

/** Shown next to a question or appointment still on this phone (s53). */
export const PENDING_LABEL = 'Saved on this phone';
export const PENDING_HINT = 'This will sync when you are back online.';

export const APPENDIX_LABEL = 'Include detailed history appendix';
export const APPENDIX_HINT =
  'Adds the full symptom timeline and dose history after the one-page summary.';

export const SHARE_ACTION = 'Share or save PDF';
export const REGENERATE_ACTION = 'Regenerate';

/** Said beside Regenerate, so nobody fears losing what they already sent. */
export const REGENERATE_HINT = 'Makes a new version. Earlier versions are kept.';

export const DELETE_REPORT_CONFIRM =
  'Delete this version? Your health records are not affected.';

// --- sentences built from data -----------------------------------------------

/** "Dr Ahmed Khan · Cardiology", or whichever part exists. */
export function clinicianLine(
  name: string | null,
  specialty: string | null
): string | null {
  const parts = [name, specialty].filter(
    (part): part is string => typeof part === 'string' && part.length > 0
  );
  return parts.length === 0 ? null : parts.join(' · ');
}

export function upcomingCountSentence(count: number): string {
  if (count === 0) return EMPTY_UPCOMING;
  return count === 1 ? '1 upcoming appointment' : `${count} upcoming appointments`;
}

export function questionCountSentence(count: number): string {
  if (count === 0) return 'No questions added';
  return count === 1 ? '1 question added' : `${count} questions added`;
}

export function reportCountSentence(count: number): string {
  if (count === 0) return 'No summary generated';
  return count === 1 ? '1 summary generated' : `${count} summaries generated`;
}

/** "Report v2 · 2 October 2026, 9:15 AM" (PRD 7, section 31). */
export function reportVersionLine(version: number, generatedLabel: string): string {
  return `Report v${version} · ${generatedLabel}`;
}

/** "1 page" / "2 pages", or nothing when the server did not say. */
export function pageCountSentence(pageCount: number | null): string | null {
  if (pageCount === null || pageCount <= 0) return null;
  return pageCount === 1 ? '1 page' : `${pageCount} pages`;
}

/**
 * How a symptom reads on the review screen (PRD 7, section 15).
 *
 * Counts and the user's own answers. No ordering hint, no "significant", and
 * nothing that suggests one symptom matters more than another.
 */
export function symptomReviewLines(review: SymptomReview): string[] {
  const lines: string[] = [];

  if (review.entryCount === 0) {
    lines.push('Still ongoing · no entries in this period');
  } else {
    lines.push(
      review.entryCount === 1 ? 'Logged once' : `Logged ${review.entryCount} times`
    );
  }

  if (review.latestSeverity !== null) {
    lines.push(`Latest severity: ${review.latestSeverity}/10`);
  }
  if (review.latestChangeState !== null) {
    lines.push(`Change: ${CHANGE_LABELS[review.latestChangeState].toLowerCase()}`);
  }
  return lines;
}

/**
 * How the dose counts read (PRD 7, section 18).
 *
 * Counts, with the denominator in the same sentence. Never a percentage on this
 * screen, and never a word about whether it is good.
 */
export function adherenceSentence(adherence: AdherenceReview): string {
  if (adherence.total === 0) return 'No doses were scheduled in this period.';
  return `${adherence.taken} of ${adherence.total} scheduled doses marked taken`;
}

export function skippedSentence(adherence: AdherenceReview): string | null {
  const parts: string[] = [];
  if (adherence.skipped > 0) {
    parts.push(
      adherence.skipped === 1 ? '1 dose skipped' : `${adherence.skipped} doses skipped`
    );
  }
  if (adherence.missed > 0) {
    parts.push(
      adherence.missed === 1
        ? '1 dose not marked taken'
        : `${adherence.missed} doses not marked taken`
    );
  }
  return parts.length === 0 ? null : parts.join(' · ');
}

/** "Good: 8 days · Okay: 11 days · Not great: 4 days" (PRD 7, section 20). */
export function checkinSentence(review: CheckInReview): string {
  if (review.total === 0) return 'No check-ins recorded in this period.';
  const parts: string[] = [];
  const days = (count: number) => (count === 1 ? '1 day' : `${count} days`);
  if (review.good > 0) parts.push(`Good: ${days(review.good)}`);
  if (review.okay > 0) parts.push(`Okay: ${days(review.okay)}`);
  if (review.notGreat > 0) parts.push(`Not great: ${days(review.notGreat)}`);
  return parts.join(' · ');
}

/**
 * The one sentence on the Today card, below the title.
 *
 * "Tomorrow at 3:30 PM · Dr Ahmed Khan", built from what exists.
 */
export function todayCardSubtitle(
  whenLabel: string,
  clinicianName: string | null
): string {
  return clinicianName ? `${whenLabel} · ${clinicianName}` : whenLabel;
}
