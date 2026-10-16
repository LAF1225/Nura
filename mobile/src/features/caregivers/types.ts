/**
 * Caregiver, suggestion, message and emergency-contact shapes (PRD 9).
 *
 * Wire fields are snake_case; everything the app works with is camelCase, and
 * `api.ts` is the only place the two meet.
 *
 * Four shapes here are worth noticing.
 *
 * **Every section of a caregiver's home is nullable, and null means absent.**
 * PRD 9 section 18 says the absence of a permission must not leak, so the
 * backend omits a section the caregiver was not granted rather than sending an
 * empty one. `null` here therefore means "not granted", and `[]` means "granted
 * and nothing recorded" -- two different things, and the screens say so
 * differently.
 *
 * **A role is a label.** `CaregiverRole` exists so a list of three people reads
 * sensibly. Nothing in this app branches on it to decide what to show: that is
 * `granted`, and the server decides it (section 10).
 *
 * **A suggestion carries its own diff.** `SuggestionDiff` comes from the server
 * because a reminder time only means something in its schedule's zone and an
 * appointment in its own -- the same reason PRD 7 renders appointment labels
 * server-side. There is no date arithmetic for either in this app.
 *
 * **There is no shape for a decline reason a caregiver could read.** Sections 25
 * and 88 keep a private note private, so `Suggestion` has no field for one and
 * only `OwnerSuggestion` does.
 */

import type { CaregiverRoutine } from '../productivity/types';

export type CaregiverRole =
  'primary_caregiver' | 'family' | 'caregiver' | 'emergency_contact' | 'other';

export type RelationshipStatus =
  'pending' | 'active' | 'declined' | 'revoked' | 'expired';

/** The categories a caregiver can be granted, one at a time (section 6). */
export type PermissionKey =
  | 'medications'
  | 'appointments'
  | 'symptoms'
  | 'reports'
  | 'safety_alerts'
  | 'communication'
  | 'routines'
  | 'general_health_summary';

export type SuggestionCategory = 'medications' | 'appointments' | 'routines';

/**
 * One routine as a caregiver sees it (PRD 12, section 16).
 *
 * Re-exported from the daily-life feature rather than defined again: the
 * caregiver home and the `care/routines` route return the same shape, and two
 * declarations of it would be two places to update.
 */
export type { CaregiverRoutine };

/**
 * The changes a caregiver may propose (section 85).
 *
 * This union is the whole list. `change_medication_dose`, `delete_condition`
 * and `change_diagnosis` are not here, and there is no screen that could ask
 * for one -- the same guarantee the backend makes by having no action type.
 */
export type SuggestionActionType =
  | 'change_medication_reminder_time'
  | 'pause_medication_reminder'
  | 'resume_medication_reminder'
  | 'add_appointment'
  | 'change_appointment_time';

export type SuggestionStatus =
  'pending' | 'approved' | 'declined' | 'expired' | 'cancelled';

export type MessageType = 'text' | 'check_in';

/** Who sent a line. `system` is the server, and nothing writes one yet. */
export type MessageSide = 'primary_user' | 'caregiver' | 'system';

/** The quick check-ins, split by who may send which (sections 35 and 36). */
export type CheckInCode =
  | 'im_okay'
  | 'not_great'
  | 'please_call_me'
  | 'need_help'
  | 'how_are_you'
  | 'thinking_of_you';

export type CaregiverNotificationKey =
  'messages' | 'appointment_updates' | 'suggestion_outcomes' | 'safety_alerts';

export type CareNotificationKey =
  | 'caregiver_messages'
  | 'suggestion_requests'
  | 'appointment_suggestions'
  | 'routine_suggestions';

/** Where an audio call is (section 40). Nothing reaches these yet. */
export type CallState = 'idle' | 'ringing' | 'connecting' | 'active' | 'ended' | 'failed';

export interface Permission {
  key: PermissionKey;
  allowed: boolean;
  /** The server's wording. Section 15 forbids vague labels. */
  label: string;
  description: string;
  /**
   * False when the category is granted but has nothing behind it:
   * `safety_alerts` until PRD 10, and `routines` until PRD 12 built them.
   * **Empty in this build**, because every granted permission now unlocks
   * something.
   */
  hasData: boolean;
}

export interface Caregiver {
  id: string;
  invitedName: string;
  role: CaregiverRole;
  roleLabel: string;
  status: RelationshipStatus;
  inviteEmail: string | null;
  invitePhone: string | null;
  inviteExpiresAt: string | null;
  acceptedAt: string | null;
  revokedAt: string | null;
  createdAt: string;
  permissions: Permission[];
  grantedCount: number;
}

export interface CaregiverList {
  caregivers: Caregiver[];
  hasAny: boolean;
}

export interface InviteCreated {
  caregiver: Caregiver;
  /**
   * The only copy. Nura has no way to send it, so the app shows it once for the
   * primary user to pass on -- see `copy.INVITE_DELIVERY`.
   */
  token: string;
  expiresAt: string;
  delivery: 'share_manually';
}

export interface InvitationPreview {
  invitedName: string;
  profileName: string;
  role: CaregiverRole;
  roleLabel: string;
  permissions: Permission[];
  /** Both lists section 15 asks for, as labels, already in order. */
  willAccess: string[];
  willNotAccess: string[];
  expiresAt: string;
}

export interface SupportedProfile {
  relationshipId: string;
  profileId: string;
  profileName: string;
  role: CaregiverRole;
  roleLabel: string;
  granted: PermissionKey[];
  notifications: Record<CaregiverNotificationKey, boolean>;
  acceptedAt: string | null;
}

export interface SuggestionDiff {
  subject: string;
  /** Null when the thing being proposed does not exist yet. */
  current: string | null;
  proposed: string;
  /** True when the target has gone, so Approve is not offered. */
  targetMissing: boolean;
}

export interface Suggestion {
  id: string;
  actionType: SuggestionActionType;
  actionLabel: string;
  category: SuggestionCategory;
  status: SuggestionStatus;
  diff: SuggestionDiff;
  caregiverName: string;
  createdAt: string;
  reviewedAt: string | null;
}

/** The primary user's own view, which may carry the note they wrote. */
export interface OwnerSuggestion extends Suggestion {
  declineNote: string | null;
}

export interface SuggestionList {
  suggestions: OwnerSuggestion[];
  pendingCount: number;
}

export interface FamilyMessage {
  id: string;
  messageType: 'text' | 'check_in' | 'photo' | 'system';
  side: MessageSide;
  /** On a check-in this is the sentence the server rendered from the code. */
  text: string | null;
  checkInCode: CheckInCode | null;
  createdAt: string;
  readAt: string | null;
  clientMessageId: string | null;
}

export interface FamilyThread {
  id: string;
  relationshipId: string;
  /** Who the thread is with, from this reader's side. */
  withName: string;
  unread: number;
  lastMessage: FamilyMessage | null;
  lastMessageAt: string | null;
}

export interface FamilyThreadList {
  threads: FamilyThread[];
}

export interface FamilyThreadDetail {
  thread: FamilyThread;
  messages: FamilyMessage[];
}

export interface EmergencyContact {
  id: string;
  name: string;
  phone: string | null;
  relationshipLabel: string | null;
  priority: number;
  isActive: boolean;
  /** True when this contact also uses Nura. Never settable from here. */
  hasAccount: boolean;
}

export interface EmergencyContactList {
  contacts: EmergencyContact[];
}

export interface EmergencyContactInput {
  name: string;
  phone?: string | null;
  relationshipLabel?: string | null;
  isActive?: boolean;
}

// --- the caregiver's home ----------------------------------------------------

export interface CaregiverMedication {
  medicationId: string;
  name: string;
  dose: string | null;
  scheduleLabel: string | null;
  remindersPaused: boolean;
  supplyLow: boolean;
  remainingDoses: number | null;
  /** What a reminder-time suggestion would target. Null with no schedule. */
  scheduleId: string | null;
}

export interface CaregiverAdherence {
  fromDate: string;
  toDate: string;
  taken: number;
  skipped: number;
  missed: number;
  /** Null when nothing was due. Never rendered as 0%. */
  percent: number | null;
}

export interface CaregiverAppointment {
  appointmentId: string;
  title: string;
  whenLabel: string;
  dayLabel: string;
  appointmentType: string;
  locationName: string | null;
  questionCount: number;
  preparationStatus: string;
}

export interface CaregiverSymptom {
  episodeId: string;
  name: string;
  status: string;
  severity: number | null;
  changeState: string | null;
  lastRecordedAt: string | null;
}

export interface CaregiverReport {
  reportId: string;
  appointmentTitle: string;
  version: number;
  generatedAt: string;
  status: string;
}

export interface CaregiverHealthCounts {
  activeConditions: number;
  activeMedications: number;
  activeSymptoms: number;
  allergies: number;
}

/**
 * The caregiver's Today (sections 17 and 60).
 *
 * Every optional field is `null` when the category was not granted, and the
 * screens treat that differently from an empty list: one says nothing about
 * whether anything is recorded, the other says there is nothing.
 */
export interface CaregiverHome {
  profileId: string;
  profileName: string;
  role: CaregiverRole;
  roleLabel: string;
  granted: PermissionKey[];
  /** Granted but with nothing behind it yet (section 94, and routines). */
  grantedWithoutData: PermissionKey[];
  medications: CaregiverMedication[] | null;
  adherence: CaregiverAdherence | null;
  dosesRemainingToday: number | null;
  dosesOverdue: number | null;
  appointments: CaregiverAppointment[] | null;
  symptoms: CaregiverSymptom[] | null;
  reports: CaregiverReport[] | null;
  /**
   * Routines and how today's runs are going (PRD 12, section 16). Absent --
   * null, not `[]` -- unless `routines` was granted, and it reaches routines
   * only: section 42 keeps tasks, alarms and personal reminders private.
   */
  routines: CaregiverRoutine[] | null;
  healthCounts: CaregiverHealthCounts | null;
  unreadMessages: number | null;
  /**
   * Safety alerts about this person, for this caregiver (PRD 10, s31 and 50).
   *
   * Null when `safety_alerts` was not granted -- the same omission rule every
   * other section here follows, so an absent key cannot be read to learn
   * whether anything has ever happened to this person.
   */
  safety: CaregiverSafety | null;
  pendingSuggestions: number;
  /** False in every deployment today, so no Call control is shown. */
  callingAvailable: boolean;
}

/** The safety block on a caregiver's home (PRD 10, sections 31 and 50). */
export interface CaregiverSafety {
  unreadCount: number;
  latestAlertId: string | null;
  latestEventLabel: string | null;
  latestAt: string | null;
  latestAcknowledged: boolean;
}

export interface CareSummary {
  caregiverCount: number;
  pendingInvitationCount: number;
  pendingSuggestionCount: number;
  unreadMessageCount: number;
  emergencyContactCount: number;
}

export interface CallSession {
  callId: string;
  state: CallState;
  credential: string | null;
  expiresAt: string | null;
}

/** What the invite form collects (section 11). */
export interface InviteInput {
  invitedName: string;
  role: CaregiverRole;
  email?: string | null;
  phone?: string | null;
  permissions: Partial<Record<PermissionKey, boolean>>;
}

/** What a caregiver proposes. The payload shape depends on the action. */
export interface SuggestionInput {
  actionType: SuggestionActionType;
  targetResourceId?: string | null;
  payload?: Record<string, unknown>;
  clientSuggestionId?: string | null;
}
