/**
 * The Privacy & Security stack (PRD 13, sections 4 and 45).
 *
 * Three screens, which is all section 45 allows: the hub, the export screen
 * and the delete screen. Everything else the hub shows is a link to a screen
 * that already exists -- caregiver permissions, memory, conversation history,
 * Nura Device settings, Safety Monitoring -- because section 4 says not to
 * duplicate those settings and section 109's efficiency rule says not to
 * rebuild working systems.
 *
 * **A caregiver reaches none of it.** Every endpoint behind these screens
 * resolves the profile through the signed-in account's own join row, so a
 * caregiver is answered 404. An export is a complete copy of somebody's
 * record and a delete is irreversible; neither is something a permission
 * could sensibly grant.
 */
import { Stack } from 'expo-router';

import { DELETE_TITLE, EXPORT_TITLE, HUB_TITLE } from '../../src/features/privacy/copy';
import { useTheme } from '../../src/theme';

export default function PrivacyLayout() {
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
      <Stack.Screen name="index" options={{ title: HUB_TITLE }} />
      <Stack.Screen name="export" options={{ title: EXPORT_TITLE }} />
      <Stack.Screen name="delete" options={{ title: DELETE_TITLE }} />
    </Stack>
  );
}
