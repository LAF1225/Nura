/**
 * The Today screen's data (PRD 3, sections 16, 50 and 60).
 *
 * Everything here mirrors `/api/v1/today`. Two rules the types encode:
 *
 *  - A check-in belongs to a *date*, and that date is the user's local
 *    calendar day as a `YYYY-MM-DD` string. Never a `Date`, which would drag a
 *    time and a zone along with it.
 *  - `syncStatus` is a client-only idea. The server has no notion of a pending
 *    check-in; it is how the app remembers something it has not managed to
 *    send yet (PRD 3, section 27).
 */
import type { ConnectionStatus } from './device';
import type { TodayAppointments } from '../features/appointments/types';
import type { TodayMedications } from '../features/medications/types';
import type { DailyLifeSummary } from '../features/productivity/types';
import type { TodaySymptoms } from '../features/symptoms/types';

export type { DailyLifeSummary, TodayAppointments, TodayMedications, TodaySymptoms };

export type WellbeingLevel = 'good' | 'okay' | 'not_great';

export const WELLBEING_LEVELS: readonly WellbeingLevel[] = ['good', 'okay', 'not_great'];

/** Whether a check-in has reached the backend yet. */
export type CheckInSyncStatus = 'synced' | 'pending';

export interface DailyCheckIn {
  /** The user's local calendar day, `YYYY-MM-DD`. */
  date: string;
  wellbeingLevel: WellbeingLevel;
  note: string | null;
  /** Absent on a purely local entry that has never been stored. */
  updatedAt?: string | null;
  syncStatus?: CheckInSyncStatus;
}

export interface TodayProfile {
  id: string;
  preferredName: string;
}

/** The robot as Today talks about it. Null when no robot is linked. */
export interface TodayDevice {
  deviceId: string;
  displayName: string;
  /** Always the backend's derivation. The app never decides this. */
  connectionStatus: ConnectionStatus;
  lastSeenAt: string | null;
  setupCompleted: boolean;
}

export interface TodayCheckInState {
  status: 'completed' | 'not_completed';
  checkIn: DailyCheckIn | null;
  /** Days in the recent window that have a check-in. A count, not a trend. */
  recentCompletedCount: number;
  recentWindowDays: number;
}

/**
 * An Important Today item.
 *
 * The shape was fixed in PRD 3 so later modules could fill the section without
 * the client changing how it renders. PRD 5 is the first to do it: medication
 * doses that are overdue, due, or next up, in that order (PRD 5, section 29).
 */
export interface TodayItem {
  id: string;
  type: string;
  title: string;
  subtitle?: string;
  dueAt?: string;
  priority?: 'normal' | 'important';
  actionRoute?: string;
}

/**
 * Every card Today can place. Adding one here, in the server registry and in
 * the client renderer map is all a later PRD needs to do (PRD 3, section 59).
 */
export type DashboardCardKey =
  | 'daily_checkin'
  | 'device_status'
  | 'quick_actions'
  | 'health_profile'
  | 'medications'
  | 'appointments'
  | 'symptoms'
  | 'care_requests'
  | 'routines'
  | 'hydration'
  | 'physiotherapy';

export interface DashboardCard {
  key: DashboardCardKey;
  title: string;
  /** False while the feature behind the card does not exist. Never rendered. */
  available: boolean;
  visible: boolean;
  position: number;
}

export interface TodaySummary {
  localDate: string;
  /** Null only for an account that has not created a profile yet. */
  profile: TodayProfile | null;
  dailyCheckIn: TodayCheckInState;
  /** Null when no robot is linked -- a normal state, not an error. */
  device: TodayDevice | null;
  cards: DashboardCard[];
  /**
   * The next dose and a few counts (PRD 5, section 53). Null only for an
   * account with no profile yet; `hasSchedules` is false for anyone who has
   * not set a reminder up, and the card is then not drawn at all.
   */
  medications: TodayMedications | null;
  /**
   * Two counts and the symptom written about most recently
   * (PRD 6, section 52). Null only for an account with no profile yet;
   * `hasEpisodes` is false for anybody who has never logged a symptom, and
   * the card is then not drawn at all.
   */
  symptoms: TodaySymptoms | null;
  /**
   * The next appointment and two counts (PRD 7, section 9). Null only for an
   * account with no profile yet. Unlike the two above, an empty one does *not*
   * hide the card: PRD 7 section 9 gives "No upcoming appointments" its own
   * wording, because checking when the next visit is, or noting one down, is a
   * reason people open the app.
   */
  appointments: TodayAppointments | null;
  /**
   * Tasks, reminders, routines and alarms (PRD 12, sections 18 and 19). Null
   * only for an account with no profile yet; `hasAnything` is false for
   * anybody who has never made one, and the card is then not drawn at all.
   */
  dailyLife: DailyLifeSummary | null;
  important: TodayItem[];
}

export interface DashboardPreferences {
  profileId: string | null;
  cards: DashboardCard[];
}
