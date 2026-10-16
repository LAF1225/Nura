/**
 * Emergency contacts (PRD 9, sections 43-47, 89 and 93).
 *
 * The primary user's own stack. No caregiver route reaches it -- section 45 gives
 * the chain to the person themselves, and the backend has no caregiver-scoped
 * endpoint for a contact at any verb, reads included.
 *
 * Nothing in this stack contacts anybody. Section 47 puts escalation in PRD 10,
 * and the screens say so where somebody is typing a phone number, which is the
 * difference between a list they understand and a safety feature they think they
 * have.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function EmergencyContactsLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Emergency contacts' }} />
      <Stack.Screen name="[id]" options={{ title: 'Contact' }} />
    </Stack>
  );
}
