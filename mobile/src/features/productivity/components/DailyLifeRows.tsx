/**
 * The rows and cards the daily-life screens are built from.
 *
 * PRD 12, sections 6, 9, 11, 19, 33, 48 and 61.
 *
 * Three decisions, all of them section 48's accessibility requirements made
 * concrete.
 *
 * **Nothing is carried by colour alone.** A done task reads as "Call the
 * physiotherapist. Done." to a screen reader and shows a tick, not a green
 * tint; an overdue one says "Past its due time" in words. Section 48 asks for
 * non-colour-only completion states and this is where that is kept.
 *
 * **Reordering has buttons, not only a drag.** Section 48: *if drag-and-drop
 * exists, also provide Move Up / Move Down.* There is no drag at all here --
 * the buttons are the whole mechanism, which is simpler and reachable by
 * everybody.
 *
 * **Every label a row shows about scheduling comes from the server.** A due
 * label, a schedule sentence, a progress line and the alarm limitation are
 * written by `services/productivity/wording.py`, so this file renders prose
 * rather than composing it.
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListRow,
  StatusChip,
  ToggleRow,
} from '../../../components';
import type { StatusTone } from '../../../components';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, spacing } from '../../../theme/tokens';
import {
  CAPABILITY_STATE_LABELS,
  MOVE_DOWN,
  MOVE_UP,
  PENDING_BADGE,
  REMOVE_STEP,
  stepAccessibilityLabel,
  taskAccessibilityLabel,
} from '../copy';
import type {
  Alarm,
  Capability,
  Reminder,
  ReminderOccurrence,
  Routine,
  RoutineRun,
  RoutineStep,
  StepCompletion,
  Task,
} from '../types';

// --- tasks ------------------------------------------------------------------

interface TaskRowProps {
  task: Task;
  onToggle: () => void;
  onOpen?: () => void;
}

/**
 * One task, with a tick box that is the whole interaction.
 *
 * The box is its own pressable with its own accessible label, so somebody
 * using a screen reader can mark a task done without opening it -- which is
 * the common case and should be one gesture.
 */
export function TaskRow({ task, onToggle, onOpen }: TaskRowProps) {
  const theme = useTheme();
  const done = task.status === 'completed';
  const pending = task.syncStatus === 'pending';

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: spacing.xs,
      }}
    >
      <Pressable
        onPress={onToggle}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: done }}
        accessibilityLabel={taskAccessibilityLabel(task.title, done, task.overdue)}
        accessibilityHint={done ? 'Marks this task as not done' : 'Marks this task done'}
        style={{
          minWidth: minTouchTarget,
          minHeight: minTouchTarget,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons
          name={done ? 'checkmark-circle' : 'ellipse-outline'}
          size={iconSize.md}
          color={done ? theme.colors.success : theme.colors.textSecondary}
        />
      </Pressable>

      <Pressable
        onPress={onOpen}
        disabled={onOpen === undefined}
        accessibilityRole={onOpen ? 'button' : 'text'}
        accessibilityLabel={task.title}
        accessibilityHint={onOpen ? 'Opens this task' : undefined}
        style={{ flex: 1, minHeight: minTouchTarget, justifyContent: 'center' }}
      >
        <AppText variant="bodyStrong" tone={done ? 'secondary' : 'primary'}>
          {task.title}
        </AppText>
        {task.dueLabel ? (
          <AppText variant="caption" tone={task.overdue ? 'danger' : 'secondary'}>
            {task.overdue ? `${task.dueLabel} · past its due time` : task.dueLabel}
          </AppText>
        ) : null}
        {pending ? (
          <AppText variant="caption" tone="secondary">
            {PENDING_BADGE}
          </AppText>
        ) : null}
      </Pressable>

      {task.priority === 'important' && !done ? (
        <StatusChip label={task.priorityLabel} tone="warning" />
      ) : null}
    </View>
  );
}

// --- reminders --------------------------------------------------------------

interface ReminderRowProps {
  reminder: Reminder;
  onOpen?: () => void;
}

export function ReminderRow({ reminder, onOpen }: ReminderRowProps) {
  const paused = reminder.status !== 'active';
  const description = paused
    ? `${reminder.scheduleLabel} · ${reminder.statusLabel}`
    : reminder.scheduleLabel;

  return (
    <ListRow
      label={reminder.title}
      description={description}
      leadingIcon="notifications-outline"
      showChevron={onOpen !== undefined}
      onPress={onOpen}
      accessibilityHint={onOpen ? 'Opens this reminder' : undefined}
    />
  );
}

interface OccurrenceRowProps {
  occurrence: ReminderOccurrence;
  onDone: () => void;
  onDismiss: () => void;
  onSnooze: () => void;
}

/**
 * One moment waiting for an answer, with section 8's three actions.
 *
 * Three buttons rather than a swipe: Done, Snooze and Dismiss are three
 * different facts, and a gesture that did one of them would be a gesture
 * somebody has to remember.
 */
export function OccurrenceRow({
  occurrence,
  onDone,
  onDismiss,
  onSnooze,
}: OccurrenceRowProps) {
  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{occurrence.title}</AppText>
        {occurrence.body ? (
          <AppText variant="body" tone="secondary">
            {occurrence.body}
          </AppText>
        ) : null}
        <AppText variant="caption" tone="secondary">
          {occurrence.statusLabel}
        </AppText>
      </View>

      <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
        <Button label="Done" onPress={onDone} accessibilityHint="Marks this done" />
        {occurrence.canSnooze ? (
          <Button
            label="Snooze"
            variant="secondary"
            onPress={onSnooze}
            accessibilityHint="Puts this off for a while"
          />
        ) : null}
        <Button
          label="Dismiss"
          variant="ghost"
          onPress={onDismiss}
          accessibilityHint="Clears this without doing it"
        />
      </View>
    </Card>
  );
}

// --- alarms -----------------------------------------------------------------

interface AlarmRowProps {
  alarm: Alarm;
  onToggle: (enabled: boolean) => void;
  onOpen?: () => void;
}

export function AlarmRow({ alarm, onToggle, onOpen }: AlarmRowProps) {
  return (
    <View style={{ gap: spacing.xxs }}>
      <ToggleRow
        label={alarm.label}
        description={alarm.scheduleLabel}
        value={alarm.enabled}
        onChange={onToggle}
      />
      {onOpen ? (
        <Button
          label="Edit"
          variant="ghost"
          onPress={onOpen}
          accessibilityHint={`Opens the alarm ${alarm.label}`}
        />
      ) : null}
    </View>
  );
}

/**
 * **Section 11's sentence, wherever an alarm is shown.**
 *
 * The text comes from the server with every alarm list, so this component
 * cannot soften it and a screen cannot leave it out by forgetting a string.
 * It is announced as a note rather than drawn as fine print.
 */
export function AlarmLimitationNote({ limitation }: { limitation: string }) {
  return (
    <Card accessible accessibilityLabel={limitation}>
      <AppText variant="body" tone="secondary">
        {limitation}
      </AppText>
    </Card>
  );
}

// --- routines ---------------------------------------------------------------

interface RoutineCardProps {
  routine: Routine;
  onOpen: () => void;
}

export function RoutineCard({ routine, onOpen }: RoutineCardProps) {
  const run = routine.todayRun;
  const tone: StatusTone = routine.status === 'active' ? 'success' : 'neutral';

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <AppText variant="heading" style={{ flex: 1 }}>
            {routine.title}
          </AppText>
          <StatusChip label={routine.statusLabel} tone={tone} />
        </View>
        <AppText variant="body" tone="secondary">
          {routine.scheduleLabel}
        </AppText>
        {run ? (
          <AppText variant="body" tone="secondary">
            {run.progressLabel}
          </AppText>
        ) : null}
        {routine.source !== 'user' ? (
          <AppText variant="caption" tone="secondary">
            {routine.sourceLabel}
          </AppText>
        ) : null}
      </View>

      <Button
        label={run ? 'Open today' : 'Open'}
        onPress={onOpen}
        accessibilityHint={`Opens the routine ${routine.title}`}
      />
    </Card>
  );
}

interface RoutineStepRowProps {
  step: RoutineStep;
  completion: StepCompletion | null;
  onToggle: () => void;
  onSkip?: () => void;
}

/**
 * One step of a run.
 *
 * The state is in the accessible label as well as the icon, which is section
 * 48's non-colour-only requirement -- a tick and a dash look different, and a
 * screen reader hears "Done" or "Skipped" either way.
 */
export function RoutineStepRow({
  step,
  completion,
  onToggle,
  onSkip,
}: RoutineStepRowProps) {
  const theme = useTheme();
  const state = completion?.state ?? null;
  const icon =
    state === 'completed'
      ? 'checkmark-circle'
      : state === 'skipped'
        ? 'remove-circle-outline'
        : 'ellipse-outline';
  const colour =
    state === 'completed'
      ? theme.colors.success
      : state === 'skipped'
        ? theme.colors.textSecondary
        : theme.colors.textSecondary;

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        paddingVertical: spacing.xs,
      }}
    >
      <Pressable
        onPress={onToggle}
        accessibilityRole="checkbox"
        accessibilityState={{ checked: state === 'completed' }}
        accessibilityLabel={stepAccessibilityLabel(step.title, state)}
        accessibilityHint={state === null ? 'Marks this step done' : 'Clears this step'}
        style={{
          minWidth: minTouchTarget,
          minHeight: minTouchTarget,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Ionicons name={icon} size={iconSize.md} color={colour} />
      </Pressable>

      <View style={{ flex: 1 }}>
        <AppText variant="body" tone={state === null ? 'primary' : 'secondary'}>
          {step.title}
        </AppText>
        {step.optional ? (
          <AppText variant="caption" tone="secondary">
            Optional
          </AppText>
        ) : null}
      </View>

      {state === null && onSkip ? (
        <Button
          label="Skip"
          variant="ghost"
          onPress={onSkip}
          accessibilityHint={`Marks ${step.title} skipped`}
        />
      ) : null}
    </View>
  );
}

interface EditableStepRowProps {
  title: string;
  index: number;
  total: number;
  onChangeTitle: (value: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  children?: React.ReactNode;
}

/**
 * A step while a routine is being edited, with Move Up and Move Down.
 *
 * **There is no drag-and-drop anywhere in this feature.** Section 48 asks for
 * these buttons as an alternative to one; having only the buttons is simpler,
 * works with a screen reader and a switch control, and removes the whole
 * question of an accessible drag.
 */
export function EditableStepRow({
  title,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onRemove,
  children,
}: EditableStepRowProps) {
  return (
    <View style={{ gap: spacing.xs }}>
      {children}
      <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
        <Button
          label={MOVE_UP}
          variant="ghost"
          disabled={index === 0}
          onPress={onMoveUp}
          accessibilityHint={`Moves ${title} earlier`}
        />
        <Button
          label={MOVE_DOWN}
          variant="ghost"
          disabled={index >= total - 1}
          onPress={onMoveDown}
          accessibilityHint={`Moves ${title} later`}
        />
        <Button
          label={REMOVE_STEP}
          variant="ghost"
          onPress={onRemove}
          accessibilityHint={`Removes ${title}`}
        />
      </View>
    </View>
  );
}

interface RunProgressProps {
  run: RoutineRun;
}

export function RunProgress({ run }: RunProgressProps) {
  return (
    <Card accessible accessibilityLabel={`${run.routineTitle}. ${run.progressLabel}`}>
      <AppText variant="heading">{run.routineTitle}</AppText>
      <AppText variant="body" tone="secondary">
        {run.progressLabel}
      </AppText>
      <AppText variant="caption" tone="secondary">
        {run.statusLabel}
      </AppText>
    </Card>
  );
}

// --- external capabilities (sections 25-29) ---------------------------------

/**
 * One thing Nura can or cannot reach.
 *
 * The sentence is the server's -- for weather, news and an external calendar
 * it is the PRD's own wording -- so this row cannot say anything softer than
 * "not configured in this build".
 */
export function ExternalCapabilityRow({ capability }: { capability: Capability }) {
  const tone: StatusTone =
    capability.state === 'available'
      ? 'success'
      : capability.state === 'unavailable'
        ? 'warning'
        : 'neutral';

  return (
    <View
      style={{ gap: spacing.xxs, paddingVertical: spacing.xs }}
      accessible
      accessibilityLabel={`${capability.label}. ${capability.sentence}`}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        <AppText variant="bodyStrong" style={{ flex: 1 }}>
          {capability.label}
        </AppText>
        <StatusChip label={CAPABILITY_STATE_LABELS[capability.state]} tone={tone} />
      </View>
      <AppText variant="caption" tone="secondary">
        {capability.sentence}
      </AppText>
    </View>
  );
}
