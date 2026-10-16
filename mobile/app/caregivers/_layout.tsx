/**
 * The caregiver stack, for the primary user (PRD 9, sections 11, 52, 53, 83).
 *
 * Reached from Care. Everything in here is about *the person's own* caregivers:
 * who they are, what each can see, the invitations outstanding, and the care
 * requests waiting for a decision. A caregiver reaches none of it -- these
 * screens read endpoints that authorize through the owner's own profile link.
 *
 * Caregiver Mode is a separate stack (`app/care-mode`), deliberately: section 59
 * allows a simplified navigation there, and mixing "manage my caregivers" with
 * "look at the person I support" in one stack is how somebody ends up on the
 * wrong screen for the wrong person.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function CaregiversLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Caregivers' }} />
      <Stack.Screen name="invite" options={{ title: 'Invite someone' }} />
      <Stack.Screen name="[id]" options={{ title: '' }} />
      <Stack.Screen name="accept" options={{ title: 'Invitation' }} />
      <Stack.Screen name="notifications" options={{ title: 'Care notifications' }} />
      <Stack.Screen name="requests/index" options={{ title: 'Care requests' }} />
      <Stack.Screen name="requests/[id]" options={{ title: 'Care request' }} />
    </Stack>
  );
}
