/**
 * Appointment endpoints (PRD 7, sections 48-52).
 *
 * Every path is nested under the profile the records belong to, because that is
 * what they belong to -- not to the account that is signed in.
 *
 * Responses are parsed rather than cast. The fields the app reasons about -- a
 * status, a preparation state, whether a report is ready -- are checked and given
 * safe fallbacks, so a field the server renames cannot turn into a screen that
 * silently shows the wrong thing.
 *
 * A report's PDF is fetched through `reportPdfPath` plus a bearer token. There
 * is no public or signed URL anywhere in this module (PRD 7, section 52).
 */
import { apiRequest, mediaSource } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  AdherenceReview,
  AllergyItem,
  Appointment,
  AppointmentPayload,
  AppointmentQuestion,
  AppointmentReport,
  AppointmentScope,
  AppointmentStatus,
  AppointmentSummary,
  AppointmentType,
  BaselineReview,
  ChangeState,
  CheckInReview,
  ClinicianBrief,
  ConditionItem,
  MedicalNoteItem,
  MedicationReview,
  Preparation,
  PreparationStatus,
  ProcedureItem,
  QuestionSuggestion,
  ReportPeriod,
  ReportPeriodPreset,
  ReportSection,
  ReportSectionKey,
  ReportSelection,
  ReportSnapshot,
  ReportStatus,
  SymptomReview,
  TodayAppointment,
  TodayAppointments,
  WellbeingLevel,
} from './types';

const APPOINTMENT_TYPES: readonly AppointmentType[] = [
  'primary_care',
  'specialist',
  'therapy',
  'physiotherapy',
  'dentist',
  'lab',
  'imaging',
  'other',
];
const STATUSES: readonly AppointmentStatus[] = [
  'scheduled',
  'completed',
  'cancelled',
  'missed',
];
const PREPARATION_STATUSES: readonly PreparationStatus[] = [
  'not_started',
  'in_progress',
  'complete',
];
const REPORT_STATUSES: readonly ReportStatus[] = ['pending', 'ready', 'failed'];
const PERIOD_PRESETS: readonly ReportPeriodPreset[] = [
  'since_last_visit',
  '7_days',
  '30_days',
  '90_days',
  'custom',
];
const CHANGE_STATES: readonly ChangeState[] = [
  'improving',
  'same',
  'worsening',
  'unsure',
];
const WELLBEING_LEVELS: readonly WellbeingLevel[] = ['good', 'okay', 'not_great'];
export const REPORT_SECTION_KEYS: readonly ReportSectionKey[] = [
  'conditions',
  'allergies',
  'procedures',
  'blood_type',
  'medications',
  'adherence',
  'daily_checkins',
  'medical_notes',
  'questions',
];

// --- small parsing helpers --------------------------------------------------

function object(value: unknown, endpoint: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new ApiError('server', `Unexpected response shape from ${endpoint}.`);
  }
  return value as Record<string, unknown>;
}

function requiredString(
  body: Record<string, unknown>,
  key: string,
  endpoint: string
): string {
  const value = body[key];
  if (typeof value !== 'string' || value.length === 0) {
    throw new ApiError('server', `${endpoint} response is missing ${key}.`);
  }
  return value;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function count(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function nullableCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function maybeOneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

// --- parsing ----------------------------------------------------------------

function parseClinician(raw: unknown): ClinicianBrief | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, '/appointments');
  return {
    id: requiredString(body, 'id', '/appointments'),
    name: text(body.name) ?? 'Clinician',
    specialty: text(body.specialty),
  };
}

export function parseQuestion(raw: unknown, endpoint: string): AppointmentQuestion {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    appointmentId: requiredString(body, 'appointment_id', endpoint),
    text: text(body.text) ?? '',
    position: count(body.position),
    isAnswered: body.is_answered === true,
    answerNote: text(body.answer_note),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    updatedAt: text(body.updated_at) ?? new Date().toISOString(),
    syncStatus: 'synced',
  };
}

export function parseSelection(raw: unknown): ReportSelection {
  const body =
    raw === null || raw === undefined ? {} : object(raw, '/appointments/reports');
  const include = {} as Record<ReportSectionKey, boolean>;
  const sent =
    body.include === null || body.include === undefined
      ? {}
      : object(body.include, '/appointments/reports');
  for (const key of REPORT_SECTION_KEYS) {
    include[key] = sent[key] === true;
  }
  const medicationIds = body.medication_ids;

  return {
    include,
    symptomEpisodeIds: stringList(body.symptom_episode_ids),
    symptomNoteEntryIds: stringList(body.symptom_note_entry_ids),
    medicationIds:
      medicationIds === null || medicationIds === undefined
        ? null
        : stringList(medicationIds),
    checkinNoteDates: stringList(body.checkin_note_dates),
    medicalNoteIds: stringList(body.medical_note_ids),
    focus: text(body.focus),
    includeAppendix: body.include_appendix === true,
    includeSkipReasonNotes: body.include_skip_reason_notes === true,
  };
}

function parseSection(raw: unknown, endpoint: string): ReportSection {
  const body = object(raw, endpoint);
  return {
    key: text(body.key) ?? '',
    heading: text(body.heading) ?? '',
    items: list(body.items).map((item) => {
      const entry = object(item, endpoint);
      return { title: text(entry.title), lines: stringList(entry.lines) };
    }),
  };
}

export function parseSnapshot(raw: unknown, endpoint: string): ReportSnapshot {
  const body = object(raw, endpoint);
  const header = object(body.header ?? {}, endpoint);
  const period = object(body.period ?? {}, endpoint);

  return {
    schemaVersion: count(body.schema_version),
    title: text(body.title) ?? 'Nura Health Summary',
    generatedAt: text(body.generated_at) ?? new Date().toISOString(),
    header: {
      patient: text(header.patient) ?? '',
      lines: stringList(header.lines),
      periodLabel: text(header.period_label) ?? '',
    },
    period: {
      start: text(period.start) ?? '',
      end: text(period.end) ?? '',
      label: text(period.label) ?? '',
      preset: text(period.preset) ?? 'custom',
      requestedPreset: text(period.requested_preset) ?? 'custom',
      fallbackReason: text(period.fallback_reason),
      note: text(period.note),
    },
    summarySections: list(body.summary_sections).map((entry) =>
      parseSection(entry, endpoint)
    ),
    appendixSections: list(body.appendix_sections).map((entry) =>
      parseSection(entry, endpoint)
    ),
    includeAppendix: body.include_appendix === true,
    summaryCondensed: body.summary_condensed === true,
    footerLines: stringList(body.footer_lines),
  };
}

export function parseReport(raw: unknown, endpoint: string): AppointmentReport {
  const body = object(raw, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    appointmentId: requiredString(body, 'appointment_id', endpoint),
    version: count(body.version),
    status: oneOf(body.status, REPORT_STATUSES, 'pending'),
    periodStart: text(body.period_start) ?? '',
    periodEnd: text(body.period_end) ?? '',
    periodPreset: oneOf(body.period_preset, PERIOD_PRESETS, 'custom'),
    periodLabel: text(body.period_label) ?? '',
    includeAppendix: body.include_appendix === true,
    generatedAt: text(body.generated_at) ?? new Date().toISOString(),
    generatedLabel: text(body.generated_label) ?? '',
    byteSize: nullableCount(body.byte_size),
    pageCount: nullableCount(body.page_count),
    fileName: text(body.file_name) ?? 'Nura_Health_Summary.pdf',
    selection: parseSelection(body.selection),
    snapshot:
      body.snapshot === null || body.snapshot === undefined
        ? undefined
        : parseSnapshot(body.snapshot, endpoint),
  };
}

export function parseAppointment(raw: unknown, endpoint: string): Appointment {
  const body = object(raw, endpoint);
  const questions = body.questions;
  const reports = body.reports;

  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    title: text(body.title) ?? 'Appointment',
    appointmentType: oneOf(body.appointment_type, APPOINTMENT_TYPES, 'other'),
    status: oneOf(body.status, STATUSES, 'scheduled'),
    preparationStatus: oneOf(
      body.preparation_status,
      PREPARATION_STATUSES,
      'not_started'
    ),
    scheduledAt: text(body.scheduled_at) ?? new Date().toISOString(),
    timezone: text(body.timezone) ?? 'UTC',
    localDate: text(body.local_date) ?? '',
    dayLabel: text(body.day_label) ?? '',
    timeLabel: text(body.time_label) ?? '',
    whenLabel: text(body.when_label) ?? '',
    relativeDay: text(body.relative_day),
    clinician: parseClinician(body.clinician),
    locationName: text(body.location_name),
    address: text(body.address),
    phone: text(body.phone),
    notes: text(body.notes),
    visitNotes: text(body.visit_notes),
    followUpDate: text(body.follow_up_date),
    remindersEnabled: body.reminders_enabled !== false,
    cancelledAt: text(body.cancelled_at),
    completedAt: text(body.completed_at),
    questionCount: count(body.question_count),
    reportCount: count(body.report_count),
    createdAt: text(body.created_at) ?? new Date().toISOString(),
    updatedAt: text(body.updated_at) ?? new Date().toISOString(),
    questions: Array.isArray(questions)
      ? questions.map((entry) => parseQuestion(entry, endpoint))
      : undefined,
    reports: Array.isArray(reports)
      ? reports.map((entry) => parseReport(entry, endpoint))
      : undefined,
    syncStatus: 'synced',
  };
}

function parsePeriod(raw: unknown, endpoint: string): ReportPeriod {
  const body = object(raw, endpoint);
  return {
    start: text(body.start) ?? '',
    end: text(body.end) ?? '',
    label: text(body.label) ?? '',
    preset: oneOf(body.preset, PERIOD_PRESETS, 'custom'),
    requestedPreset: oneOf(body.requested_preset, PERIOD_PRESETS, 'custom'),
    note: text(body.note),
    sinceLabel: text(body.since_label),
    days: count(body.days),
  };
}

function parseSymptomReview(raw: unknown, endpoint: string): SymptomReview {
  const body = object(raw, endpoint);
  return {
    episodeId: requiredString(body, 'episode_id', endpoint),
    name: text(body.name) ?? 'Symptom',
    bodySite: text(body.body_site),
    status: text(body.status) ?? 'active',
    isOngoing: body.is_ongoing === true,
    entryCount: count(body.entry_count),
    firstNoticedLabel: text(body.first_noticed_label),
    latestSeverity: nullableCount(body.latest_severity),
    severityMin: nullableCount(body.severity_min),
    severityMax: nullableCount(body.severity_max),
    latestChangeState: maybeOneOf(body.latest_change_state, CHANGE_STATES),
    associatedSymptoms: stringList(body.associated_symptoms),
    exacerbatingFactors: stringList(body.exacerbating_factors),
    relievingFactors: stringList(body.relieving_factors),
    negatedItems: stringList(body.negated_items),
    uncertainItems: stringList(body.uncertain_items),
    contextDependentItems: stringList(body.context_dependent_items),
    notes: list(body.notes).map((entry) => {
      const note = object(entry, endpoint);
      return {
        entryId: requiredString(note, 'entry_id', endpoint),
        recordedAt: text(note.recorded_at) ?? '',
        text: text(note.text) ?? '',
      };
    }),
    photoCount: count(body.photo_count),
  };
}

function parseMedicationReview(raw: unknown, endpoint: string): MedicationReview {
  const body = object(raw, endpoint);
  return {
    medicationId: requiredString(body, 'medication_id', endpoint),
    name: text(body.name) ?? '',
    displayName: text(body.display_name) ?? text(body.name) ?? '',
    dose: text(body.dose),
    doseUnit: text(body.dose_unit),
    frequency: text(body.frequency),
    reason: text(body.reason),
    isActive: body.is_active !== false,
  };
}

function parseAdherence(raw: unknown, endpoint: string): AdherenceReview | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, endpoint);
  return {
    fromDate: text(body.from_date) ?? '',
    toDate: text(body.to_date) ?? '',
    taken: count(body.taken),
    skipped: count(body.skipped),
    missed: count(body.missed),
    total: count(body.total),
    percent: nullableCount(body.percent),
    skipNotes: list(body.skip_notes).map((entry) => {
      const note = object(entry, endpoint);
      return {
        doseId: requiredString(note, 'dose_id', endpoint),
        localDate: text(note.local_date) ?? '',
        medicationName: text(note.medication_name) ?? '',
        reasonCode: text(note.reason_code),
        reasonText: text(note.reason_text),
      };
    }),
  };
}

function parseCheckins(raw: unknown, endpoint: string): CheckInReview | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, endpoint);
  return {
    good: count(body.good),
    okay: count(body.okay),
    notGreat: count(body.not_great),
    total: count(body.total),
    daysInPeriod: count(body.days_in_period),
    notes: list(body.notes).map((entry) => {
      const note = object(entry, endpoint);
      return {
        checkinDate: text(note.checkin_date) ?? '',
        wellbeingLevel: oneOf(note.wellbeing_level, WELLBEING_LEVELS, 'okay'),
        note: text(note.note) ?? '',
      };
    }),
  };
}

function parseBaseline(raw: unknown, endpoint: string): BaselineReview | null {
  if (raw === null || raw === undefined) return null;
  const body = object(raw, endpoint);
  return {
    conditions: list(body.conditions).map((entry): ConditionItem => {
      const item = object(entry, endpoint);
      return {
        conditionId: requiredString(item, 'condition_id', endpoint),
        name: text(item.name) ?? '',
        status: text(item.status) ?? 'active',
        diagnosedLabel: text(item.diagnosed_label),
      };
    }),
    allergies: list(body.allergies).map((entry): AllergyItem => {
      const item = object(entry, endpoint);
      return {
        allergyId: requiredString(item, 'allergy_id', endpoint),
        allergen: text(item.allergen) ?? '',
        reaction: text(item.reaction),
        severity: text(item.severity) ?? 'unknown',
      };
    }),
    procedures: list(body.procedures).map((entry): ProcedureItem => {
      const item = object(entry, endpoint);
      return {
        procedureId: requiredString(item, 'procedure_id', endpoint),
        name: text(item.name) ?? '',
        performedLabel: text(item.performed_label),
      };
    }),
    bloodType: text(body.blood_type),
  };
}

export function parsePreparation(raw: unknown, endpoint: string): Preparation {
  const body = object(raw, endpoint);
  return {
    appointment: parseAppointment(body.appointment, endpoint),
    period: parsePeriod(body.period, endpoint),
    symptoms: list(body.symptoms).map((entry) => parseSymptomReview(entry, endpoint)),
    medications: list(body.medications).map((entry) =>
      parseMedicationReview(entry, endpoint)
    ),
    adherence: parseAdherence(body.adherence, endpoint),
    dailyCheckins: parseCheckins(body.daily_checkins, endpoint),
    baseline: parseBaseline(body.baseline, endpoint),
    medicalNotes: list(body.medical_notes).map((entry): MedicalNoteItem => {
      const item = object(entry, endpoint);
      return {
        noteId: requiredString(item, 'note_id', endpoint),
        title: text(item.title) ?? '',
        body: text(item.body) ?? '',
        category: text(item.category) ?? 'general',
      };
    }),
    questions: list(body.questions).map((entry) => parseQuestion(entry, endpoint)),
    suggestions: list(body.suggestions).map((entry): QuestionSuggestion => {
      const item = object(entry, endpoint);
      return {
        key: requiredString(item, 'key', endpoint),
        prompt: text(item.prompt) ?? '',
        questionText: text(item.question_text) ?? '',
        reason: text(item.reason) ?? 'generic',
      };
    }),
    hasHealthData: body.has_health_data === true,
    defaultSelection: parseSelection(body.default_selection),
  };
}

function parseTodayAppointment(raw: unknown, endpoint: string): TodayAppointment {
  const body = object(raw, endpoint);
  return {
    appointmentId: requiredString(body, 'appointment_id', endpoint),
    title: text(body.title) ?? 'Appointment',
    appointmentType: oneOf(body.appointment_type, APPOINTMENT_TYPES, 'other'),
    scheduledAt: text(body.scheduled_at) ?? new Date().toISOString(),
    timezone: text(body.timezone) ?? 'UTC',
    whenLabel: text(body.when_label) ?? '',
    relativeDay: text(body.relative_day),
    clinicianName: text(body.clinician_name),
    clinicianSpecialty: text(body.clinician_specialty),
    locationName: text(body.location_name),
    preparationStatus: oneOf(
      body.preparation_status,
      PREPARATION_STATUSES,
      'not_started'
    ),
    questionCount: count(body.question_count),
    reportCount: count(body.report_count),
  };
}

export function parseTodayAppointments(raw: unknown): TodayAppointments | null {
  if (raw === null || raw === undefined) return null;
  const endpoint = '/api/v1/today';
  const body = object(raw, endpoint);
  return {
    next:
      body.next === null || body.next === undefined
        ? null
        : parseTodayAppointment(body.next, endpoint),
    upcomingCount: count(body.upcoming_count),
    hasAppointments: body.has_appointments === true,
  };
}

export function parseAppointmentSummary(
  raw: unknown,
  endpoint: string
): AppointmentSummary {
  const body = object(raw, endpoint);
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    upcomingCount: count(body.upcoming_count),
    pastCount: count(body.past_count),
    cancelledCount: count(body.cancelled_count),
    hasAppointments: body.has_appointments === true,
    next:
      body.next === null || body.next === undefined
        ? null
        : parseTodayAppointment(body.next, endpoint),
  };
}

// --- requests ---------------------------------------------------------------

function base(profileId: string): string {
  return `/api/v1/profiles/${encodeURIComponent(profileId)}/appointments`;
}

function one(profileId: string, appointmentId: string): string {
  return `${base(profileId)}/${encodeURIComponent(appointmentId)}`;
}

export async function fetchAppointments(
  profileId: string,
  scope?: AppointmentScope,
  signal?: AbortSignal
): Promise<Appointment[]> {
  const url = scope === undefined ? base(profileId) : `${base(profileId)}?scope=${scope}`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseAppointment(entry, url));
}

export async function fetchAppointment(
  profileId: string,
  appointmentId: string,
  signal?: AbortSignal
): Promise<Appointment> {
  const url = one(profileId, appointmentId);
  return parseAppointment(await apiRequest<unknown>(url, { signal }), url);
}

export async function fetchAppointmentSummary(
  profileId: string,
  signal?: AbortSignal
): Promise<AppointmentSummary> {
  const url = `${base(profileId)}/summary`;
  return parseAppointmentSummary(await apiRequest<unknown>(url, { signal }), url);
}

export async function createAppointment(
  profileId: string,
  payload: AppointmentPayload
): Promise<Appointment> {
  const url = base(profileId);
  const body = object(
    await apiRequest<unknown>(url, { method: 'POST', body: payload }),
    url
  );
  return parseAppointment(body.appointment, url);
}

export async function updateAppointment(
  profileId: string,
  appointmentId: string,
  patch: Partial<AppointmentPayload> & { visit_notes?: string | null }
): Promise<Appointment> {
  const url = one(profileId, appointmentId);
  return parseAppointment(
    await apiRequest<unknown>(url, { method: 'PATCH', body: patch }),
    url
  );
}

export async function cancelAppointment(
  profileId: string,
  appointmentId: string
): Promise<Appointment> {
  const url = `${one(profileId, appointmentId)}/cancel`;
  return parseAppointment(await apiRequest<unknown>(url, { method: 'POST' }), url);
}

export async function completeAppointment(
  profileId: string,
  appointmentId: string,
  body: { visit_notes?: string | null; follow_up_date?: string | null } = {}
): Promise<Appointment> {
  const url = `${one(profileId, appointmentId)}/complete`;
  return parseAppointment(await apiRequest<unknown>(url, { method: 'POST', body }), url);
}

export async function reopenAppointment(
  profileId: string,
  appointmentId: string
): Promise<Appointment> {
  const url = `${one(profileId, appointmentId)}/reopen`;
  return parseAppointment(await apiRequest<unknown>(url, { method: 'POST' }), url);
}

export async function deleteAppointment(
  profileId: string,
  appointmentId: string
): Promise<void> {
  await apiRequest<void>(one(profileId, appointmentId), { method: 'DELETE' });
}

// --- questions --------------------------------------------------------------

export async function fetchQuestions(
  profileId: string,
  appointmentId: string,
  signal?: AbortSignal
): Promise<AppointmentQuestion[]> {
  const url = `${one(profileId, appointmentId)}/questions`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseQuestion(entry, url));
}

export async function createQuestion(
  profileId: string,
  appointmentId: string,
  body: { text: string; client_question_id?: string }
): Promise<AppointmentQuestion> {
  const url = `${one(profileId, appointmentId)}/questions`;
  const saved = object(await apiRequest<unknown>(url, { method: 'POST', body }), url);
  return parseQuestion(saved.question, url);
}

export async function updateQuestion(
  profileId: string,
  appointmentId: string,
  questionId: string,
  patch: { text?: string; is_answered?: boolean; answer_note?: string | null }
): Promise<AppointmentQuestion> {
  const url = `${one(profileId, appointmentId)}/questions/${encodeURIComponent(questionId)}`;
  return parseQuestion(
    await apiRequest<unknown>(url, { method: 'PATCH', body: patch }),
    url
  );
}

export async function deleteQuestion(
  profileId: string,
  appointmentId: string,
  questionId: string
): Promise<void> {
  await apiRequest<void>(
    `${one(profileId, appointmentId)}/questions/${encodeURIComponent(questionId)}`,
    { method: 'DELETE' }
  );
}

export async function reorderQuestions(
  profileId: string,
  appointmentId: string,
  questionIds: string[]
): Promise<AppointmentQuestion[]> {
  const url = `${one(profileId, appointmentId)}/questions/order`;
  const raw = await apiRequest<unknown>(url, {
    method: 'PUT',
    body: { question_ids: questionIds },
  });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseQuestion(entry, url));
}

// --- preparation and reports ------------------------------------------------

export interface PeriodRequest {
  preset?: ReportPeriodPreset;
  periodStart?: string;
  periodEnd?: string;
}

export async function fetchPreparation(
  profileId: string,
  appointmentId: string,
  period: PeriodRequest = {},
  signal?: AbortSignal
): Promise<Preparation> {
  const query = new URLSearchParams();
  if (period.preset) query.set('preset', period.preset);
  if (period.periodStart) query.set('period_start', period.periodStart);
  if (period.periodEnd) query.set('period_end', period.periodEnd);
  const suffix = query.toString();
  const url = `${one(profileId, appointmentId)}/prepare${suffix ? `?${suffix}` : ''}`;
  return parsePreparation(await apiRequest<unknown>(url, { signal }), url);
}

/** The wire shape of a selection. Built here so screens never assemble one. */
export function selectionPayload(selection: ReportSelection): Record<string, unknown> {
  return {
    include: selection.include,
    symptom_episode_ids: selection.symptomEpisodeIds,
    symptom_note_entry_ids: selection.symptomNoteEntryIds,
    medication_ids: selection.medicationIds,
    checkin_note_dates: selection.checkinNoteDates,
    medical_note_ids: selection.medicalNoteIds,
    focus: selection.focus,
    include_appendix: selection.includeAppendix,
    include_skip_reason_notes: selection.includeSkipReasonNotes,
  };
}

export async function fetchReports(
  profileId: string,
  appointmentId: string,
  signal?: AbortSignal
): Promise<AppointmentReport[]> {
  const url = `${one(profileId, appointmentId)}/reports`;
  const raw = await apiRequest<unknown>(url, { signal });
  if (!Array.isArray(raw)) {
    throw new ApiError('server', `Unexpected response shape from ${url}.`);
  }
  return raw.map((entry) => parseReport(entry, url));
}

export async function fetchReport(
  profileId: string,
  appointmentId: string,
  reportId: string,
  signal?: AbortSignal
): Promise<AppointmentReport> {
  const url = `${one(profileId, appointmentId)}/reports/${encodeURIComponent(reportId)}`;
  return parseReport(await apiRequest<unknown>(url, { signal }), url);
}

export async function generateReport(
  profileId: string,
  appointmentId: string,
  body: {
    period_preset: ReportPeriodPreset;
    period_start?: string | null;
    period_end?: string | null;
    selection: Record<string, unknown>;
    client_report_id?: string;
  }
): Promise<AppointmentReport> {
  const url = `${one(profileId, appointmentId)}/reports`;
  const saved = object(await apiRequest<unknown>(url, { method: 'POST', body }), url);
  return parseReport(saved.report, url);
}

export async function deleteReport(
  profileId: string,
  appointmentId: string,
  reportId: string
): Promise<void> {
  await apiRequest<void>(
    `${one(profileId, appointmentId)}/reports/${encodeURIComponent(reportId)}`,
    { method: 'DELETE' }
  );
}

/** The authenticated path a report's PDF is downloaded from (s52). */
export function reportPdfPath(
  profileId: string,
  appointmentId: string,
  reportId: string
): string {
  return `${one(profileId, appointmentId)}/reports/${encodeURIComponent(reportId)}/pdf`;
}

/**
 * The URL *and* the bearer token for a report's PDF, or null when signed out.
 *
 * The URL is only ever used with the token beside it: the route authorizes the
 * account, the profile, the appointment and the report before it serves a byte
 * (PRD 7, section 52).
 */
export async function reportPdfSource(
  profileId: string,
  appointmentId: string,
  reportId: string
): Promise<{ uri: string; headers: Record<string, string> } | null> {
  return mediaSource(reportPdfPath(profileId, appointmentId, reportId));
}
