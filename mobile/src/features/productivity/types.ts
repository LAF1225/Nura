/**
 * Tasks, reminders, alarms and routines, as the app sees them (PRD 12).
 *
 * Mirrors the backend's `app/schemas/productivity.py` field for field, in
 * camelCase. Three things the types carry on purpose.
 *
 * **Labels come from the server.** `dueLabel`, `scheduleLabel`,
 * `progressLabel` and `limitation` are rendered by
 * `services/productivity/wording.py`, which is the one place that writes
 * daily-life prose. A client that reassembled them would be a second place
 * they could disagree -- and the alarm limitation is a sentence no client gets
 * to leave out (PRD 12, section 11).
 *
 * **A task may have no due date at all**, so `dueAt`, `dueLocalDate` and
 * `dueLabel` are all nullable together. That is the common case, not a
 * half-filled task (section 5).
 *
 * **Two timestamps, not one.** `contentUpdatedAt` and `statusChangedAt` are
 * separate because section 40 requires that a completion cannot be undone by
 * an unrelated title edit from another device. The client sends
 * `clientUpdatedAt` with an edit and the server compares it against the right
 * one.
 */

export type TaskStatus = 'open' | 'completed' | 'archived' | 'cancelled';
export type TaskPriority = 'normal' | 'important';
export type DailyLifeSource =
  'user' | 'assistant' | 'caregiver_suggestion' | 'import_future';

export type ReminderRecurrence =
  'one_time' | 'daily' | 'selected_days' | 'weekly' | 'monthly';
export type ReminderStatus = 'active' | 'paused' | 'completed' | 'cancelled';
export type OccurrenceStatus =
  'scheduled' | 'completed' | 'dismissed' | 'snoozed' | 'missed' | 'cancelled';

export type AlarmRecurrence = 'one_time' | 'daily' | 'selected_days';
export type AlarmSound = 'default' | 'gentle' | 'chime' | 'bell';

export type RoutineScheduleType = 'daily' | 'selected_days';
export type RoutineStatus = 'active' | 'paused' | 'archived';
export type RoutineRunStatus =
  'scheduled' | 'in_progress' | 'completed' | 'skipped' | 'missed' | 'cancelled';
export type RoutineStepState = 'completed' | 'skipped';

export type ItemWindow = 'upcoming' | 'due' | 'overdue' | 'completed';

export type CapabilityKey =
  | 'tasks'
  | 'reminders'
  | 'alarms'
  | 'routines'
  | 'weather'
  | 'news'
  | 'external_calendar';
export type CapabilityState = 'available' | 'not_configured' | 'unavailable';

/** The snooze durations the server offers. */
export type SnoozeMinutes = 10 | 30 | 60;

/** Whether something has reached the backend yet. A client-only idea. */
export type SyncStatus = 'synced' | 'pending';

export interface Task {
  id: string;
  profileId: string;
  title: string;
  notes: string | null;
  status: TaskStatus;
  statusLabel: string;
  priority: TaskPriority;
  priorityLabel: string;
  dueAt: string | null;
  dueLocalDate: string | null;
  timezone: string;
  /** "Today, 4:00 PM". Null for a task with no due date. */
  dueLabel: string | null;
  /** Derived by the server on every read. A fact about a clock, not an alert. */
  overdue: boolean;
  source: DailyLifeSource;
  sourceLabel: string;
  completedAt: string | null;
  archivedAt: string | null;
  cancelledAt: string | null;
  contentUpdatedAt: string | null;
  statusChangedAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Set by the app for a task saved on this phone and not yet sent. */
  syncStatus?: SyncStatus;
}

export interface TaskInput {
  title: string;
  notes?: string | null;
  priority?: TaskPriority;
  dueAt?: string | null;
  timezone?: string;
  clientTaskId?: string;
}

export interface TaskEdit {
  title?: string;
  notes?: string | null;
  priority?: TaskPriority;
  dueAt?: string | null;
  timezone?: string;
  /** When the user made this edit, so a stale one cannot win (section 40). */
  clientUpdatedAt?: string;
}

export interface TaskList {
  tasks: Task[];
  openCount: number;
  overdueCount: number;
}

export interface ReminderOccurrence {
  id: string;
  reminderId: string;
  profileId: string;
  title: string;
  body: string | null;
  scheduledFor: string;
  localDate: string;
  status: OccurrenceStatus;
  statusLabel: string;
  window: ItemWindow;
  actionAt: string | null;
  snoozedUntil: string | null;
  snoozeCount: number;
  canSnooze: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Reminder {
  id: string;
  profileId: string;
  title: string;
  body: string | null;
  recurrence: ReminderRecurrence;
  recurrenceLabel: string;
  /** "Every day at 7:30 AM" -- the whole pattern as one sentence. */
  scheduleLabel: string;
  timezone: string;
  startDate: string;
  endDate: string | null;
  timeOfDay: string;
  weekdays: number[] | null;
  dayOfMonth: number | null;
  status: ReminderStatus;
  statusLabel: string;
  notificationEnabled: boolean;
  /** Section 9's sentence, when the reminder will be silent. */
  notificationNote: string | null;
  source: DailyLifeSource;
  sourceLabel: string;
  pausedAt: string | null;
  nextOccurrenceAt: string | null;
  createdAt: string;
  updatedAt: string;
  /** Present on a detail read. */
  occurrences?: ReminderOccurrence[];
}

export interface ReminderInput {
  title: string;
  timeOfDay: string;
  startDate: string;
  recurrence?: ReminderRecurrence;
  timezone?: string;
  body?: string | null;
  endDate?: string | null;
  weekdays?: number[] | null;
  dayOfMonth?: number | null;
  notificationEnabled?: boolean;
  clientReminderId?: string;
}

export interface ReminderList {
  reminders: Reminder[];
  dueCount: number;
}

export interface Alarm {
  id: string;
  profileId: string;
  label: string;
  timeOfDay: string;
  timezone: string;
  recurrence: AlarmRecurrence;
  recurrenceLabel: string;
  scheduleLabel: string;
  weekdays: number[] | null;
  onDate: string | null;
  enabled: boolean;
  soundKey: AlarmSound;
  soundLabel: string;
  vibration: boolean;
  /** Derived on every read. Null for a disabled alarm or a past one-off. */
  nextFireAt: string | null;
  source: DailyLifeSource;
  createdAt: string;
  updatedAt: string;
}

export interface AlarmInput {
  label: string;
  timeOfDay: string;
  recurrence?: AlarmRecurrence;
  timezone?: string;
  weekdays?: number[] | null;
  onDate?: string | null;
  enabled?: boolean;
  soundKey?: AlarmSound;
  vibration?: boolean;
  clientAlarmId?: string;
}

export interface AlarmList {
  alarms: Alarm[];
  enabledCount: number;
  /**
   * What an alarm in this build can and cannot do (section 11). Sent with
   * every response, so a screen cannot ship without it. **No alarm has ever
   * fired on a physical phone.**
   */
  limitation: string;
}

export interface RoutineStep {
  id: string;
  routineId: string;
  title: string;
  position: number;
  optional: boolean;
}

export interface StepCompletion {
  id: string;
  stepId: string;
  state: RoutineStepState;
  stateLabel: string;
  completedAt: string;
}

export interface RoutineRun {
  id: string;
  routineId: string;
  profileId: string;
  routineTitle: string;
  scheduledFor: string;
  localDate: string;
  status: RoutineRunStatus;
  statusLabel: string;
  startedAt: string | null;
  completedAt: string | null;
  totalSteps: number;
  completedSteps: number;
  skippedSteps: number;
  /** "2 of 3 complete. Next: Stretch" -- section 33's own line. */
  progressLabel: string;
  nextStepId: string | null;
  nextStepTitle: string | null;
  completions: StepCompletion[];
}

export interface Routine {
  id: string;
  profileId: string;
  title: string;
  description: string | null;
  scheduleType: RoutineScheduleType;
  scheduleLabel: string;
  timezone: string;
  timeOfDay: string;
  weekdays: number[] | null;
  startDate: string;
  endDate: string | null;
  status: RoutineStatus;
  statusLabel: string;
  pausedAt: string | null;
  source: DailyLifeSource;
  sourceLabel: string;
  steps: RoutineStep[];
  /** Null means the routine does not run today, which is not "not started". */
  todayRun: RoutineRun | null;
  createdAt: string;
  updatedAt: string;
}

export interface RoutineStepInput {
  title: string;
  optional?: boolean;
}

export interface RoutineInput {
  title: string;
  timeOfDay: string;
  startDate: string;
  scheduleType?: RoutineScheduleType;
  timezone?: string;
  description?: string | null;
  weekdays?: number[] | null;
  endDate?: string | null;
  steps: RoutineStepInput[];
  clientRoutineId?: string;
}

export interface RoutineEdit {
  title?: string;
  description?: string | null;
  scheduleType?: RoutineScheduleType;
  timezone?: string;
  timeOfDay?: string;
  weekdays?: number[] | null;
  startDate?: string;
  endDate?: string | null;
  /** Replaces the whole list, in the order given (section 48). */
  steps?: RoutineStepInput[];
}

export interface RoutineList {
  routines: Routine[];
  activeCount: number;
}

export interface TaskCounts {
  dueToday: number;
  overdue: number;
  openTotal: number;
}

export interface ReminderCounts {
  dueToday: number;
  dueNow: number;
}

export interface RoutineCounts {
  dueToday: number;
  inProgress: number;
  completedToday: number;
}

/** The Today card's block, and what the Care card reads (section 58). */
export interface DailyLifeSummary {
  tasks: TaskCounts;
  reminders: ReminderCounts;
  routines: RoutineCounts;
  nextAlarmAt: string | null;
  alarmCount: number;
  /** "3 tasks, 1 routine and 2 reminders today." */
  summaryLabel: string;
  /** False for anybody who has never made one, and the card is not drawn. */
  hasAnything: boolean;
}

export interface Capability {
  key: CapabilityKey;
  state: CapabilityState;
  label: string;
  /** The sentence for this state -- the PRD's own, for the external three. */
  sentence: string;
}

export interface ExternalCapabilities {
  profileId: string;
  capabilities: Capability[];
  external: Record<string, CapabilityState>;
  /** False in every deployment today. */
  anyExternalConfigured: boolean;
}

/** One routine as a caregiver sees it. Narrower than `Routine` on purpose. */
export interface CaregiverRoutine {
  routineId: string;
  title: string;
  scheduleLabel: string;
  stepCount: number;
  paused: boolean;
  todayStatus: RoutineRunStatus | null;
  todayDone: number | null;
  todayTotal: number | null;
  todayProgressLabel: string | null;
}

export interface CaregiverRoutineList {
  routines: CaregiverRoutine[];
  /** Section 42, said on the caregiver's own screen. */
  scopeNote: string;
}

// --- offline queues (sections 37, 38 and 39) --------------------------------

/** A task written on this phone and not yet sent. */
export interface PendingTask {
  clientTaskId: string;
  title: string;
  notes: string | null;
  priority: TaskPriority;
  dueAt: string | null;
  timezone: string;
  savedAt: string;
}

/** One action on a task, queued. One per task: the last decision wins. */
export interface PendingTaskAction {
  taskId: string;
  action: 'complete' | 'reopen' | 'archive' | 'cancel';
  /** When the user pressed it, which is what settles a conflict. */
  clientUpdatedAt: string;
}

/** A reminder written offline. */
export interface PendingReminder {
  clientReminderId: string;
  input: ReminderInput;
  savedAt: string;
}

/** A routine step ticked offline. */
export interface PendingStepCompletion {
  clientCompletionId: string;
  runId: string;
  stepId: string;
  state: RoutineStepState;
  completedAt: string;
}
