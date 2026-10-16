/**
 * The reminder list, and whatever is waiting for an answer.
 *
 * PRD 12, sections 7, 8, 9, 34 and 60's RemindersScreen.
 *
 * Three decisions.
 *
 * **Due occurrences come first, as cards with Done, Snooze and Dismiss.**
 * Section 8's three actions are three buttons: they are three different facts,
 * and a gesture that did one of them would be a gesture somebody has to
 * remember.
 *
 * **The phone's notifications are rebuilt from what this screen is showing**
 * (section 34). Reconciliation, not notification: the rows are the plan, and
 * `useDailyLifeNotifications` makes the operating system agree with them.
 *
 * **When notifications have been refused the screen says so** (section 9). The
 * reminder is still stored and still on Today; what it will not do is make a
 * sound, and that is said plainly rather than left for somebody to discover.
 */
import { useRouter } from 'expo-router';
import { useMemo } from 'react';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import {
  OccurrenceRow,
  ReminderRow,
} from '../../src/features/productivity/components/DailyLifeRows';
import {
  ADD_REMINDER,
  NOTIFICATIONS_BLOCKED,
  NO_REMINDERS,
  NO_REMINDERS_HINT,
} from '../../src/features/productivity/copy';
import {
  useAlarms,
  useDailyLifeNotifications,
  useNotificationPermission,
  useOccurrenceAction,
  useReminderOccurrences,
  useReminders,
  useSnoozeOccurrence,
  useSyncPendingDailyLife,
} from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

export default function RemindersScreen() {
  const router = useRouter();
  const reminders = useReminders();
  const occurrences = useReminderOccurrences();
  const alarms = useAlarms();
  const act = useOccurrenceAction();
  const snooze = useSnoozeOccurrence();
  useSyncPendingDailyLife();

  const enabledIds = useMemo(
    () =>
      new Set(
        (reminders.data?.reminders ?? [])
          .filter((reminder) => reminder.notificationEnabled)
          .map((reminder) => reminder.id)
      ),
    [reminders.data]
  );

  // Section 34: the phone's pending notifications are brought in step with
  // what the server says is due, every time this screen is shown.
  useDailyLifeNotifications(occurrences.data, alarms.data?.alarms, enabledIds);
  // Section 9: whether they will make a sound is a separate question, asked
  // of the operating system rather than inferred from the rebuild.
  const permitted = useNotificationPermission();

  const data = reminders.data;
  const waiting = (occurrences.data ?? []).filter(
    (row) => row.window === 'due' || row.window === 'overdue'
  );

  return (
    <Screen
      onRefresh={() => {
        void reminders.refetch();
        void occurrences.refetch();
      }}
      refreshing={reminders.isRefetching && !reminders.isLoading}
    >
      {permitted.data === false ? (
        <Card accessible accessibilityLabel={NOTIFICATIONS_BLOCKED}>
          <AppText variant="body" tone="secondary">
            {NOTIFICATIONS_BLOCKED}
          </AppText>
        </Card>
      ) : null}

      <View style={{ height: spacing.md }} />

      <AsyncState
        status={reminders.isError ? 'error' : data ? 'success' : 'loading'}
        error={reminders.error}
        onRetry={() => void reminders.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            {waiting.length > 0 ? (
              <View style={{ gap: spacing.md }}>
                <AppText variant="heading">Waiting for you</AppText>
                {waiting.map((occurrence) => (
                  <OccurrenceRow
                    key={occurrence.id}
                    occurrence={occurrence}
                    onDone={() =>
                      act.mutate({ occurrenceId: occurrence.id, action: 'complete' })
                    }
                    onDismiss={() =>
                      act.mutate({ occurrenceId: occurrence.id, action: 'dismiss' })
                    }
                    onSnooze={() =>
                      snooze.mutate({ occurrenceId: occurrence.id, minutes: 10 })
                    }
                  />
                ))}
              </View>
            ) : null}

            {data.reminders.length === 0 ? (
              <Card style={{ gap: spacing.xxs }}>
                <AppText variant="body" tone="secondary">
                  {NO_REMINDERS}
                </AppText>
                <AppText variant="caption" tone="secondary">
                  {NO_REMINDERS_HINT}
                </AppText>
              </Card>
            ) : (
              <Card>
                {data.reminders.map((reminder) => (
                  <ReminderRow
                    key={reminder.id}
                    reminder={reminder}
                    onOpen={() =>
                      router.push({
                        pathname: '/daily/reminder-form',
                        params: { id: reminder.id },
                      })
                    }
                  />
                ))}
              </Card>
            )}

            <Button
              label={ADD_REMINDER}
              onPress={() => router.push('/daily/reminder-form')}
              accessibilityHint="Opens the new reminder form"
            />
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
