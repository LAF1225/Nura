/**
 * Family messages (PRD 9, sections 30-37, 65 and 68).
 *
 * The same stack for both sides: the primary user reaches it from Care and sees a
 * thread per caregiver, a caregiver reaches it from Caregiver Mode and sees one.
 * The server decides which, so there is no branch here that could get it wrong.
 *
 * No AI anywhere in this stack. Section 65 forbids summarising or analysing
 * private family messages, and no assistant hook is imported by any screen in it.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function FamilyLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Messages' }} />
      <Stack.Screen name="[threadId]" options={{ title: '' }} />
    </Stack>
  );
}
