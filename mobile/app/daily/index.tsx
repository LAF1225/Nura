/**
 * The daily-life overview (PRD 12, sections 19, 60's ProductivityOverviewScreen).
 *
 * One screen that says what today looks like and leads to the four lists. It
 * is also where anything queued offline is sent: somebody who has been out of
 * signal lands here, which is the same place PRD 5 and PRD 7 put their sync
 * hooks.
 *
 * Nothing here interprets. Four counts and a sentence, and no streak, score or
 * encouragement -- the discipline PRD 3 set for the check-in and PRD 5 for
 * adherence applies just as much to a task list.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, ListRow, Screen } from '../../src/components';
import {
  ALARMS_TITLE,
  DAILY_LIFE_SUBTITLE,
  EXTERNAL_TITLE,
  REMINDERS_TITLE,
  ROUTINES_TITLE,
  TASKS_TITLE,
  alarmCountSentence,
  reminderCountSentence,
  routineCountSentence,
  taskCountSentence,
} from '../../src/features/productivity/copy';
import {
  useDailyLifeSummary,
  useSyncPendingDailyLife,
} from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

export default function DailyLifeOverviewScreen() {
  const router = useRouter();
  const summary = useDailyLifeSummary();

  // Somebody lands here after being offline, so this is where whatever was
  // written on the phone gets sent (sections 37, 38 and 39).
  useSyncPendingDailyLife();

  const data = summary.data;

  return (
    <Screen
      onRefresh={() => void summary.refetch()}
      refreshing={summary.isRefetching && !summary.isLoading}
    >
      <AppText variant="body" tone="secondary">
        {DAILY_LIFE_SUBTITLE}
      </AppText>

      <View style={{ height: spacing.lg }} />

      <AsyncState
        status={summary.isError ? 'error' : data ? 'success' : 'loading'}
        error={summary.error}
        onRetry={() => void summary.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.xxs }}>
              <AppText variant="heading">Today</AppText>
              <AppText variant="body" tone="secondary">
                {data.summaryLabel}
              </AppText>
            </Card>

            <Card>
              <ListRow
                label={TASKS_TITLE}
                description={taskCountSentence(data.tasks.openTotal, data.tasks.overdue)}
                leadingIcon="checkmark-circle-outline"
                showChevron
                onPress={() => router.push('/daily/tasks')}
                accessibilityHint="Opens your task list"
              />
              <ListRow
                label={REMINDERS_TITLE}
                description={reminderCountSentence(data.reminders.dueToday)}
                leadingIcon="notifications-outline"
                showChevron
                onPress={() => router.push('/daily/reminders')}
                accessibilityHint="Opens your reminders"
              />
              <ListRow
                label={ALARMS_TITLE}
                description={alarmCountSentence(data.alarmCount)}
                leadingIcon="alarm-outline"
                showChevron
                onPress={() => router.push('/daily/alarms')}
                accessibilityHint="Opens your alarms"
              />
              <ListRow
                label={ROUTINES_TITLE}
                description={routineCountSentence(data.routines.dueToday)}
                leadingIcon="repeat-outline"
                showChevron
                onPress={() => router.push('/daily/routines')}
                accessibilityHint="Opens your routines"
              />
            </Card>

            <Card style={{ gap: spacing.sm }}>
              <AppText variant="heading">{EXTERNAL_TITLE}</AppText>
              <AppText variant="body" tone="secondary">
                What Nura can and cannot look up in this build.
              </AppText>
              <Button
                label="See what Nura can reach"
                variant="secondary"
                onPress={() => router.push('/daily/capabilities')}
                accessibilityHint="Opens the list of what Nura can reach"
              />
            </Card>
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
