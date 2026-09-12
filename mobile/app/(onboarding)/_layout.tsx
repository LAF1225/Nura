/**
 * Onboarding stack (PRD 1, section 43).
 *
 * Deliberately separate from the five-tab navigator: the main tabs are not
 * shown at all until onboarding is finished. Headers are bare except for a
 * back arrow, which is what lets someone revisit an earlier answer
 * (PRD 1, section 44).
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function OnboardingLayout() {
  const theme = useTheme();

  return (
    <Stack
      screenOptions={{
        headerShown: true,
        headerTitle: '',
        headerShadowVisible: false,
        headerStyle: { backgroundColor: theme.colors.background },
        headerTintColor: theme.colors.textPrimary,
        contentStyle: { backgroundColor: theme.colors.background },
      }}
    >
      {/* Nothing to go back to from the first screen. */}
      <Stack.Screen name="welcome" options={{ headerShown: false }} />
    </Stack>
  );
}
