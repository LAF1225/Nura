/**
 * How a dose reads on screen (PRD 5, sections 19, 24, 27, 34, 54 and 57).
 *
 * All of the user-facing wording for medications lives in this file, which is
 * what keeps it consistent -- and reviewable. Three rules govern every string
 * here:
 *
 * **Neutral, never guilt-oriented.** A dose nobody recorded "wasn't marked as
 * taken". It is not a failure, a lapse or a miss on the person's part, and no
 * streak, score or red state appears anywhere (PRD 5, section 24).
 *
 * **Recorded, never interpreted.** A skip reason is shown back exactly as it
 * was chosen. Nothing here concludes anything medical from it, and nothing
 * changes because of it (section 19).
 *
 * **Nothing that could be mistaken for advice.** Nura does not say whether to
 * take a late dose, double up, or stop. Where people plainly want an answer,
 * it says to ask the person who prescribed it -- that sentence is
 * `MISSED_DOSE_GUIDANCE`, and it is the only thing approaching advice that
 * PRD 5 section 57 permits.
 */
import type { Adherence, DoseWindow, MedicationDose, SkipReasonCode } from './types';

/**
 * The one piece of generic guidance PRD 5 section 57 allows. It names no
 * medication, suggests no action, and points at a clinician.
 */
export const MISSED_DOSE_GUIDANCE =
  'If you’re unsure what to do after missing a dose, follow the instructions from your clinician or pharmacist.';

/** Shown under a supply figure, because the figure came from a person. */
export const SUPPLY_CAVEAT = 'This is the count you entered, so treat it as approximate.';

export const SKIP_REASONS: { code: SkipReasonCode; label: string }[] = [
  { code: 'feeling_unwell', label: 'Feeling unwell' },
  { code: 'ran_out', label: 'Ran out' },
  { code: 'clinician_advised', label: 'Doctor advised' },
  { code: 'too_late', label: 'Forgot or too late' },
  { code: 'other', label: 'Other' },
  { code: 'none', label: 'Prefer not to say' },
];

export function skipReasonLabel(code: SkipReasonCode | null): string | null {
  if (code === null || code === 'none') return null;
  return SKIP_REASONS.find((reason) => reason.code === code)?.label ?? null;
}

export const SNOOZE_OPTIONS: { minutes: number; label: string }[] = [
  { minutes: 10, label: '10 minutes' },
  { minutes: 30, label: '30 minutes' },
  { minutes: 60, label: '1 hour' },
];

/** "Metformin — 500 mg", or just the name when no dose was recorded. */
export function doseTitle(dose: {
  medicationName: string;
  medicationDose: string | null;
}): string {
  return dose.medicationDose
    ? `${dose.medicationName} — ${dose.medicationDose}`
    : dose.medicationName;
}

/**
 * "8:00 AM" for an instant, in the phone's own zone.
 *
 * The *schedule* keeps its own zone so reminders fire at the intended local
 * time; a dose that has already been placed is an instant, and showing it
 * where the reader is standing is the only thing that makes sense.
 */
export function formatDoseTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  const hours = parsed.getHours();
  const minutes = String(parsed.getMinutes()).padStart(2, '0');
  const suffix = hours < 12 ? 'AM' : 'PM';
  const displayHour = hours % 12 === 0 ? 12 : hours % 12;
  return `${displayHour}:${minutes} ${suffix}`;
}

/** "14 September", for a history heading. */
export function formatDoseDay(localDate: string): string {
  const parsed = new Date(`${localDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return localDate;
  return parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'long' });
}

/** What the dose is waiting for -- its snooze, if it has one. */
export function dueAt(dose: MedicationDose): string {
  return dose.status === 'snoozed' && dose.snoozedUntil !== null
    ? dose.snoozedUntil
    : dose.scheduledFor;
}

/**
 * One line saying where this dose stands.
 *
 * A recorded dose says what was recorded; an unrecorded one says when it is
 * due. Nothing is phrased as a warning, and `missed` deliberately reads as
 * bookkeeping rather than as a reprimand (PRD 5, section 24).
 */
export function doseStatusLine(dose: MedicationDose): string {
  switch (dose.status) {
    case 'taken':
      return dose.late
        ? `Taken at ${formatDoseTime(dose.actionAt ?? dose.scheduledFor)}`
        : 'Taken';
    case 'skipped': {
      const reason = skipReasonLabel(dose.skipReasonCode);
      return reason === null ? 'Skipped' : `Skipped — ${reason.toLowerCase()}`;
    }
    case 'missed':
      return 'Wasn’t marked as taken';
    case 'snoozed':
      return `Snoozed until ${formatDoseTime(dueAt(dose))}`;
    case 'cancelled':
      return 'No longer scheduled';
    default:
      return `Due at ${formatDoseTime(dose.scheduledFor)}`;
  }
}

/** A short phrase for the window, used beside the time on the Today card. */
export function windowLabel(window: DoseWindow): string | null {
  switch (window) {
    case 'overdue':
      return 'Not marked as taken';
    case 'due':
      return 'Due now';
    case 'upcoming':
      return 'Coming up';
    default:
      return null;
  }
}

/** Still waiting for the person to record something. */
export function isWaiting(dose: MedicationDose): boolean {
  return (
    dose.status === 'scheduled' || dose.status === 'snoozed' || dose.status === 'missed'
  );
}

/**
 * "86% of scheduled doses were marked taken in the last 7 days."
 *
 * Returns the denominator in the sentence rather than a bare percentage, so
 * the number is never mistaken for a grade. Nothing labels it adequate or
 * inadequate, and there is no target (PRD 5, section 27).
 */
export function adherenceSentence(adherence: Adherence, days: number): string {
  if (adherence.total === 0) {
    return `No doses were scheduled in the last ${days} days.`;
  }
  const window = days === 1 ? 'day' : `${days} days`;
  return `${adherence.percent}% of scheduled doses were marked taken in the last ${window}.`;
}

/** "You have about 5 doses of Metformin left." Cautious on purpose (s34). */
export function lowSupplySentence(name: string, remaining: number): string {
  const doses = remaining === 1 ? '1 dose' : `${remaining} doses`;
  return `You have about ${doses} of ${name} left.`;
}

/** Groups a flat dose list by local day, newest day first (PRD 5, s26). */
export function groupByDay(
  doses: MedicationDose[]
): { localDate: string; doses: MedicationDose[] }[] {
  const days = new Map<string, MedicationDose[]>();
  for (const dose of doses) {
    const existing = days.get(dose.localDate);
    if (existing) {
      existing.push(dose);
    } else {
      days.set(dose.localDate, [dose]);
    }
  }
  return Array.from(days.entries())
    .sort((left, right) => right[0].localeCompare(left[0]))
    .map(([localDate, entries]) => ({
      localDate,
      doses: [...entries].sort((left, right) =>
        left.scheduledFor.localeCompare(right.scheduledFor)
      ),
    }));
}
