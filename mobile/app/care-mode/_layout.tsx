/**
 * Caregiver Mode (PRD 9, sections 3, 16, 56, 57, 58 and 59).
 *
 * The same app, not a second one (section 3): this is a stack inside Nura, and an
 * account that both uses Nura for itself and helps somebody else has both.
 *
 * Simplified on purpose (section 59). There is no assistant, no health record and
 * no Today here -- a caregiver sees what they were granted and nothing else, so a
 * screen offering sections they cannot open would be noise.
 *
 * Switching person is `useSwitchCareContext`, which clears the previous person's
 * cached data before changing context. Section 58 forbids briefly showing the
 * prior profile's data, and that is the one place it is enforced.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function CareModeLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Caregiver Mode' }} />
      <Stack.Screen name="profiles" options={{ title: 'People you support' }} />
      <Stack.Screen name="suggest" options={{ title: 'Suggest a change' }} />
      <Stack.Screen name="notifications" options={{ title: 'Notifications' }} />
      <Stack.Screen name="safety-alerts" options={{ title: 'Safety alerts' }} />
    </Stack>
  );
}
