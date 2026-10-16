/**
 * The Today card (PRD 12, sections 18 and 19).
 *
 * Three decisions.
 *
 * **It draws nothing at all for somebody who has never made a task, a
 * reminder or a routine.** `hasAnything` is false for them, and the card
 * returns null -- the same choice the symptoms card makes, and the reason
 * Today opens calm rather than full (PRD 3, section 3).
 *
 * **It is counts and one sentence.** The rows themselves arrive through
 * Today's `important` list, in the order section 18 fixes, and are drawn by
 * the Important Today section -- not here. A card that listed them again
 * would be a second place that could put a task above a dose.
 *
 * **Quick add is three buttons, not a menu.** Section 19 asks for "+ Task",
 * "+ Reminder" and "+ Routine", and three buttons are reachable with a screen
 * reader in a way a sheet behind a plus icon is not.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card } from '../../../components';
import { spacing } from '../../../theme/tokens';
import { ADD_REMINDER, ADD_ROUTINE, ADD_TASK, DAILY_LIFE_TITLE } from '../copy';
import type { DailyLifeSummary } from '../types';

interface DailyLifeTodayCardProps {
  /** Null for an account with no profile yet. */
  dailyLife: DailyLifeSummary | null;
}

export function DailyLifeTodayCard({ dailyLife }: DailyLifeTodayCardProps) {
  const router = useRouter();

  // Nothing to say, so nothing drawn. Not an empty card with a heading.
  if (dailyLife === null || !dailyLife.hasAnything) return null;

  const { tasks, routines, reminders } = dailyLife;

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">{DAILY_LIFE_TITLE}</AppText>
        <AppText variant="body" tone="secondary">
          {dailyLife.summaryLabel}
        </AppText>
        {tasks.overdue > 0 ? (
          // Stated, not warned about. Section 18 keeps daily life well below
          // anything safety-critical, and an overdue task is a fact about a
          // clock.
          <AppText variant="body" tone="secondary">
            {tasks.overdue === 1
              ? '1 task is past its due time.'
              : `${tasks.overdue} tasks are past their due time.`}
          </AppText>
        ) : null}
        {routines.inProgress > 0 ? (
          <AppText variant="body" tone="secondary">
            {routines.inProgress === 1
              ? '1 routine is under way.'
              : `${routines.inProgress} routines are under way.`}
          </AppText>
        ) : null}
        {reminders.dueNow > 0 ? (
          <AppText variant="body" tone="secondary">
            {reminders.dueNow === 1
              ? '1 reminder is waiting for an answer.'
              : `${reminders.dueNow} reminders are waiting for an answer.`}
          </AppText>
        ) : null}
      </View>

      <Button
        label="Open"
        onPress={() => router.push('/daily')}
        accessibilityHint="Opens your tasks, reminders, alarms and routines"
      />

      <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
        <Button
          label={ADD_TASK}
          variant="secondary"
          onPress={() => router.push('/daily/task-form')}
          accessibilityHint="Opens the new task form"
        />
        <Button
          label={ADD_REMINDER}
          variant="secondary"
          onPress={() => router.push('/daily/reminder-form')}
          accessibilityHint="Opens the new reminder form"
        />
        <Button
          label={ADD_ROUTINE}
          variant="secondary"
          onPress={() => router.push('/daily/routine-form')}
          accessibilityHint="Opens the new routine form"
        />
      </View>
    </Card>
  );
}
