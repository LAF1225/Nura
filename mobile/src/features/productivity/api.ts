/**
 * The daily-life endpoints (PRD 12, sections 52-58).
 *
 * Responses are parsed field by field rather than cast, the same way the
 * safety, caregiver and robot clients parse. Three decisions carry a rule.
 *
 * **An unrecognised status falls back to the quietest value, never the
 * loudest.** A task status nobody recognises reads as `open` -- something
 * still to do, which is the state that shows a row rather than hiding one --
 * and an occurrence status falls back to `scheduled`. Guessing optimistically
 * about something unrecognised is how a screen comes to tell somebody a thing
 * is done when the server never said so.
 *
 * **Labels are kept verbatim.** `dueLabel`, `scheduleLabel`, `progressLabel`
 * and `limitation` are the server's prose, and a client that assembled its own
 * would be a second place that could disagree -- which matters most for the
 * alarm limitation, a sentence section 11 does not let anybody drop.
 *
 * **Nothing here writes a `source`.** Provenance is the server's record of how
 * a write arrived (section 43), so no request body below carries one.
 */
import { apiRequest } from '../../services/api/client';
import { ApiError } from '../../services/api/errors';
import type {
  Alarm,
  AlarmInput,
  AlarmList,
  AlarmRecurrence,
  AlarmSound,
  CaregiverRoutine,
  CaregiverRoutineList,
  Capability,
  CapabilityKey,
  CapabilityState,
  DailyLifeSource,
  DailyLifeSummary,
  ExternalCapabilities,
  ItemWindow,
  OccurrenceStatus,
  Reminder,
  ReminderInput,
  ReminderList,
  ReminderOccurrence,
  ReminderRecurrence,
  ReminderStatus,
  Routine,
  RoutineEdit,
  RoutineInput,
  RoutineList,
  RoutineRun,
  RoutineRunStatus,
  RoutineScheduleType,
  RoutineStep,
  RoutineStepState,
  RoutineStatus,
  SnoozeMinutes,
  StepCompletion,
  Task,
  TaskEdit,
  TaskInput,
  TaskList,
  TaskPriority,
  TaskStatus,
} from './types';

const TASK_STATUSES: readonly TaskStatus[] = [
  'open',
  'completed',
  'archived',
  'cancelled',
];
const TASK_PRIORITIES: readonly TaskPriority[] = ['normal', 'important'];
const SOURCES: readonly DailyLifeSource[] = [
  'user',
  'assistant',
  'caregiver_suggestion',
  'import_future',
];
const RECURRENCES: readonly ReminderRecurrence[] = [
  'one_time',
  'daily',
  'selected_days',
  'weekly',
  'monthly',
];
const REMINDER_STATUSES: readonly ReminderStatus[] = [
  'active',
  'paused',
  'completed',
  'cancelled',
];
const OCCURRENCE_STATUSES: readonly OccurrenceStatus[] = [
  'scheduled',
  'completed',
  'dismissed',
  'snoozed',
  'missed',
  'cancelled',
];
const WINDOWS: readonly ItemWindow[] = ['upcoming', 'due', 'overdue', 'completed'];
const ALARM_RECURRENCES: readonly AlarmRecurrence[] = [
  'one_time',
  'daily',
  'selected_days',
];
export const ALARM_SOUNDS: readonly AlarmSound[] = ['default', 'gentle', 'chime', 'bell'];
const ROUTINE_SCHEDULE_TYPES: readonly RoutineScheduleType[] = ['daily', 'selected_days'];
const ROUTINE_STATUSES: readonly RoutineStatus[] = ['active', 'paused', 'archived'];
const RUN_STATUSES: readonly RoutineRunStatus[] = [
  'scheduled',
  'in_progress',
  'completed',
  'skipped',
  'missed',
  'cancelled',
];
const STEP_STATES: readonly RoutineStepState[] = ['completed', 'skipped'];
const CAPABILITY_KEYS: readonly CapabilityKey[] = [
  'tasks',
  'reminders',
  'alarms',
  'routines',
  'weather',
  'news',
  'external_calendar',
];
const CAPABILITY_STATES: readonly CapabilityState[] = [
  'available',
  'not_configured',
  'unavailable',
];

/** The snooze durations the server offers (PRD 5's, reused). */
export const SNOOZE_OPTIONS: readonly SnoozeMinutes[] = [10, 30, 60];

function base(profileId: string): string {
  return `/api/v1/profiles/${profileId}`;
}

// --- parsing primitives ------------------------------------------------------

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

function flag(value: unknown): boolean {
  return value === true;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

function optional<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function numbers(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const parsed = value.filter(
    (entry): entry is number => typeof entry === 'number' && Number.isFinite(entry)
  );
  return parsed.length > 0 ? parsed : null;
}

// --- tasks -------------------------------------------------------------------

export function parseTask(value: unknown, endpoint = 'tasks'): Task {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    title: requiredString(body, 'title', endpoint),
    notes: text(body.notes),
    // An unrecognised status reads as something still to do, which shows the
    // row rather than hiding it.
    status: oneOf(body.status, TASK_STATUSES, 'open'),
    statusLabel: requiredString(body, 'status_label', endpoint),
    priority: oneOf(body.priority, TASK_PRIORITIES, 'normal'),
    priorityLabel: requiredString(body, 'priority_label', endpoint),
    dueAt: text(body.due_at),
    dueLocalDate: text(body.due_local_date),
    timezone: typeof body.timezone === 'string' ? body.timezone : 'UTC',
    dueLabel: text(body.due_label),
    overdue: flag(body.overdue),
    source: oneOf(body.source, SOURCES, 'user'),
    sourceLabel: requiredString(body, 'source_label', endpoint),
    completedAt: text(body.completed_at),
    archivedAt: text(body.archived_at),
    cancelledAt: text(body.cancelled_at),
    contentUpdatedAt: text(body.content_updated_at),
    statusChangedAt: text(body.status_changed_at),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

function taskBody(input: TaskInput): Record<string, unknown> {
  const body: Record<string, unknown> = { title: input.title };
  if (input.notes !== undefined) body.notes = input.notes;
  if (input.priority !== undefined) body.priority = input.priority;
  if (input.dueAt !== undefined) body.due_at = input.dueAt;
  if (input.timezone !== undefined) body.timezone = input.timezone;
  if (input.clientTaskId !== undefined) body.client_task_id = input.clientTaskId;
  return body;
}

export async function fetchTasks(
  profileId: string,
  scope?: 'open' | 'completed' | 'archived'
): Promise<TaskList> {
  const query = scope ? `?scope=${scope}` : '';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/tasks${query}`),
    'tasks'
  );
  return {
    tasks: list(body.tasks).map((row) => parseTask(row)),
    openCount: count(body.open_count),
    overdueCount: count(body.overdue_count),
  };
}

/** Returns the stored task and whether this call created it (section 37). */
export async function createTask(
  profileId: string,
  input: TaskInput
): Promise<{ task: Task; created: boolean }> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/tasks`, {
      method: 'POST',
      body: taskBody(input),
    }),
    'tasks'
  );
  return { task: parseTask(body.task), created: flag(body.created) };
}

export async function updateTask(
  profileId: string,
  taskId: string,
  edit: TaskEdit
): Promise<{ task: Task; applied: boolean }> {
  // `'key' in edit` rather than a truthiness check, so clearing a due date by
  // sending null is a change rather than an omission.
  const body: Record<string, unknown> = {};
  if ('title' in edit) body.title = edit.title;
  if ('notes' in edit) body.notes = edit.notes;
  if ('priority' in edit) body.priority = edit.priority;
  if ('dueAt' in edit) body.due_at = edit.dueAt;
  if ('timezone' in edit) body.timezone = edit.timezone;
  if ('clientUpdatedAt' in edit) body.client_updated_at = edit.clientUpdatedAt;

  const response = object(
    await apiRequest<unknown>(`${base(profileId)}/tasks/${taskId}`, {
      method: 'PATCH',
      body,
    }),
    'tasks'
  );
  return { task: parseTask(response.task), applied: flag(response.applied) };
}

export async function taskAction(
  profileId: string,
  taskId: string,
  action: 'complete' | 'reopen' | 'archive' | 'cancel',
  clientUpdatedAt?: string
): Promise<{ task: Task; applied: boolean }> {
  const response = object(
    await apiRequest<unknown>(`${base(profileId)}/tasks/${taskId}/${action}`, {
      method: 'POST',
      body: clientUpdatedAt ? { client_updated_at: clientUpdatedAt } : {},
    }),
    'tasks'
  );
  return { task: parseTask(response.task), applied: flag(response.applied) };
}

export async function deleteTask(profileId: string, taskId: string): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/tasks/${taskId}`, { method: 'DELETE' });
}

// --- reminders ---------------------------------------------------------------

export function parseOccurrence(
  value: unknown,
  endpoint = 'reminder-occurrences'
): ReminderOccurrence {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    reminderId: requiredString(body, 'reminder_id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    title: requiredString(body, 'title', endpoint),
    body: text(body.body),
    scheduledFor: requiredString(body, 'scheduled_for', endpoint),
    localDate: requiredString(body, 'local_date', endpoint),
    status: oneOf(body.status, OCCURRENCE_STATUSES, 'scheduled'),
    statusLabel: requiredString(body, 'status_label', endpoint),
    window: oneOf(body.window, WINDOWS, 'upcoming'),
    actionAt: text(body.action_at),
    snoozedUntil: text(body.snoozed_until),
    snoozeCount: count(body.snooze_count),
    canSnooze: flag(body.can_snooze),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

export function parseReminder(value: unknown, endpoint = 'reminders'): Reminder {
  const body = object(value, endpoint);
  const occurrences = body.occurrences;
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    title: requiredString(body, 'title', endpoint),
    body: text(body.body),
    recurrence: oneOf(body.recurrence, RECURRENCES, 'one_time'),
    recurrenceLabel: requiredString(body, 'recurrence_label', endpoint),
    scheduleLabel: requiredString(body, 'schedule_label', endpoint),
    timezone: typeof body.timezone === 'string' ? body.timezone : 'UTC',
    startDate: requiredString(body, 'start_date', endpoint),
    endDate: text(body.end_date),
    timeOfDay: requiredString(body, 'time_of_day', endpoint),
    weekdays: numbers(body.weekdays),
    dayOfMonth: typeof body.day_of_month === 'number' ? body.day_of_month : null,
    status: oneOf(body.status, REMINDER_STATUSES, 'active'),
    statusLabel: requiredString(body, 'status_label', endpoint),
    notificationEnabled: flag(body.notification_enabled),
    notificationNote: text(body.notification_note),
    source: oneOf(body.source, SOURCES, 'user'),
    sourceLabel: requiredString(body, 'source_label', endpoint),
    pausedAt: text(body.paused_at),
    nextOccurrenceAt: text(body.next_occurrence_at),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
    ...(Array.isArray(occurrences)
      ? { occurrences: occurrences.map((row) => parseOccurrence(row)) }
      : {}),
  };
}

function reminderBody(input: ReminderInput): Record<string, unknown> {
  const body: Record<string, unknown> = {
    title: input.title,
    time_of_day: input.timeOfDay,
    start_date: input.startDate,
  };
  if (input.recurrence !== undefined) body.recurrence = input.recurrence;
  if (input.timezone !== undefined) body.timezone = input.timezone;
  if (input.body !== undefined) body.body = input.body;
  if (input.endDate !== undefined) body.end_date = input.endDate;
  if (input.weekdays !== undefined) body.weekdays = input.weekdays;
  if (input.dayOfMonth !== undefined) body.day_of_month = input.dayOfMonth;
  if (input.notificationEnabled !== undefined) {
    body.notification_enabled = input.notificationEnabled;
  }
  if (input.clientReminderId !== undefined) {
    body.client_reminder_id = input.clientReminderId;
  }
  return body;
}

export async function fetchReminders(profileId: string): Promise<ReminderList> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/reminders`),
    'reminders'
  );
  return {
    reminders: list(body.reminders).map((row) => parseReminder(row)),
    dueCount: count(body.due_count),
  };
}

export async function fetchReminder(
  profileId: string,
  reminderId: string
): Promise<Reminder> {
  return parseReminder(
    await apiRequest<unknown>(`${base(profileId)}/reminders/${reminderId}`)
  );
}

export async function createReminder(
  profileId: string,
  input: ReminderInput
): Promise<{ reminder: Reminder; created: boolean }> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/reminders`, {
      method: 'POST',
      body: reminderBody(input),
    }),
    'reminders'
  );
  return { reminder: parseReminder(body.reminder), created: flag(body.created) };
}

export async function updateReminder(
  profileId: string,
  reminderId: string,
  input: Partial<ReminderInput>
): Promise<Reminder> {
  const body: Record<string, unknown> = {};
  if ('title' in input) body.title = input.title;
  if ('body' in input) body.body = input.body;
  if ('recurrence' in input) body.recurrence = input.recurrence;
  if ('timezone' in input) body.timezone = input.timezone;
  if ('startDate' in input) body.start_date = input.startDate;
  if ('endDate' in input) body.end_date = input.endDate;
  if ('timeOfDay' in input) body.time_of_day = input.timeOfDay;
  if ('weekdays' in input) body.weekdays = input.weekdays;
  if ('dayOfMonth' in input) body.day_of_month = input.dayOfMonth;
  if ('notificationEnabled' in input) {
    body.notification_enabled = input.notificationEnabled;
  }
  return parseReminder(
    await apiRequest<unknown>(`${base(profileId)}/reminders/${reminderId}`, {
      method: 'PATCH',
      body,
    })
  );
}

export async function setReminderPaused(
  profileId: string,
  reminderId: string,
  paused: boolean
): Promise<Reminder> {
  const action = paused ? 'pause' : 'resume';
  return parseReminder(
    await apiRequest<unknown>(`${base(profileId)}/reminders/${reminderId}/${action}`, {
      method: 'POST',
    })
  );
}

export async function deleteReminder(
  profileId: string,
  reminderId: string
): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/reminders/${reminderId}`, {
    method: 'DELETE',
  });
}

export async function fetchOccurrences(
  profileId: string,
  range?: { from?: string; to?: string }
): Promise<ReminderOccurrence[]> {
  const params = new URLSearchParams();
  if (range?.from) params.set('from_date', range.from);
  if (range?.to) params.set('to_date', range.to);
  const query = params.toString() ? `?${params.toString()}` : '';
  const rows = await apiRequest<unknown>(
    `${base(profileId)}/reminder-occurrences${query}`
  );
  return list(rows).map((row) => parseOccurrence(row));
}

export async function occurrenceAction(
  profileId: string,
  occurrenceId: string,
  action: 'complete' | 'dismiss',
  actionAt?: string
): Promise<{ occurrence: ReminderOccurrence; applied: boolean }> {
  const response = object(
    await apiRequest<unknown>(
      `${base(profileId)}/reminder-occurrences/${occurrenceId}/${action}`,
      { method: 'POST', body: actionAt ? { action_at: actionAt } : {} }
    ),
    'reminder-occurrences'
  );
  return {
    occurrence: parseOccurrence(response.occurrence),
    applied: flag(response.applied),
  };
}

export async function snoozeOccurrence(
  profileId: string,
  occurrenceId: string,
  minutes: SnoozeMinutes
): Promise<{ occurrence: ReminderOccurrence; applied: boolean }> {
  const response = object(
    await apiRequest<unknown>(
      `${base(profileId)}/reminder-occurrences/${occurrenceId}/snooze`,
      { method: 'POST', body: { minutes } }
    ),
    'reminder-occurrences'
  );
  return {
    occurrence: parseOccurrence(response.occurrence),
    applied: flag(response.applied),
  };
}

// --- alarms ------------------------------------------------------------------

export function parseAlarm(value: unknown, endpoint = 'alarms'): Alarm {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    label: requiredString(body, 'label', endpoint),
    timeOfDay: requiredString(body, 'time_of_day', endpoint),
    timezone: typeof body.timezone === 'string' ? body.timezone : 'UTC',
    recurrence: oneOf(body.recurrence, ALARM_RECURRENCES, 'one_time'),
    recurrenceLabel: requiredString(body, 'recurrence_label', endpoint),
    scheduleLabel: requiredString(body, 'schedule_label', endpoint),
    weekdays: numbers(body.weekdays),
    onDate: text(body.on_date),
    enabled: flag(body.enabled),
    soundKey: oneOf(body.sound_key, ALARM_SOUNDS, 'default'),
    soundLabel: requiredString(body, 'sound_label', endpoint),
    vibration: flag(body.vibration),
    nextFireAt: text(body.next_fire_at),
    source: oneOf(body.source, SOURCES, 'user'),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

function alarmBody(input: AlarmInput | Partial<AlarmInput>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if ('label' in input) body.label = input.label;
  if ('timeOfDay' in input) body.time_of_day = input.timeOfDay;
  if ('recurrence' in input) body.recurrence = input.recurrence;
  if ('timezone' in input) body.timezone = input.timezone;
  if ('weekdays' in input) body.weekdays = input.weekdays;
  if ('onDate' in input) body.on_date = input.onDate;
  if ('enabled' in input) body.enabled = input.enabled;
  if ('soundKey' in input) body.sound_key = input.soundKey;
  if ('vibration' in input) body.vibration = input.vibration;
  if ('clientAlarmId' in input) body.client_alarm_id = input.clientAlarmId;
  return body;
}

export async function fetchAlarms(profileId: string): Promise<AlarmList> {
  const endpoint = 'alarms';
  const body = object(await apiRequest<unknown>(`${base(profileId)}/alarms`), endpoint);
  return {
    alarms: list(body.alarms).map((row) => parseAlarm(row)),
    enabledCount: count(body.enabled_count),
    // Required, not optional: section 11's sentence is part of the contract,
    // and a response without it is a response this client refuses.
    limitation: requiredString(body, 'limitation', endpoint),
  };
}

export async function createAlarm(
  profileId: string,
  input: AlarmInput
): Promise<{ alarm: Alarm; created: boolean }> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/alarms`, {
      method: 'POST',
      body: alarmBody(input),
    }),
    'alarms'
  );
  return { alarm: parseAlarm(body.alarm), created: flag(body.created) };
}

export async function updateAlarm(
  profileId: string,
  alarmId: string,
  input: Partial<AlarmInput>
): Promise<Alarm> {
  return parseAlarm(
    await apiRequest<unknown>(`${base(profileId)}/alarms/${alarmId}`, {
      method: 'PATCH',
      body: alarmBody(input),
    })
  );
}

export async function deleteAlarm(profileId: string, alarmId: string): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/alarms/${alarmId}`, { method: 'DELETE' });
}

// --- routines ----------------------------------------------------------------

function parseStep(value: unknown, endpoint = 'routines'): RoutineStep {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    routineId: requiredString(body, 'routine_id', endpoint),
    title: requiredString(body, 'title', endpoint),
    position: count(body.position),
    optional: flag(body.optional),
  };
}

function parseCompletion(value: unknown, endpoint = 'routine-runs'): StepCompletion {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    stepId: requiredString(body, 'step_id', endpoint),
    state: oneOf(body.state, STEP_STATES, 'completed'),
    stateLabel: requiredString(body, 'state_label', endpoint),
    completedAt: requiredString(body, 'completed_at', endpoint),
  };
}

export function parseRun(value: unknown, endpoint = 'routine-runs'): RoutineRun {
  const body = object(value, endpoint);
  return {
    id: requiredString(body, 'id', endpoint),
    routineId: requiredString(body, 'routine_id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    routineTitle: requiredString(body, 'routine_title', endpoint),
    scheduledFor: requiredString(body, 'scheduled_for', endpoint),
    localDate: requiredString(body, 'local_date', endpoint),
    status: oneOf(body.status, RUN_STATUSES, 'scheduled'),
    statusLabel: requiredString(body, 'status_label', endpoint),
    startedAt: text(body.started_at),
    completedAt: text(body.completed_at),
    totalSteps: count(body.total_steps),
    completedSteps: count(body.completed_steps),
    skippedSteps: count(body.skipped_steps),
    progressLabel: requiredString(body, 'progress_label', endpoint),
    nextStepId: text(body.next_step_id),
    nextStepTitle: text(body.next_step_title),
    completions: list(body.completions).map((row) => parseCompletion(row)),
  };
}

export function parseRoutine(value: unknown, endpoint = 'routines'): Routine {
  const body = object(value, endpoint);
  const run = body.today_run;
  return {
    id: requiredString(body, 'id', endpoint),
    profileId: requiredString(body, 'profile_id', endpoint),
    title: requiredString(body, 'title', endpoint),
    description: text(body.description),
    scheduleType: oneOf(body.schedule_type, ROUTINE_SCHEDULE_TYPES, 'daily'),
    scheduleLabel: requiredString(body, 'schedule_label', endpoint),
    timezone: typeof body.timezone === 'string' ? body.timezone : 'UTC',
    timeOfDay: requiredString(body, 'time_of_day', endpoint),
    weekdays: numbers(body.weekdays),
    startDate: requiredString(body, 'start_date', endpoint),
    endDate: text(body.end_date),
    status: oneOf(body.status, ROUTINE_STATUSES, 'active'),
    statusLabel: requiredString(body, 'status_label', endpoint),
    pausedAt: text(body.paused_at),
    source: oneOf(body.source, SOURCES, 'user'),
    sourceLabel: requiredString(body, 'source_label', endpoint),
    steps: list(body.steps).map((row) => parseStep(row, endpoint)),
    todayRun: run === null || run === undefined ? null : parseRun(run),
    createdAt: requiredString(body, 'created_at', endpoint),
    updatedAt: requiredString(body, 'updated_at', endpoint),
  };
}

function routineBody(input: RoutineInput | RoutineEdit): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if ('title' in input) body.title = input.title;
  if ('timeOfDay' in input) body.time_of_day = input.timeOfDay;
  if ('startDate' in input) body.start_date = input.startDate;
  if ('scheduleType' in input) body.schedule_type = input.scheduleType;
  if ('timezone' in input) body.timezone = input.timezone;
  if ('description' in input) body.description = input.description;
  if ('weekdays' in input) body.weekdays = input.weekdays;
  if ('endDate' in input) body.end_date = input.endDate;
  if ('clientRoutineId' in input) {
    body.client_routine_id = (input as RoutineInput).clientRoutineId;
  }
  if ('steps' in input && input.steps) {
    body.steps = input.steps.map((step) => ({
      title: step.title,
      optional: step.optional ?? false,
    }));
  }
  return body;
}

export async function fetchRoutines(profileId: string): Promise<RoutineList> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/routines`),
    'routines'
  );
  return {
    routines: list(body.routines).map((row) => parseRoutine(row)),
    activeCount: count(body.active_count),
  };
}

export async function fetchRoutine(
  profileId: string,
  routineId: string
): Promise<Routine> {
  return parseRoutine(
    await apiRequest<unknown>(`${base(profileId)}/routines/${routineId}`)
  );
}

export async function createRoutine(
  profileId: string,
  input: RoutineInput
): Promise<{ routine: Routine; created: boolean }> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/routines`, {
      method: 'POST',
      body: routineBody(input),
    }),
    'routines'
  );
  return { routine: parseRoutine(body.routine), created: flag(body.created) };
}

export async function updateRoutine(
  profileId: string,
  routineId: string,
  edit: RoutineEdit
): Promise<Routine> {
  return parseRoutine(
    await apiRequest<unknown>(`${base(profileId)}/routines/${routineId}`, {
      method: 'PATCH',
      body: routineBody(edit),
    })
  );
}

export async function setRoutinePaused(
  profileId: string,
  routineId: string,
  paused: boolean
): Promise<Routine> {
  const action = paused ? 'pause' : 'resume';
  return parseRoutine(
    await apiRequest<unknown>(`${base(profileId)}/routines/${routineId}/${action}`, {
      method: 'POST',
    })
  );
}

export async function archiveRoutine(
  profileId: string,
  routineId: string
): Promise<Routine> {
  return parseRoutine(
    await apiRequest<unknown>(`${base(profileId)}/routines/${routineId}/archive`, {
      method: 'POST',
    })
  );
}

export async function deleteRoutine(profileId: string, routineId: string): Promise<void> {
  await apiRequest<void>(`${base(profileId)}/routines/${routineId}`, {
    method: 'DELETE',
  });
}

export async function fetchTodayRuns(profileId: string): Promise<RoutineRun[]> {
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/routine-runs/today`),
    'routine-runs'
  );
  return list(body.runs).map((row) => parseRun(row));
}

export async function fetchRun(profileId: string, runId: string): Promise<RoutineRun> {
  return parseRun(await apiRequest<unknown>(`${base(profileId)}/routine-runs/${runId}`));
}

export async function completeStep(
  profileId: string,
  runId: string,
  stepId: string,
  options: {
    state?: RoutineStepState;
    completedAt?: string;
    clientCompletionId?: string;
  } = {}
): Promise<RoutineRun> {
  const body: Record<string, unknown> = {};
  if (options.state !== undefined) body.state = options.state;
  if (options.completedAt !== undefined) body.completed_at = options.completedAt;
  if (options.clientCompletionId !== undefined) {
    body.client_completion_id = options.clientCompletionId;
  }
  return parseRun(
    await apiRequest<unknown>(
      `${base(profileId)}/routine-runs/${runId}/steps/${stepId}/complete`,
      { method: 'POST', body }
    )
  );
}

export async function clearStep(
  profileId: string,
  runId: string,
  stepId: string
): Promise<RoutineRun> {
  return parseRun(
    await apiRequest<unknown>(
      `${base(profileId)}/routine-runs/${runId}/steps/${stepId}/complete`,
      { method: 'DELETE' }
    )
  );
}

export async function runAction(
  profileId: string,
  runId: string,
  action: 'complete' | 'skip'
): Promise<{ run: RoutineRun; applied: boolean }> {
  const response = object(
    await apiRequest<unknown>(`${base(profileId)}/routine-runs/${runId}/${action}`, {
      method: 'POST',
    }),
    'routine-runs'
  );
  return { run: parseRun(response.run), applied: flag(response.applied) };
}

// --- the summary and the capability map --------------------------------------

export function parseDailyLifeSummary(value: unknown): DailyLifeSummary | null {
  if (value === null || value === undefined) return null;
  const endpoint = 'daily-life';
  const body = object(value, endpoint);
  const tasks = object(body.tasks ?? {}, endpoint);
  const reminders = object(body.reminders ?? {}, endpoint);
  const routines = object(body.routines ?? {}, endpoint);
  return {
    tasks: {
      dueToday: count(tasks.due_today),
      overdue: count(tasks.overdue),
      openTotal: count(tasks.open_total),
    },
    reminders: {
      dueToday: count(reminders.due_today),
      dueNow: count(reminders.due_now),
    },
    routines: {
      dueToday: count(routines.due_today),
      inProgress: count(routines.in_progress),
      completedToday: count(routines.completed_today),
    },
    nextAlarmAt: text(body.next_alarm_at),
    alarmCount: count(body.alarm_count),
    summaryLabel: typeof body.summary_label === 'string' ? body.summary_label : '',
    hasAnything: flag(body.has_anything),
  };
}

export async function fetchDailyLifeSummary(
  profileId: string,
  localDate?: string
): Promise<DailyLifeSummary> {
  const query = localDate ? `?local_date=${localDate}` : '';
  const summary = parseDailyLifeSummary(
    await apiRequest<unknown>(`${base(profileId)}/daily-life/summary${query}`)
  );
  if (summary === null) {
    throw new ApiError('server', 'daily-life summary response was empty.');
  }
  return summary;
}

function parseCapability(value: unknown): Capability | null {
  const endpoint = 'external-capabilities';
  const body = object(value, endpoint);
  const key = optional(body.key, CAPABILITY_KEYS);
  // A capability a later backend adds is dropped rather than rendered as a
  // mystery row. A *state* nobody recognises falls back to `not_configured`,
  // which is the conservative direction.
  if (key === null) return null;
  return {
    key,
    state: oneOf(body.state, CAPABILITY_STATES, 'not_configured'),
    label: requiredString(body, 'label', endpoint),
    sentence: requiredString(body, 'sentence', endpoint),
  };
}

export async function fetchExternalCapabilities(
  profileId: string
): Promise<ExternalCapabilities> {
  const endpoint = 'external-capabilities';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/assistant/external-capabilities`),
    endpoint
  );
  const external: Record<string, CapabilityState> = {};
  for (const [key, value] of Object.entries(object(body.external ?? {}, endpoint))) {
    external[key] = oneOf(value, CAPABILITY_STATES, 'not_configured');
  }
  return {
    profileId: requiredString(body, 'profile_id', endpoint),
    capabilities: list(body.capabilities)
      .map((row) => parseCapability(row))
      .filter((row): row is Capability => row !== null),
    external,
    anyExternalConfigured: flag(body.any_external_configured),
  };
}

// --- the caregiver's view ----------------------------------------------------

export async function fetchCareRoutines(
  profileId: string
): Promise<CaregiverRoutineList> {
  const endpoint = 'care/routines';
  const body = object(
    await apiRequest<unknown>(`${base(profileId)}/care/routines`),
    endpoint
  );
  return {
    routines: list(body.routines).map((value) => {
      const row = object(value, endpoint);
      return {
        routineId: requiredString(row, 'routine_id', endpoint),
        title: requiredString(row, 'title', endpoint),
        scheduleLabel: requiredString(row, 'schedule_label', endpoint),
        stepCount: count(row.step_count),
        paused: flag(row.paused),
        todayStatus: optional(row.today_status, RUN_STATUSES),
        todayDone: typeof row.today_done === 'number' ? row.today_done : null,
        todayTotal: typeof row.today_total === 'number' ? row.today_total : null,
        todayProgressLabel: text(row.today_progress_label),
      } satisfies CaregiverRoutine;
    }),
    scopeNote: requiredString(body, 'scope_note', endpoint),
  };
}
