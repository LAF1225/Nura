/**
 * The Nura stack (PRD 8, sections 5, 6 and 85).
 *
 * Reached from the Nura tab. Its own stack rather than a section of the tab
 * because a conversation, its history and five settings screens are places
 * you go and come back from -- and a tab cannot hold a back stack.
 *
 * Nothing here rebuilds notifications. PRD 8's proactivity is in-app only
 * (section 34): the prompts are drawn on the Nura tab, and the reminders that
 * *do* reach the phone belong to PRD 5 and PRD 7 and are untouched by any of
 * this (section 67).
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function NuraLayout() {
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
      <Stack.Screen name="[id]" options={{ title: '' }} />
      <Stack.Screen name="history" options={{ title: 'Conversations' }} />
      <Stack.Screen name="personality" options={{ title: 'Personality' }} />
      <Stack.Screen name="voice" options={{ title: 'Voice and language' }} />
      <Stack.Screen name="memory" options={{ title: 'What Nura remembers' }} />
      <Stack.Screen name="proactivity" options={{ title: 'Speaking first' }} />
      <Stack.Screen name="instructions" options={{ title: 'Custom instructions' }} />
    </Stack>
  );
}
