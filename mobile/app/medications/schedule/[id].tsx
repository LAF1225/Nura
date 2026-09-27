/**
 * Creating or changing one reminder schedule (PRD 5, sections 11, 36-39, 42).
 *
 * Three promises this screen keeps, all of them PRD 5's:
 *
 * **Editing changes the future only.** The server rebuilds doses from now
 * forward and never touches one that has been recorded (section 36), so
 * nothing here needs to warn about losing history -- there is none to lose.
 *
 * **Nothing is removed without being asked.** Delete goes through a native
 * alert that says what will happen to the history (section 39).
 *
 * **The reminders on the phone follow the schedule.** Every save, pause and
 * delete rebuilds the OS notifications from the doses that come back, which
 * is what stops a cancelled reminder from firing anyway (section 42).
 *
 * Permission is asked for here and nowhere earlier: somebody turning on a
 * reminder is exactly the moment the request makes sense (section 14).
 */
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { Alert, View } from 'react-native';

import { AppText, Button, Card, Screen, SkeletonCard } from '../../../src/components';
import {
  ScheduleActions,
  ScheduleForm,
} from '../../../src/features/medications/components/ScheduleForm';
import {
  useDeleteSchedule,
  useMedicationSchedules,
  useSaveSchedule,
  useSetSchedulePaused,
  useTodayDoses,
} from '../../../src/features/medications/hooks';
import {
  rebuildReminders,
  requestReminderPermission,
} from '../../../src/features/medications/notifications';
import {
  buildSchedulePayload,
  deviceTimezone,
  describeSchedule,
  initialScheduleValues,
  validateSchedule,
  valuesFromSchedule,
  type ScheduleFormValues,
} from '../../../src/features/medications/schedule';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';
import { localDateString } from '../../../src/utils/date';

export default function MedicationScheduleFormScreen() {
  const { id, medicationId } = useLocalSearchParams<{
    id: string;
    medicationId?: string;
  }>();
  const router = useRouter();
  const navigation = useNavigation();

  const isNew = id === 'new';
  const schedules = useMedicationSchedules();
  const doses = useTodayDoses();
  const save = useSaveSchedule();
  const setPaused = useSetSchedulePaused();
  const remove = useDeleteSchedule();

  const schedule = isNew
    ? null
    : (schedules.data?.find((entry) => entry.id === id) ?? null);

  /**
   * Edits are an overlay on the schedule rather than copied into state when
   * it arrives: nothing to keep in sync, no effect, and the form renders
   * correctly on the first frame it has data.
   */
  const [edits, setEdits] = useState<ScheduleFormValues | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const values =
    edits ??
    (schedule === null
      ? initialScheduleValues(deviceTimezone(), localDateString())
      : valuesFromSchedule(schedule));

  const errors = validateSchedule(values);
  const busy = save.isPending || setPaused.isPending || remove.isPending;

  useLayoutEffect(() => {
    navigation.setOptions({
      title: isNew ? 'Set a reminder' : 'Edit reminder',
    });
  }, [navigation, isNew]);

  /** Makes the phone's pending reminders match whatever the server now says. */
  const refreshReminders = async () => {
    const { data } = await doses.refetch();
    await rebuildReminders(data ?? []);
  };

  const onSave = async () => {
    if (Object.keys(errors).length > 0) {
      setShowErrors(true);
      return;
    }

    const attachTo = schedule?.medicationId ?? medicationId;
    if (!attachTo) return;

    // Asked for here, with the reason plainly in front of the user, and only
    // for a new schedule -- an edit does not need re-asking (PRD 5, s14).
    if (isNew) {
      const granted = await requestReminderPermission();
      setPermissionDenied(!granted);
    }

    save.mutate(
      {
        scheduleId: schedule?.id,
        payload: buildSchedulePayload(attachTo, values),
      },
      {
        onSuccess: async () => {
          await refreshReminders();
          router.back();
        },
      }
    );
  };

  const onTogglePause = () => {
    if (schedule === null) return;
    setPaused.mutate(
      { scheduleId: schedule.id, paused: schedule.isActive },
      { onSuccess: () => void refreshReminders() }
    );
  };

  const onDelete = () => {
    if (schedule === null) return;
    Alert.alert(
      'Remove this reminder?',
      `Nura will stop reminding you about ${schedule.medicationName}. Everything you have already recorded is kept, and the medication stays in your health profile.`,
      [
        { text: 'Keep it', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: () =>
            remove.mutate(schedule.id, {
              onSuccess: async () => {
                await refreshReminders();
                router.back();
              },
            }),
        },
      ]
    );
  };

  if (!isNew && schedules.isLoading) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={4} label="Loading this reminder" />
        </Card>
      </Screen>
    );
  }

  if (!isNew && schedule === null) {
    return (
      <Screen>
        <Card>
          <AppText variant="body" tone="secondary">
            That reminder is no longer here.
          </AppText>
        </Card>
      </Screen>
    );
  }

  if (isNew && !medicationId) {
    return (
      <Screen>
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            Choose which medication this reminder is for.
          </AppText>
          <Button
            label="Choose a medication"
            variant="secondary"
            onPress={() => router.replace('/medications/schedules')}
          />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ gap: spacing.lg }}>
        {schedule ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="heading">
              {schedule.medicationDose
                ? `${schedule.medicationName} — ${schedule.medicationDose}`
                : schedule.medicationName}
            </AppText>
            <AppText variant="body" tone="secondary">
              {describeSchedule(schedule)}
            </AppText>
          </Card>
        ) : null}

        <ScheduleForm
          values={values}
          errors={showErrors ? errors : {}}
          disabled={busy}
          onChange={(next) => setEdits(next)}
        />

        {permissionDenied ? (
          // Honest rather than silent: the schedule is real and the screen
          // will still show what is due; only the phone's alert is off.
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="bodyStrong">Notifications are turned off</AppText>
            <AppText variant="body" tone="secondary">
              Nura will still show what’s due when you open the app, but it can’t alert
              you until notifications are allowed in your phone’s settings.
            </AppText>
          </Card>
        ) : null}

        {save.isError ? (
          <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(save.error)}
          </AppText>
        ) : null}

        <ScheduleActions
          isNew={isNew}
          paused={schedule !== null && !schedule.isActive}
          busy={busy}
          onSave={() => void onSave()}
          onTogglePause={onTogglePause}
          onDelete={onDelete}
        />
      </View>
    </Screen>
  );
}
