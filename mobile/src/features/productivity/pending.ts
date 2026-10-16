/**
 * Daily-life writes made offline (PRD 12, sections 37, 38, 39 and 40).
 *
 * The rule this exists to keep: **nothing the user did is silently lost.** If
 * the phone cannot reach the backend, the task, the reminder, the action or
 * the ticked step is written to the device and the row says so, rather than a
 * spinner that ends in nothing.
 *
 * Four small queues rather than one, and the shape of each follows what the
 * thing is.
 *
 * **Creates are queued whole** (sections 37 and 38), each with a
 * client-generated id. The *server* enforces the idempotency: every retry
 * sends the same id and the backend answers a replay with the row it already
 * stored. That is why a send which fails *after* the server accepted it -- a
 * dropped response -- still converges on one record.
 *
 * **Actions are one per task**, not a log of them. Pressing Done and then
 * Archive on the same task should send one final answer, because the server
 * holds one row and the last thing the person decided is the thing they meant.
 * Each entry carries `clientUpdatedAt`, which is what lets the server keep a
 * newer decision made on another device (section 40).
 *
 * **Step completions are queued individually** and are safe to retry, because
 * `(run, step)` is unique on the server -- so an offline queue that sends the
 * same tick twice cannot invent progress (section 39).
 *
 * Where it is stored: AsyncStorage, in the app's private data directory. Not
 * secure storage -- that is for credentials. It does hold titles and step
 * text, which is unavoidable for an offline draft and is why nothing here is
 * ever logged (section 45).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { isRetryable } from '../reliability/retry';
import { createLogger } from '../../utils/logger';
import { completeStep, createReminder, createTask, taskAction } from './api';
import type {
  PendingReminder,
  PendingStepCompletion,
  PendingTask,
  PendingTaskAction,
  ReminderInput,
  TaskInput,
} from './types';

const log = createLogger('productivity');

const TASKS_KEY = 'nura.productivity.pendingTasks';
const TASK_ACTIONS_KEY = 'nura.productivity.pendingTaskActions';
const REMINDERS_KEY = 'nura.productivity.pendingReminders';
const STEPS_KEY = 'nura.productivity.pendingSteps';

/**
 * Which failures are worth sending again -- the shared policy (PRD 13, s30).
 *
 * This file held its own copy of the list until PRD 13, as four other queues
 * did, all five identical. The policy and the reasoning behind each kind now
 * live in `features/reliability/retry.ts`; it is re-exported here because
 * other modules already import the name from this one.
 */
export { isRetryable };

async function read<T>(key: string, guard: (value: unknown) => value is T): Promise<T[]> {
  try {
    const raw = await AsyncStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Entries from an older build, or corrupted ones, are dropped rather than
    // allowed to crash the screen that reads them.
    return parsed.filter(guard);
  } catch {
    return [];
  }
}

async function write<T>(key: string, entries: T[]): Promise<void> {
  if (entries.length === 0) {
    await AsyncStorage.removeItem(key);
    return;
  }
  await AsyncStorage.setItem(key, JSON.stringify(entries));
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : null;
}

function isPendingTask(value: unknown): value is PendingTask {
  const entry = record(value);
  return (
    entry !== null &&
    typeof entry.clientTaskId === 'string' &&
    typeof entry.title === 'string' &&
    typeof entry.savedAt === 'string'
  );
}

function isPendingTaskAction(value: unknown): value is PendingTaskAction {
  const entry = record(value);
  return (
    entry !== null &&
    typeof entry.taskId === 'string' &&
    (entry.action === 'complete' ||
      entry.action === 'reopen' ||
      entry.action === 'archive' ||
      entry.action === 'cancel') &&
    typeof entry.clientUpdatedAt === 'string'
  );
}

function isPendingReminder(value: unknown): value is PendingReminder {
  const entry = record(value);
  return (
    entry !== null &&
    typeof entry.clientReminderId === 'string' &&
    record(entry.input) !== null &&
    typeof entry.savedAt === 'string'
  );
}

function isPendingStep(value: unknown): value is PendingStepCompletion {
  const entry = record(value);
  return (
    entry !== null &&
    typeof entry.clientCompletionId === 'string' &&
    typeof entry.runId === 'string' &&
    typeof entry.stepId === 'string' &&
    typeof entry.completedAt === 'string'
  );
}

// --- reading ----------------------------------------------------------------

export const loadPendingTasks = () => read(TASKS_KEY, isPendingTask);
export const loadPendingTaskActions = () => read(TASK_ACTIONS_KEY, isPendingTaskAction);
export const loadPendingReminders = () => read(REMINDERS_KEY, isPendingReminder);
export const loadPendingSteps = () => read(STEPS_KEY, isPendingStep);

/**
 * A client id a screen can use for a draft.
 *
 * `Math.random` rather than a UUID library: this only has to be unique within
 * one profile's queue, the server enforces the uniqueness that matters, and a
 * collision would simply return the earlier task rather than losing anything.
 */
export function clientId(prefix: string): string {
  const stamp = Date.now().toString(36);
  const noise = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${stamp}-${noise}`;
}

// --- tasks (section 37) -----------------------------------------------------

export interface Outcome<T> {
  /** Null when the write is queued: there is no server answer to show yet. */
  result: T | null;
  /** `pending` means it is saved on this phone and not yet on the server. */
  status: 'synced' | 'pending';
}

/**
 * Creates a task, or keeps it on the phone if that is not possible.
 *
 * Resolves either way: "saved on this phone" is a success from the user's
 * point of view, and the row says which happened. It only rejects when the
 * server refuses the task itself -- too many open tasks, an unknown time zone
 * -- because retrying those later changes nothing.
 */
export async function createTaskOrQueue(
  profileId: string,
  input: TaskInput
): Promise<Outcome<Awaited<ReturnType<typeof createTask>>>> {
  const entry: PendingTask = {
    clientTaskId: input.clientTaskId ?? clientId('task'),
    title: input.title,
    notes: input.notes ?? null,
    priority: input.priority ?? 'normal',
    dueAt: input.dueAt ?? null,
    timezone: input.timezone ?? 'UTC',
    savedAt: new Date().toISOString(),
  };

  try {
    const result = await createTask(profileId, {
      ...input,
      clientTaskId: entry.clientTaskId,
    });
    return { result, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    const existing = await loadPendingTasks();
    await write(TASKS_KEY, [
      ...existing.filter((row) => row.clientTaskId !== entry.clientTaskId),
      entry,
    ]);
    // The title is not logged: a line says what happened, never what.
    log.warn('task saved on this device; will sync later');
    return { result: null, status: 'pending' };
  }
}

/** Replaces any queued action for the same task. One answer per task. */
export async function queueTaskAction(entry: PendingTaskAction): Promise<void> {
  const existing = await loadPendingTaskActions();
  await write(TASK_ACTIONS_KEY, [
    ...existing.filter((row) => row.taskId !== entry.taskId),
    entry,
  ]);
}

export async function submitTaskActionOrQueue(
  profileId: string,
  taskId: string,
  action: PendingTaskAction['action']
): Promise<Outcome<Awaited<ReturnType<typeof taskAction>>>> {
  const clientUpdatedAt = new Date().toISOString();
  try {
    const result = await taskAction(profileId, taskId, action, clientUpdatedAt);
    const existing = await loadPendingTaskActions();
    await write(
      TASK_ACTIONS_KEY,
      existing.filter((row) => row.taskId !== taskId)
    );
    return { result, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    await queueTaskAction({ taskId, action, clientUpdatedAt });
    log.warn('task action saved on this device; will sync later');
    return { result: null, status: 'pending' };
  }
}

// --- reminders (section 38) -------------------------------------------------

export async function createReminderOrQueue(
  profileId: string,
  input: ReminderInput
): Promise<Outcome<Awaited<ReturnType<typeof createReminder>>>> {
  const entry: PendingReminder = {
    clientReminderId: input.clientReminderId ?? clientId('reminder'),
    input: { ...input },
    savedAt: new Date().toISOString(),
  };

  try {
    const result = await createReminder(profileId, {
      ...input,
      clientReminderId: entry.clientReminderId,
    });
    return { result, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    const existing = await loadPendingReminders();
    await write(REMINDERS_KEY, [
      ...existing.filter((row) => row.clientReminderId !== entry.clientReminderId),
      entry,
    ]);
    log.warn('reminder saved on this device; will sync later');
    return { result: null, status: 'pending' };
  }
}

// --- routine steps (section 39) ---------------------------------------------

export async function completeStepOrQueue(
  profileId: string,
  runId: string,
  stepId: string,
  state: PendingStepCompletion['state'] = 'completed'
): Promise<Outcome<Awaited<ReturnType<typeof completeStep>>>> {
  const entry: PendingStepCompletion = {
    clientCompletionId: clientId('step'),
    runId,
    stepId,
    state,
    completedAt: new Date().toISOString(),
  };

  try {
    const result = await completeStep(profileId, runId, stepId, {
      state,
      completedAt: entry.completedAt,
      clientCompletionId: entry.clientCompletionId,
    });
    return { result, status: 'synced' };
  } catch (error) {
    if (!isRetryable(error)) throw error;
    const existing = await loadPendingSteps();
    // One per (run, step): ticking the same step twice offline is one tick,
    // which is what the server's unique constraint would have done anyway.
    await write(STEPS_KEY, [
      ...existing.filter((row) => !(row.runId === runId && row.stepId === stepId)),
      entry,
    ]);
    log.warn('routine step saved on this device; will sync later');
    return { result: null, status: 'pending' };
  }
}

// --- syncing ----------------------------------------------------------------

export interface SyncSummary {
  sent: number;
  /** Still waiting; those entries are kept. */
  pending: number;
  /** Could never succeed as written, and have been dropped. */
  discarded: number;
}

async function drain<T>(
  key: string,
  entries: T[],
  send: (entry: T) => Promise<unknown>
): Promise<SyncSummary> {
  if (entries.length === 0) return { sent: 0, pending: 0, discarded: 0 };

  const keep: T[] = [];
  let sent = 0;
  let discarded = 0;

  for (const entry of entries) {
    try {
      await send(entry);
      sent += 1;
    } catch (error) {
      if (isRetryable(error)) {
        keep.push(entry);
      } else {
        // The server refused it outright -- most often a row that no longer
        // exists, or a rule that will not allow it. Keeping it would mean
        // retrying forever.
        discarded += 1;
      }
    }
  }

  await write(key, keep);
  return { sent, pending: keep.length, discarded };
}

/**
 * Tries to send everything queued.
 *
 * Safe to call often: it does nothing when the queues are empty, and every
 * write is idempotent on the server -- a create through its client id, an
 * action because it sets a state rather than appending an event, a step
 * completion because `(run, step)` is unique. So a duplicate send leaves the
 * same single row (sections 37, 39 and 40).
 */
export async function syncPendingDailyLife(profileId: string): Promise<SyncSummary> {
  const totals: SyncSummary = { sent: 0, pending: 0, discarded: 0 };

  const add = (summary: SyncSummary) => {
    totals.sent += summary.sent;
    totals.pending += summary.pending;
    totals.discarded += summary.discarded;
  };

  add(
    await drain(TASKS_KEY, await loadPendingTasks(), (entry) =>
      createTask(profileId, {
        title: entry.title,
        notes: entry.notes,
        priority: entry.priority,
        dueAt: entry.dueAt,
        timezone: entry.timezone,
        clientTaskId: entry.clientTaskId,
      })
    )
  );
  add(
    await drain(TASK_ACTIONS_KEY, await loadPendingTaskActions(), (entry) =>
      taskAction(profileId, entry.taskId, entry.action, entry.clientUpdatedAt)
    )
  );
  add(
    await drain(REMINDERS_KEY, await loadPendingReminders(), (entry) =>
      createReminder(profileId, {
        ...entry.input,
        clientReminderId: entry.clientReminderId,
      })
    )
  );
  add(
    await drain(STEPS_KEY, await loadPendingSteps(), (entry) =>
      completeStep(profileId, entry.runId, entry.stepId, {
        state: entry.state,
        completedAt: entry.completedAt,
        clientCompletionId: entry.clientCompletionId,
      })
    )
  );

  if (totals.sent > 0 || totals.discarded > 0) {
    log.info('queued daily-life writes synced', {
      sent: totals.sent,
      discarded: totals.discarded,
    });
  }
  return totals;
}

export async function clearAllPendingDailyLife(): Promise<void> {
  await AsyncStorage.multiRemove([TASKS_KEY, TASK_ACTIONS_KEY, REMINDERS_KEY, STEPS_KEY]);
}

// --- overlaying -------------------------------------------------------------

/**
 * Applies whatever is queued on top of the server's tasks, so a pending write
 * shows immediately rather than reverting on the next refresh.
 *
 * Only the fields the user can actually have changed are overlaid, and each
 * one is flagged `pending` so the row can say it has not synced yet.
 */
export function withPendingTasks<
  Task extends { id: string; status: string; syncStatus?: 'synced' | 'pending' },
>(tasks: Task[], actions: PendingTaskAction[]): Task[] {
  if (actions.length === 0) return tasks;
  const byTask = new Map(actions.map((entry) => [entry.taskId, entry]));
  const statusFor: Record<PendingTaskAction['action'], string> = {
    complete: 'completed',
    reopen: 'open',
    archive: 'archived',
    cancel: 'cancelled',
  };

  return tasks.map((task) => {
    const entry = byTask.get(task.id);
    if (entry === undefined) return task;
    return { ...task, status: statusFor[entry.action], syncStatus: 'pending' as const };
  });
}
