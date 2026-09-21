/**
 * "You're offline" (PRD 3, sections 26 and 30).
 *
 * States a fact and stops. The app still works offline -- cached information
 * is shown, and a check-in is saved on the phone -- so this is not a warning,
 * an error, or a reason to block anything.
 */
import { Ionicons } from '@expo/vector-icons';
import { View } from 'react-native';

import { useTheme } from '../../theme';
import { iconSize, radius, spacing } from '../../theme/tokens';
import { AppText } from '../AppText';

export function OfflineBanner() {
  const theme = useTheme();

  return (
    <View
      accessible
      // Announced when it appears, without pulling focus away from whatever
      // the user was doing.
      accessibilityLiveRegion="polite"
      accessibilityRole="alert"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        padding: spacing.sm,
        marginBottom: spacing.md,
        borderRadius: radius.md,
        backgroundColor: theme.colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: theme.colors.border,
      }}
    >
      <Ionicons
        name="cloud-offline-outline"
        size={iconSize.md}
        color={theme.colors.textSecondary}
      />
      <AppText variant="caption" tone="secondary" style={{ flex: 1 }}>
        You’re offline. Some information may be out of date.
      </AppText>
    </View>
  );
}
