/**
 * The safety stack, for the primary user (PRD 10, sections 4, 12, 99).
 *
 * Reached from Care. Everything in here is about *this person's own* safety:
 * whether they are being watched over, what happens if they do not answer,
 * what Nura actually did, and what this build cannot do at all.
 *
 * A caregiver reaches none of it. Every screen here reads an owner-scoped
 * endpoint, and a caregiver's whole view of safety is the alert list in
 * Caregiver Mode -- which is section 50, enforced by the backend rather than
 * by which stack a screen happens to be in.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function SafetyLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Safety' }} />
      <Stack.Screen name="start" options={{ title: 'Start monitoring' }} />
      <Stack.Screen name="check" options={{ title: 'Are you okay?' }} />
      <Stack.Screen name="emergency" options={{ title: 'Emergency request' }} />
      <Stack.Screen name="history" options={{ title: 'Safety history' }} />
      <Stack.Screen name="capabilities" options={{ title: 'What Nura can do' }} />
      <Stack.Screen name="[eventId]" options={{ title: 'Safety event' }} />
    </Stack>
  );
}
