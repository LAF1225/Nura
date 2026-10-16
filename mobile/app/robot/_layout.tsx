/**
 * The Nura Device stack (PRD 11, sections 46 and 70).
 *
 * Reached from More, as section 46 asks. Everything in here is about the
 * *account's own robot*: what it can do, how it should look and behave, what
 * it has been asked to show, and what one of those cards looks like.
 *
 * A caregiver reaches none of it. Section 70 is explicit that caregiver
 * status grants no robot control -- not brightness, not volume, not privacy
 * mode, not the face, not pairing -- and the backend enforces it: every
 * endpoint these screens read resolves the device through the signed-in
 * account's own claim, so a caregiver is answered 404 rather than hidden from.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function RobotLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Nura Device' }} />
      <Stack.Screen name="capabilities" options={{ title: 'What this Nura can do' }} />
      <Stack.Screen name="history" options={{ title: 'Nura’s screen' }} />
      <Stack.Screen name="preview" options={{ title: 'Preview' }} />
    </Stack>
  );
}
