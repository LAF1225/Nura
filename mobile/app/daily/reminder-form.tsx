/**
 * The reminder form (PRD 12, sections 7, 9, 35, 38 and 60).
 *
 * Three decisions.
 *
 * **A reminder must have a time, and the form will not let one through
 * without.** Section 22's clarification rule is about the assistant, but the
 * same thing is true of a form: a reminder with no time is not a reminder.
 *
 * **Monthly says what happens at the end of a short month** (section 35). The
 * 31st becomes the 28th in February, decided deterministically on the server,
 * and the form says so where somebody choosing it can read it rather than
 * leaving them to find out in February.
 *
 * **Notifications can be switched off per reminder, and the row says what that
 * means** (section 9). The reminder is still stored and still on Today.
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
import {
  DAYS_LABEL,
  DAY_OF_MONTH_LABEL,
  MONTH_END_NOTE,
  NOTIFICATION_LABEL,
  PENDING_NOTE,
  REPEAT_LABEL,
  REPEAT_LABELS,
  SAVE,
  TIME_HINT,
  TIME_LABEL,
  TITLE_HINT,
  TITLE_LABEL,
  WEEKDAY_NAMES,
} from '../../src/features/productivity/copy';
import {
  useCreateReminder,
  useDeleteReminder,
  useReminders,
  useSetReminderPaused,
  useUpdateReminder,
} from '../../src/features/productivity/hooks';
import type { ReminderRecurrence } from '../../src/features/productivity/types';
import {
  hasErrors,
  validateReminder,
  type Errors,
} from '../../src/features/productivity/validation';
import { localDateString } from '../../src/utils/date';
import { spacing } from '../../src/theme/tokens';

const REPEATS: ReminderRecurrence[] = [
  'one_time',
  'daily',
  'selected_days',
  'weekly',
  'monthly',
];

const REPEAT_DESCRIPTIONS: Record<ReminderRecurrence, string> = {
  one_time: 'Just the once.',
  daily: 'Every day at the same time.',
  selected_days: 'On the days you choose.',
  weekly: 'The same day each week.',
  monthly: 'The same date each month.',
};

export default function ReminderFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const reminderId = typeof params.id === 'string' ? params.id : null;

  const reminders = useReminders();
  const existing =
    reminders.data?.reminders.find((reminder) => reminder.id === reminderId) ?? null;

  const [title, setTitle] = useState(existing?.title ?? '');
  const [body, setBody] = useState(existing?.body ?? '');
  const [time, setTime] = useState(existing?.timeOfDay.slice(0, 5) ?? '');
  const [repeat, setRepeat] = useState<ReminderRecurrence>(
    existing?.recurrence ?? 'one_time'
  );
  const [weekdays, setWeekdays] = useState<number[]>(existing?.weekdays ?? []);
  const [dayOfMonth, setDayOfMonth] = useState(
    existing?.dayOfMonth ? String(existing.dayOfMonth) : ''
  );
  const [notify, setNotify] = useState(existing?.notificationEnabled ?? true);
  const [errors, setErrors] = useState<Errors>({});
  const [pending, setPending] = useState(false);

  const create = useCreateReminder();
  const update = useUpdateReminder();
  const pause = useSetReminderPaused();
  const remove = useDeleteReminder();

  const toggleDay = (day: number) =>
    setWeekdays((current) =>
      current.includes(day)
        ? current.filter((value) => value !== day)
        : [...current, day].sort((left, right) => left - right)
    );

  const save = () => {
    const next = validateReminder({
      title,
      time,
      recurrence: repeat,
      weekdays,
      dayOfMonth,
    });
    setErrors(next);
    if (hasErrors(next)) return;

    const input = {
      title: title.trim(),
      body: body.trim().length > 0 ? body.trim() : null,
      timeOfDay: time,
      startDate: existing?.startDate ?? localDateString(new Date()),
      recurrence: repeat,
      weekdays: repeat === 'selected_days' || repeat === 'weekly' ? weekdays : null,
      dayOfMonth: repeat === 'monthly' ? Number(dayOfMonth) : null,
      notificationEnabled: notify,
    };

    if (reminderId !== null) {
      update.mutate({ reminderId, input }, { onSuccess: () => router.back() });
      return;
    }

    create.mutate(input, {
      onSuccess: (outcome) => {
        if (outcome.status === 'pending') {
          setPending(true);
          return;
        }
        router.back();
      },
    });
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

        <TextField label="Message" value={body} onChangeText={setBody} multiline />

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

        {repeat === 'selected_days' || repeat === 'weekly' ? (
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

        {repeat === 'monthly' ? (
          <Card style={{ gap: spacing.sm }}>
            <TextField
              label={DAY_OF_MONTH_LABEL}
              hint="1 to 31"
              value={dayOfMonth}
              onChangeText={setDayOfMonth}
              error={errors.dayOfMonth ?? null}
              keyboardType="number-pad"
            />
            <AppText variant="caption" tone="secondary">
              {MONTH_END_NOTE}
            </AppText>
          </Card>
        ) : null}

        <ToggleRow
          label={NOTIFICATION_LABEL}
          description="Turn this off to keep the reminder without a notification."
          value={notify}
          onChange={setNotify}
        />

        {pending ? (
          <Card>
            <AppText variant="body" tone="secondary">
              {PENDING_NOTE}
            </AppText>
          </Card>
        ) : null}

        <Button label={SAVE} onPress={save} accessibilityHint="Saves this reminder" />

        {reminderId !== null && existing ? (
          <View style={{ gap: spacing.sm }}>
            <Button
              label={existing.status === 'paused' ? 'Turn back on' : 'Pause'}
              variant="secondary"
              onPress={() =>
                pause.mutate({
                  reminderId,
                  paused: existing.status !== 'paused',
                })
              }
              accessibilityHint="Stops or restarts this reminder"
            />
            <Button
              label="Delete"
              variant="ghost"
              onPress={() =>
                remove.mutate(reminderId, { onSuccess: () => router.back() })
              }
              accessibilityHint="Removes this reminder for good"
            />
          </View>
        ) : null}
      </View>
    </Screen>
  );
}
