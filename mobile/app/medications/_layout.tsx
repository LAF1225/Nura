/**
 * The medication stack (PRD 5, sections 6, 7 and 67).
 *
 * Reached from Care, which is where medication *management* lives, and from
 * the Today card. Health keeps the medication record itself -- what the
 * medication is -- and links here for reminders, which is the Health/Care
 * boundary PRD 5 section 30 asks to be kept consistently.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function MedicationsLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Medications' }} />
      <Stack.Screen name="schedules" options={{ title: 'Reminder schedules' }} />
      <Stack.Screen name="schedule/[id]" options={{ title: '' }} />
      <Stack.Screen name="history" options={{ title: 'Medication history' }} />
      <Stack.Screen name="supply/index" options={{ title: 'Supply and refills' }} />
      <Stack.Screen name="supply/[medicationId]" options={{ title: '' }} />
      {/* A sheet, because a skip reason is optional and dismissing without
          answering has to be as easy as answering (PRD 5, section 19). */}
      <Stack.Screen
        name="skip"
        options={{ title: 'Skip this dose', presentation: 'modal' }}
      />
    </Stack>
  );
}
