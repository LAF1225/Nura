/**
 * The routine form (PRD 12, sections 12, 13, 48 and 60's RoutineFormScreen).
 *
 * **Steps are reordered with Move Up and Move Down, and there is no drag.**
 * Section 48 asks for the buttons as an alternative to a drag; having only the
 * buttons is simpler, works with a screen reader and a switch control, and
 * removes the whole question of an accessible drag gesture.
 *
 * **The whole step list is sent on save**, which is what the server expects
 * (section 48) and what makes reordering one operation rather than three.
 *
 * **Nothing here decides what the steps should be.** Section 24: a routine is
 * what the person or their clinician decided on, typed in their own words.
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
  ToggleRow,
} from '../../src/components';
import { EditableStepRow } from '../../src/features/productivity/components/DailyLifeRows';
import {
  ADD_STEP,
  DAYS_LABEL,
  OPTIONAL_STEP_LABEL,
  REPEAT_LABEL,
  REPEAT_LABELS,
  SAVE,
  STEPS_LABEL,
  TIME_HINT,
  TIME_LABEL,
  TITLE_HINT,
  TITLE_LABEL,
  WEEKDAY_NAMES,
} from '../../src/features/productivity/copy';
import {
  useCreateRoutine,
  useRoutine,
  useUpdateRoutine,
} from '../../src/features/productivity/hooks';
import type {
  RoutineScheduleType,
  RoutineStepInput,
} from '../../src/features/productivity/types';
import {
  hasErrors,
  moveStep,
  usableSteps,
  validateRoutine,
  type Errors,
} from '../../src/features/productivity/validation';
import { localDateString } from '../../src/utils/date';
import { spacing } from '../../src/theme/tokens';

const SCHEDULES: RoutineScheduleType[] = ['daily', 'selected_days'];

const SCHEDULE_DESCRIPTIONS: Record<RoutineScheduleType, string> = {
  daily: 'Every day at the same time.',
  selected_days: 'On the days you choose.',
};

export default function RoutineFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const routineId = typeof params.id === 'string' ? params.id : null;

  const routine = useRoutine(routineId);
  const existing = routine.data ?? null;

  const [title, setTitle] = useState(existing?.title ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [time, setTime] = useState(existing?.timeOfDay.slice(0, 5) ?? '');
  const [schedule, setSchedule] = useState<RoutineScheduleType>(
    existing?.scheduleType ?? 'daily'
  );
  const [weekdays, setWeekdays] = useState<number[]>(existing?.weekdays ?? []);
  const [steps, setSteps] = useState<RoutineStepInput[]>(
    existing?.steps.map((step) => ({
      title: step.title,
      optional: step.optional,
    })) ?? [{ title: '', optional: false }]
  );
  const [errors, setErrors] = useState<Errors>({});

  const create = useCreateRoutine();
  const update = useUpdateRoutine();

  const toggleDay = (day: number) =>
    setWeekdays((current) =>
      current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day].sort((left, right) => left - right)
    );

  const setStep = (index: number, next: Partial<RoutineStepInput>) =>
    setSteps((current) =>
      current.map((step, position) => (position === index ? { ...step, ...next } : step))
    );

  const move = (index: number, by: -1 | 1) =>
    setSteps((current) => moveStep(current, index, by));

  const save = () => {
    const filled = usableSteps(steps);
    const next = validateRoutine({
      title,
      time,
      scheduleType: schedule,
      weekdays,
      steps,
    });
    setErrors(next);
    if (hasErrors(next)) return;

    if (routineId !== null) {
      update.mutate(
        {
          routineId,
          edit: {
            title: title.trim(),
            description: description.trim().length > 0 ? description.trim() : null,
            timeOfDay: time,
            scheduleType: schedule,
            weekdays: schedule === 'selected_days' ? weekdays : null,
            steps: filled,
          },
        },
        { onSuccess: () => router.back() }
      );
      return;
    }

    create.mutate(
      {
        title: title.trim(),
        description: description.trim().length > 0 ? description.trim() : null,
        timeOfDay: time,
        startDate: localDateString(new Date()),
        scheduleType: schedule,
        weekdays: schedule === 'selected_days' ? weekdays : null,
        steps: filled,
      },
      { onSuccess: () => router.back() }
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

        <TextField
          label="Description"
          value={description}
          onChangeText={setDescription}
          multiline
        />

        <TextField
          label={TIME_LABEL}
          hint={TIME_HINT}
          value={time}
          onChangeText={setTime}
          error={errors.time ?? null}
          autoCapitalize="none"
          keyboardType="numbers-and-punctuation"
        />

        <View style={{ gap: spacing.sm }}>
          <AppText variant="bodyStrong">{REPEAT_LABEL}</AppText>
          {SCHEDULES.map((value) => (
            <SelectableCard
              key={value}
              title={REPEAT_LABELS[value] ?? value}
              description={SCHEDULE_DESCRIPTIONS[value]}
              selected={schedule === value}
              onPress={() => setSchedule(value)}
            />
          ))}
        </View>

        {schedule === 'selected_days' ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="bodyStrong">{DAYS_LABEL}</AppText>
            {WEEKDAY_NAMES.map((name, day) => (
              <ToggleRow
                key={name}
                label={name}
                value={weekdays.includes(day)}
                onChange={() => toggleDay(day)}
              />
            ))}
            {errors.weekdays ? (
              <AppText variant="caption" tone="danger" accessibilityRole="alert">
                {errors.weekdays}
              </AppText>
            ) : null}
          </Card>
        ) : null}

        <Card style={{ gap: spacing.md }}>
          <AppText variant="bodyStrong">{STEPS_LABEL}</AppText>
          {steps.map((step, index) => (
            <EditableStepRow
              key={index}
              title={step.title || `Step ${index + 1}`}
              index={index}
              total={steps.length}
              onChangeTitle={(value) => setStep(index, { title: value })}
              onMoveUp={() => move(index, -1)}
              onMoveDown={() => move(index, 1)}
              onRemove={() =>
                setSteps((current) => current.filter((_, position) => position !== index))
              }
            >
              <TextField
                label={`Step ${index + 1}`}
                value={step.title}
                onChangeText={(value) => setStep(index, { title: value })}
              />
              <ToggleRow
                label={OPTIONAL_STEP_LABEL}
                value={step.optional ?? false}
                onChange={(value) => setStep(index, { optional: value })}
              />
            </EditableStepRow>
          ))}
          {errors.steps ? (
            <AppText variant="caption" tone="danger" accessibilityRole="alert">
              {errors.steps}
            </AppText>
          ) : null}
          <Button
            label={ADD_STEP}
            variant="secondary"
            onPress={() =>
              setSteps((current) => [...current, { title: '', optional: false }])
            }
            accessibilityHint="Adds another step to this routine"
          />
        </Card>

        <Button label={SAVE} onPress={save} accessibilityHint="Saves this routine" />
      </View>
    </Screen>
  );
}
