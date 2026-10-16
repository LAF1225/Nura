/**
 * The alarm form (PRD 12, sections 10, 11, 54 and 60's AlarmFormScreen).
 *
 * **Section 11's sentence is on this screen too**, because somebody deciding
 * whether to rely on an alarm is exactly who needs it, and the list's copy is
 * not in front of them while they fill the form in.
 *
 * The sound and vibration controls store a choice. **Nothing in this project
 * has ever played a sound or produced a vibration**, and the note says so
 * rather than the controls implying otherwise.
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
import { ALARM_SOUNDS } from '../../src/features/productivity/api';
import {
  ALARM_FORM_NOTE,
  DAYS_LABEL,
  LABEL_LABEL,
  REPEAT_LABEL,
  REPEAT_LABELS,
  SAVE,
  SOUND_LABEL,
  TIME_HINT,
  TIME_LABEL,
  VIBRATION_LABEL,
  WEEKDAY_NAMES,
} from '../../src/features/productivity/copy';
import {
  useAlarms,
  useCreateAlarm,
  useDeleteAlarm,
  useUpdateAlarm,
} from '../../src/features/productivity/hooks';
import type { AlarmRecurrence, AlarmSound } from '../../src/features/productivity/types';
import {
  hasErrors,
  validateAlarm,
  type Errors,
} from '../../src/features/productivity/validation';
import { localDateString } from '../../src/utils/date';
import { spacing } from '../../src/theme/tokens';

const REPEATS: AlarmRecurrence[] = ['one_time', 'daily', 'selected_days'];

const REPEAT_DESCRIPTIONS: Record<AlarmRecurrence, string> = {
  one_time: 'Once, today or tomorrow.',
  daily: 'Every day at the same time.',
  selected_days: 'On the days you choose.',
};

const SOUND_DESCRIPTIONS: Record<AlarmSound, string> = {
  default: 'Your phone decides.',
  gentle: 'Quieter.',
  chime: 'A short chime.',
  bell: 'A bell.',
};

export default function AlarmFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const alarmId = typeof params.id === 'string' ? params.id : null;

  const alarms = useAlarms();
  const existing = alarms.data?.alarms.find((alarm) => alarm.id === alarmId) ?? null;

  const [label, setLabel] = useState(existing?.label ?? '');
  const [time, setTime] = useState(existing?.timeOfDay.slice(0, 5) ?? '');
  const [repeat, setRepeat] = useState<AlarmRecurrence>(existing?.recurrence ?? 'daily');
  const [weekdays, setWeekdays] = useState<number[]>(existing?.weekdays ?? []);
  const [sound, setSound] = useState<AlarmSound>(existing?.soundKey ?? 'default');
  const [vibration, setVibration] = useState(existing?.vibration ?? true);
  const [errors, setErrors] = useState<Errors>({});

  const create = useCreateAlarm();
  const update = useUpdateAlarm();
  const remove = useDeleteAlarm();

  const toggleDay = (day: number) =>
    setWeekdays((current) =>
      current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day].sort((left, right) => left - right)
    );

  const save = () => {
    const next = validateAlarm({ label, time, recurrence: repeat, weekdays });
    setErrors(next);
    if (hasErrors(next)) return;

    const input = {
      label: label.trim(),
      timeOfDay: time,
      recurrence: repeat,
      weekdays: repeat === 'selected_days' ? weekdays : null,
      onDate: repeat === 'one_time' ? localDateString(new Date()) : null,
      soundKey: sound,
      vibration,
    };

    if (alarmId !== null) {
      update.mutate({ alarmId, input }, { onSuccess: () => router.back() });
      return;
    }
    create.mutate(input, { onSuccess: () => router.back() });
  };

  return (
    <Screen>
      <View style={{ gap: spacing.md }}>
        <Card accessible accessibilityLabel={ALARM_FORM_NOTE}>
          <AppText variant="body" tone="secondary">
            {ALARM_FORM_NOTE}
          </AppText>
        </Card>

        <TextField
          label={LABEL_LABEL}
          value={label}
          onChangeText={setLabel}
          error={errors.label ?? null}
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
          {REPEATS.map((value) => (
            <SelectableCard
              key={value}
              title={REPEAT_LABELS[value] ?? value}
              description={REPEAT_DESCRIPTIONS[value]}
              selected={repeat === value}
              onPress={() => setRepeat(value)}
            />
          ))}
        </View>

        {repeat === 'selected_days' ? (
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

        <View style={{ gap: spacing.sm }}>
          <AppText variant="bodyStrong">{SOUND_LABEL}</AppText>
          {ALARM_SOUNDS.map((value) => (
            <SelectableCard
              key={value}
              title={value === 'default' ? 'Default' : value}
              description={SOUND_DESCRIPTIONS[value]}
              selected={sound === value}
              onPress={() => setSound(value)}
            />
          ))}
        </View>

        <ToggleRow label={VIBRATION_LABEL} value={vibration} onChange={setVibration} />

        <Button label={SAVE} onPress={save} accessibilityHint="Saves this alarm" />

        {alarmId !== null ? (
          <Button
            label="Delete"
            variant="ghost"
            onPress={() => remove.mutate(alarmId, { onSuccess: () => router.back() })}
            accessibilityHint="Removes this alarm"
          />
        ) : null}
      </View>
    </Screen>
  );
}
