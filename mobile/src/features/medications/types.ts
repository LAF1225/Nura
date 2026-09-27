/**
 * Medication scheduling, as the app sees it (PRD 5, sections 4, 8, 21 and 54).
 *
 * Three shapes are worth reading carefully, because they are what keep the
 * whole feature honest.
 *
 * `MedicationSchedule` is *when to remind*, and it carries its own IANA time
 * zone. A reminder is a wall-clock time where the person is -- "eight in the
 * morning" -- not an instant, which is why the zone travels with the schedule
 * rather than being assumed from the phone (PRD 5, section 12).
 *
 * `MedicationDose` is one concrete moment and what happened at it. `window` is
 * the server's own derivation from the clock and is never computed here: the
 * app does not decide a dose is overdue any more than it decides a robot is
 * online (PRD 5, section 54).
 *
 * `PendingDoseAction` is a client-only idea. The server has no notion of a
 * queued action; it is how the app remembers something the user did while
 * offline, so their tap is never silently lost (PRD 5, section 62).
 */

export type ScheduleType = 'daily' | 'specific_days';

export type DoseStatus =
  'scheduled' | 'snoozed' | 'taken' | 'skipped' | 'missed' | 'cancelled';

/** How an action reached the backend. Set by the server, never by a client. */
export type DoseSource = 'app' | 'robot_voice' | 'caregiver' | 'system';

/** Where a dose sits relative to now. Always the server's answer. */
export type DoseWindow = 'upcoming' | 'due' | 'overdue' | 'completed';

export type SkipReasonCode =
  'none' | 'feeling_unwell' | 'ran_out' | 'clinician_advised' | 'too_late' | 'other';

export type DoseAction = 'taken' | 'snooze' | 'skip';

/** Monday is 0, matching the backend and `Date.getDay()` shifted by one. */
export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6;

export interface ScheduleTime {
  id?: string;
  /** `HH:MM:SS` in the schedule's own zone. */
  timeOfDay: string;
  /** Null on an every-day schedule. */
  weekday: number | null;
}

export interface MedicationSchedule {
  id: string;
  profileId: string;
  medicationId: string;
  medicationName: string;
  medicationDose: string | null;
  scheduleType: ScheduleType;
  /** IANA name, e.g. `Europe/London`. */
  timezone: string;
  startDate: string;
  endDate: string | null;
  /** False while paused. Reminders stop; nothing recorded is affected. */
  isActive: boolean;
  pausedAt: string | null;
  times: ScheduleTime[];
}

export interface MedicationDose {
  id: string;
  medicationId: string;
  medicationName: string;
  medicationDose: string | null;
  scheduleId: string | null;
  /** ISO instant. */
  scheduledFor: string;
  /** The user's own calendar day, `YYYY-MM-DD`. */
  localDate: string;
  status: DoseStatus;
  window: DoseWindow;
  actionAt: string | null;
  source: DoseSource | null;
  skipReasonCode: SkipReasonCode | null;
  skipReasonText: string | null;
  snoozedUntil: string | null;
  snoozeCount: number;
  /** Recorded after the grace period. A fact about a time, not a judgement. */
  late: boolean;
  canSnooze: boolean;
  /** Client-only: this action is saved on the phone and not yet on the server. */
  syncStatus?: 'synced' | 'pending';
}

export interface DoseActionResult {
  dose: MedicationDose;
  /** False when the dose was already in the state asked for. */
  applied: boolean;
  supplyRemaining: number | null;
  lowSupply: boolean;
}

export interface Adherence {
  fromDate: string;
  toDate: string;
  taken: number;
  skipped: number;
  missed: number;
  total: number;
  /** Null when nothing was due. Never presented as a grade or a target. */
  percent: number | null;
}

export interface MedicationSupply {
  medicationId: string;
  medicationName: string;
  trackingEnabled: boolean;
  remainingDoses: number | null;
  refillThresholdDoses: number | null;
  lastRefillDate: string | null;
  /** At or below the user's own threshold. Never a figure Nura estimated. */
  low: boolean;
}

/** The medication block of `/api/v1/today` (PRD 5, section 53). */
export interface TodayMedications {
  nextDue: {
    doseId: string;
    medicationId: string;
    medicationName: string;
    medicationDose: string | null;
    scheduledFor: string;
    status: DoseStatus;
    window: DoseWindow;
    canSnooze: boolean;
  } | null;
  dueTodayCount: number;
  overdueCount: number;
  remainingTodayCount: number;
  lowSupply: {
    medicationId: string;
    medicationName: string;
    remainingDoses: number;
  }[];
  /** False when this profile has no schedules, so the card is not drawn. */
  hasSchedules: boolean;
}

// --- writing ----------------------------------------------------------------

export interface SchedulePayload {
  medicationId: string;
  scheduleType: ScheduleType;
  timezone: string;
  startDate: string;
  endDate: string | null;
  times: { timeOfDay: string; weekday: number | null }[];
}

export interface DoseActionInput {
  action: DoseAction;
  /** Snooze only. */
  minutes?: number;
  /** Skip only. */
  reasonCode?: SkipReasonCode;
  reasonText?: string | null;
  /**
   * When the user actually pressed the button. Sent so a queued action cannot
   * overwrite a newer one made elsewhere (PRD 5, section 63).
   */
  actionAt?: string;
}

/**
 * An action taken while the phone could not reach the backend.
 *
 * Queued per dose rather than appended as a log: pressing Taken and then Skip
 * on the same dose should send one final answer, not two, which is the same
 * shape the daily check-in queue uses.
 */
export interface PendingDoseAction extends DoseActionInput {
  doseId: string;
  /** Always set once queued, so the conflict rule has something to compare. */
  actionAt: string;
}
