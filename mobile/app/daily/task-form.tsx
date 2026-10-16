/**
 * The task form (PRD 12, sections 5, 6, 37 and 60's TaskFormScreen).
 *
 * Section 6's own layout: title, due, priority, notes, Save. Three decisions.
 *
 * **A due date is optional and says so.** Section 5 is explicit that a task
 * may have none, and the hint under the field says a task without one is a
 * normal task -- not a half-filled one.
 *
 * **The date and time are two plain text fields.** An accessible date picker
 * is a real requirement (section 48) and a native picker that a screen reader
 * can drive is not something this build has verified on a handset, so the
 * honest control is a labelled field with its format in the hint and
 * validation that says what is wrong. The same choice PRD 7's appointment form
 * made.
 *
 * **Saving works offline.** `useCreateTask` queues the task with a client id
 * if the request cannot go, and the screen says it was saved on this phone
 * (section 37).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SelectableCard,
  TextField,
} from '../../src/components';
import {
  DUE_DATE_HINT,
  DUE_LABEL,
  NOTES_LABEL,
  PENDING_NOTE,
  PRIORITY_LABEL,
  PRIORITY_LABELS,
  SAVE,
  TIME_HINT,
  TITLE_HINT,
  TITLE_LABEL,
} from '../../src/features/productivity/copy';
import {
  useCreateTask,
  useDeleteTask,
  useTaskAction,
  useTasks,
  useUpdateTask,
} from '../../src/features/productivity/hooks';
import type { TaskPriority } from '../../src/features/productivity/types';
import {
  hasErrors,
  taskDueAt,
  validateTask,
  type Errors,
} from '../../src/features/productivity/validation';
import { spacing } from '../../src/theme/tokens';

/**
 * What "important" means, said plainly.
 *
 * It raises a row's prominence in the app. It is not an alert, it notifies
 * nobody, and section 18 keeps all of this well below anything
 * safety-critical -- so the description says what it does rather than
 * implying urgency.
 */
const PRIORITY_DESCRIPTIONS: Record<TaskPriority, string> = {
  normal: 'Shows in the usual order.',
  important: 'Shows nearer the top. Nobody is notified.',
};

export default function TaskFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const taskId = typeof params.id === 'string' ? params.id : null;

  const open = useTasks('open');
  const existing = open.data?.tasks.find((task) => task.id === taskId) ?? null;

  const [title, setTitle] = useState(existing?.title ?? '');
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [priority, setPriority] = useState<TaskPriority>(existing?.priority ?? 'normal');
  const [dueDate, setDueDate] = useState(existing?.dueLocalDate ?? '');
  const [dueTime, setDueTime] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [pending, setPending] = useState(false);

  const create = useCreateTask();
  const update = useUpdateTask();
  const remove = useDeleteTask();
  const action = useTaskAction();

  const save = () => {
    const draft = { title, dueDate, dueTime };
    const next = validateTask(draft);
    setErrors(next);
    if (hasErrors(next)) return;

    const dueAt = taskDueAt(draft);

    if (taskId !== null) {
      update.mutate(
        {
          taskId,
          edit: {
            title: title.trim(),
            notes: notes.trim().length > 0 ? notes.trim() : null,
            priority,
            dueAt,
          },
        },
        { onSuccess: () => router.back() }
      );
      return;
    }

    create.mutate(
      {
        title: title.trim(),
        notes: notes.trim().length > 0 ? notes.trim() : null,
        priority,
        dueAt,
      },
      {
        onSuccess: (outcome) => {
          if (outcome.status === 'pending') {
            setPending(true);
            return;
          }
          router.back();
        },
      }
    );
  };

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <TextField
          label={TITLE_LABEL}
          hint={TITLE_HINT}
          value={title}
          onChangeText={setTitle}
          error={errors.title ?? null}
        />

        <Card style={{ gap: spacing.sm }}>
          <AppText variant="bodyStrong">{DUE_LABEL}</AppText>
          <AppText variant="caption" tone="secondary">
            {DUE_DATE_HINT}
          </AppText>
          <TextField
            label="Date"
            hint="YYYY-MM-DD"
            value={dueDate}
            onChangeText={setDueDate}
            error={errors.dueDate ?? null}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
          />
          <TextField
            label="Time"
            hint={TIME_HINT}
            value={dueTime}
            onChangeText={setDueTime}
            error={errors.dueTime ?? null}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
          />
        </Card>

        <View style={{ gap: spacing.sm }}>
          <AppText variant="bodyStrong">{PRIORITY_LABEL}</AppText>
          {(['normal', 'important'] as TaskPriority[]).map((value) => (
            <SelectableCard
              key={value}
              title={PRIORITY_LABELS[value]}
              description={PRIORITY_DESCRIPTIONS[value]}
              selected={priority === value}
              onPress={() => setPriority(value)}
            />
          ))}
        </View>

        <TextField label={NOTES_LABEL} value={notes} onChangeText={setNotes} multiline />

        {pending ? (
          <Card>
            <AppText variant="body" tone="secondary">
              {PENDING_NOTE}
            </AppText>
          </Card>
        ) : null}

        <Button label={SAVE} onPress={save} accessibilityHint="Saves this task" />

        {taskId !== null ? (
          <View style={{ gap: spacing.sm }}>
            <Button
              label="Archive"
              variant="secondary"
              onPress={() =>
                action.mutate(
                  { taskId, action: 'archive' },
                  { onSuccess: () => router.back() }
                )
              }
              accessibilityHint="Keeps this task but takes it off the list"
            />
            <Button
              label="Delete"
              variant="ghost"
              onPress={() => remove.mutate(taskId, { onSuccess: () => router.back() })}
              accessibilityHint="Removes this task for good"
            />
          </View>
        ) : null}
      </View>
    </Screen>
  );
}
