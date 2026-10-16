/**
 * The daily-life stack (PRD 12, sections 19, 20, 59 and 60).
 *
 * Reached three ways, each from where somebody would already be looking: the
 * Today card, the Care tab's Routines card, and a More row. All three land on
 * the overview, which is the one screen that can say what today looks like.
 *
 * **A caregiver reaches none of this.** Section 42 keeps tasks, alarms and
 * personal reminders private to the primary user, and the backend enforces
 * it: every endpoint these screens read resolves the profile through the
 * signed-in account's own join row, so a caregiver is answered 404 rather
 * than hidden from. A caregiver with the `routines` permission sees routines
 * through Caregiver Mode, which is its own narrower screen.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';
import {
  ALARMS_TITLE,
  DAILY_LIFE_TITLE,
  NEW_ALARM_TITLE,
  NEW_REMINDER_TITLE,
  NEW_ROUTINE_TITLE,
  NEW_TASK_TITLE,
  REMINDERS_TITLE,
  ROUTINES_TITLE,
  TASKS_TITLE,
} from '../../src/features/productivity/copy';

export default function DailyLifeLayout() {
  const theme = useTheme();

  return (
    <Stack
      screenOptions={{
        contentStyle: { backgroundColor: theme.colors.background },
        headerStyle: { backgroundColor: theme.colors.background },
        headerTintColor: theme.colors.textPrimary,
        headerTitleStyle: { color: theme.colors.textPrimary },
        headerShadowVisible: false,
      }}
    >
      <Stack.Screen name="index" options={{ title: DAILY_LIFE_TITLE }} />
      <Stack.Screen name="tasks" options={{ title: TASKS_TITLE }} />
      <Stack.Screen name="task-form" options={{ title: NEW_TASK_TITLE }} />
      <Stack.Screen name="reminders" options={{ title: REMINDERS_TITLE }} />
      <Stack.Screen name="reminder-form" options={{ title: NEW_REMINDER_TITLE }} />
      <Stack.Screen name="alarms" options={{ title: ALARMS_TITLE }} />
      <Stack.Screen name="alarm-form" options={{ title: NEW_ALARM_TITLE }} />
      <Stack.Screen name="routines" options={{ title: ROUTINES_TITLE }} />
      <Stack.Screen name="routine-form" options={{ title: NEW_ROUTINE_TITLE }} />
      <Stack.Screen name="routine/[id]" options={{ title: ROUTINES_TITLE }} />
      <Stack.Screen name="run/[id]" options={{ title: ROUTINES_TITLE }} />
      <Stack.Screen name="capabilities" options={{ title: 'What Nura can reach' }} />
    </Stack>
  );
}
