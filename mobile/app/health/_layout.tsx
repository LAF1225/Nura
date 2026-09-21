/**
 * The health stack (PRD 4, section 29).
 *
 * Titles are set by each screen, because the section screens only know what
 * they are showing once the route parameter has been read.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function HealthLayout() {
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
      <Stack.Screen name="setup" options={{ title: '' }} />
      <Stack.Screen name="blood-type" options={{ title: 'Blood type' }} />
      <Stack.Screen name="[section]/index" options={{ title: '' }} />
      <Stack.Screen name="[section]/[id]" options={{ title: '' }} />
    </Stack>
  );
}
