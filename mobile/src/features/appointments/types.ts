/**
 * Appointment, question and report shapes (PRD 7, sections 6, 22, 30 and 42).
 *
 * Wire fields are snake_case; everything the app works with is camelCase, and
 * `api.ts` is the only place the two meet.
 *
 * Two shapes here are worth noticing.
 *
 * **The date labels come from the server.** `dayLabel`, `timeLabel` and
 * `whenLabel` are rendered by the backend, not by the app. An appointment has to
 * be shown in *its own* time zone (PRD 7, section 42), and doing that in
 * JavaScript needs `Intl` with full time-zone data -- which is not something this
 * app can rely on across both platforms. The server has the IANA database, so
 * that is where the sentence is built.
 *
 * **A report carries its own content.** `snapshot` is the frozen text as it read
 * when the report was generated, and the preview renders exactly that -- so what
 * somebody approves on screen and what they export cannot disagree
 * (PRD 7, sections 30 and 32).
 */

export type AppointmentType =
  | 'primary_care'
  | 'specialist'
  | 'therapy'
  | 'physiotherapy'
  | 'dentist'
  | 'lab'
  | 'imaging'
  | 'other';

export type AppointmentStatus = 'scheduled' | 'completed' | 'cancelled' | 'missed';

export type PreparationStatus = 'not_started' | 'in_progress' | 'complete';

export type ReportStatus = 'pending' | 'ready' | 'failed';

export type ReportPeriodPreset =
  'since_last_visit' | '7_days' | '30_days' | '90_days' | 'custom';

/** The sections a user may switch on or off (PRD 7, section 25). */
export type ReportSectionKey =
  | 'conditions'
  | 'allergies'
  | 'procedures'
  | 'blood_type'
  | 'medications'
  | 'adherence'
  | 'daily_checkins'
  | 'medical_notes'
  | 'questions';

export type ChangeState = 'improving' | 'same' | 'worsening' | 'unsure';

export type WellbeingLevel = 'good' | 'okay' | 'not_great';

/** Which history list an appointment belongs to (PRD 7, section 41). */
export type AppointmentScope = 'upcoming' | 'past' | 'cancelled';

export interface ClinicianBrief {
  id: string;
  name: string;
  specialty: string | null;
}

export interface Appointment {
  id: string;
  profileId: string;
  title: string;
  appointmentType: AppointmentType;
  status: AppointmentStatus;
  preparationStatus: PreparationStatus;
  /** The instant, as ISO. Shown through the labels below, not formatted here. */
  scheduledAt: string;
  /** An IANA zone name, e.g. `Europe/London`. */
  timezone: string;
  /** The appointment's date in its own zone. */
  localDate: string;
  dayLabel: string;
  timeLabel: string;
  whenLabel: string;
  /** "Today", "Tomorrow", "Yesterday", or null for anything further off. */
  relativeDay: string | null;
  clinician: ClinicianBrief | null;
  locationName: string | null;
  address: string | null;
  phone: string | null;
  notes: string | null;
  visitNotes: string | null;
  followUpDate: string | null;
  remindersEnabled: boolean;
  cancelledAt: string | null;
  completedAt: string | null;
  questionCount: number;
  reportCount: number;
  createdAt: string;
  updatedAt: string;
  /** Present on a detail response. */
  questions?: AppointmentQuestion[];
  reports?: AppointmentReport[];
  /** Set for an appointment saved on this phone and not yet on the server. */
  syncStatus?: 'synced' | 'pending';
}

export interface AppointmentQuestion {
  id: string;
  appointmentId: string;
  text: string;
  position: number;
  isAnswered: boolean;
  answerNote: string | null;
  createdAt: string;
  updatedAt: string;
  syncStatus?: 'synced' | 'pending';
}

export interface ReportPeriod {
  start: string;
  end: string;
  label: string;
  preset: ReportPeriodPreset;
  /** What was asked for, which is not always what was applied. */
  requestedPreset: ReportPeriodPreset;
  /** One sentence saying why a request could not be honoured, or null. */
  note: string | null;
  sinceLabel: string | null;
  days: number;
}

export interface SymptomNoteOption {
  entryId: string;
  recordedAt: string;
  text: string;
}

export interface SymptomReview {
  episodeId: string;
  name: string;
  bodySite: string | null;
  status: string;
  isOngoing: boolean;
  entryCount: number;
  firstNoticedLabel: string | null;
  latestSeverity: number | null;
  severityMin: number | null;
  severityMax: number | null;
  latestChangeState: ChangeState | null;
  associatedSymptoms: string[];
  exacerbatingFactors: string[];
  relievingFactors: string[];
  negatedItems: string[];
  uncertainItems: string[];
  contextDependentItems: string[];
  notes: SymptomNoteOption[];
  photoCount: number;
}

export interface MedicationReview {
  medicationId: string;
  name: string;
  displayName: string;
  dose: string | null;
  doseUnit: string | null;
  frequency: string | null;
  reason: string | null;
  isActive: boolean;
}

export interface SkipNote {
  doseId: string;
  localDate: string;
  medicationName: string;
  reasonCode: string | null;
  reasonText: string | null;
}

export interface AdherenceReview {
  fromDate: string;
  toDate: string;
  taken: number;
  skipped: number;
  missed: number;
  total: number;
  /** Never labelled adequate or inadequate (PRD 7, section 18). */
  percent: number | null;
  skipNotes: SkipNote[];
}

export interface CheckInNoteOption {
  checkinDate: string;
  wellbeingLevel: WellbeingLevel;
  note: string;
}

export interface CheckInReview {
  good: number;
  okay: number;
  notGreat: number;
  total: number;
  daysInPeriod: number;
  notes: CheckInNoteOption[];
}

export interface ConditionItem {
  conditionId: string;
  name: string;
  status: string;
  diagnosedLabel: string | null;
}

export interface AllergyItem {
  allergyId: string;
  allergen: string;
  reaction: string | null;
  severity: string;
}

export interface ProcedureItem {
  procedureId: string;
  name: string;
  performedLabel: string | null;
}

export interface MedicalNoteItem {
  noteId: string;
  title: string;
  body: string;
  category: string;
}

export interface BaselineReview {
  conditions: ConditionItem[];
  allergies: AllergyItem[];
  procedures: ProcedureItem[];
  bloodType: string | null;
}

/** A deterministic prompt the user may accept (PRD 7, section 24). */
export interface QuestionSuggestion {
  key: string;
  prompt: string;
  questionText: string;
  reason: string;
}

export interface ReportSelection {
  include: Record<ReportSectionKey, boolean>;
  symptomEpisodeIds: string[];
  symptomNoteEntryIds: string[];
  /** Null means "the active ones"; an empty list means none. */
  medicationIds: string[] | null;
  checkinNoteDates: string[];
  medicalNoteIds: string[];
  focus: string | null;
  includeAppendix: boolean;
  includeSkipReasonNotes: boolean;
}

export interface Preparation {
  appointment: Appointment;
  period: ReportPeriod;
  symptoms: SymptomReview[];
  medications: MedicationReview[];
  adherence: AdherenceReview | null;
  dailyCheckins: CheckInReview | null;
  baseline: BaselineReview | null;
  medicalNotes: MedicalNoteItem[];
  questions: AppointmentQuestion[];
  suggestions: QuestionSuggestion[];
  /** False for an appointment with nothing recorded to review (s46). */
  hasHealthData: boolean;
  defaultSelection: ReportSelection;
}

/** One item of report content: a titled block, or a bullet. */
export interface ReportItem {
  title: string | null;
  lines: string[];
}

export interface ReportSection {
  key: string;
  heading: string;
  items: ReportItem[];
}

/**
 * A report's frozen content. Rendered by the preview and by the PDF, from the
 * same stored copy (PRD 7, sections 30 and 32).
 */
export interface ReportSnapshot {
  schemaVersion: number;
  title: string;
  generatedAt: string;
  header: {
    patient: string;
    lines: string[];
    periodLabel: string;
  };
  period: {
    start: string;
    end: string;
    label: string;
    preset: string;
    requestedPreset: string;
    fallbackReason: string | null;
    note: string | null;
  };
  summarySections: ReportSection[];
  appendixSections: ReportSection[];
  includeAppendix: boolean;
  summaryCondensed: boolean;
  footerLines: string[];
}

export interface AppointmentReport {
  id: string;
  appointmentId: string;
  version: number;
  status: ReportStatus;
  periodStart: string;
  periodEnd: string;
  periodPreset: ReportPeriodPreset;
  periodLabel: string;
  includeAppendix: boolean;
  generatedAt: string;
  generatedLabel: string;
  byteSize: number | null;
  pageCount: number | null;
  /** "Nura_Health_Summary_2026-10-02.pdf" (PRD 7, section 33). */
  fileName: string;
  selection: ReportSelection;
  /** Present on a single-report response, absent in a list. */
  snapshot?: ReportSnapshot;
}

/** The appointment block of the Today response (PRD 7, section 9). */
export interface TodayAppointment {
  appointmentId: string;
  title: string;
  appointmentType: AppointmentType;
  scheduledAt: string;
  timezone: string;
  whenLabel: string;
  relativeDay: string | null;
  clinicianName: string | null;
  clinicianSpecialty: string | null;
  locationName: string | null;
  preparationStatus: PreparationStatus;
  questionCount: number;
  reportCount: number;
}

export interface TodayAppointments {
  next: TodayAppointment | null;
  upcomingCount: number;
  /** False for somebody who has never added one. The card still renders. */
  hasAppointments: boolean;
}

export interface AppointmentSummary {
  profileId: string;
  upcomingCount: number;
  pastCount: number;
  cancelledCount: number;
  hasAppointments: boolean;
  next: TodayAppointment | null;
}

/** What the form collects, before it becomes a request (PRD 7, section 8). */
export interface AppointmentDraft {
  /** Generated on this device, so a retry cannot create two appointments. */
  clientAppointmentId: string;
  title: string;
  /** `YYYY-MM-DD`, as typed. */
  date: string;
  /** `HH:MM` on a 24-hour clock, as typed. */
  time: string;
  timezone: string;
  appointmentType: AppointmentType;
  clinicianId: string | null;
  locationName: string;
  address: string;
  phone: string;
  notes: string;
  remindersEnabled: boolean;
}

/** The request body for creating or editing an appointment. */
export interface AppointmentPayload {
  title: string;
  scheduled_at: string;
  timezone: string;
  appointment_type: AppointmentType;
  clinician_id: string | null;
  location_name: string | null;
  address: string | null;
  phone: string | null;
  notes: string | null;
  reminders_enabled: boolean;
  client_appointment_id?: string;
}

/** An appointment saved on this phone and not yet accepted (s53). */
export interface PendingAppointment {
  clientAppointmentId: string;
  payload: AppointmentPayload;
  savedAt: string;
  /** What to show in the pending row. Never the notes. */
  displayTitle: string;
}

/** A question added on this phone and not yet accepted (s53). */
export interface PendingQuestion {
  clientQuestionId: string;
  appointmentId: string;
  text: string;
  savedAt: string;
}
