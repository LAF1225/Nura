/**
 * The symptom stack (PRD 6, sections 6, 7 and 70).
 *
 * Reached from Health, which is where the symptom *record* belongs, and from the
 * Today card. It is its own stack rather than a section of `/health/[section]`
 * because a symptom is not a record you fill in once: it has a history, a
 * conversation, a review step and photos, and none of that fits the one-screen
 * record form the health sections share.
 *
 *     Health = what you have been told you have, and what you are experiencing
 *     Symptoms = the experiencing part, over time
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function SymptomsLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Symptoms' }} />
      <Stack.Screen name="log" options={{ title: 'Log a symptom' }} />
      <Stack.Screen name="talk" options={{ title: 'Talk to Nura' }} />
      <Stack.Screen name="review" options={{ title: 'Review' }} />
      <Stack.Screen name="history" options={{ title: 'Symptom history' }} />
      <Stack.Screen name="[id]/index" options={{ title: '' }} />
      <Stack.Screen name="[id]/update" options={{ title: 'Add an update' }} />
    </Stack>
  );
}
