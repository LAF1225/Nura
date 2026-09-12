/**
 * Compact status pill, e.g. the development-only backend indicator on Today.
 *
 * Carries an icon as well as a colour, so the meaning does not depend on
 * colour vision (PRD 0, section 24).
 */
import { Ionicons } from '@expo/vector-icons';
import { View } from 'react-native';

import { useTheme } from '../theme';
import { iconSize, radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

interface StatusChipProps {
  label: string;
  tone?: StatusTone;
  /** Overrides the icon chosen for the tone. */
  icon?: keyof typeof Ionicons.glyphMap;
}

const DEFAULT_ICONS: Record<StatusTone, keyof typeof Ionicons.glyphMap> = {
  success: 'checkmark-circle',
  warning: 'alert-circle',
  danger: 'close-circle',
  info: 'information-circle',
  neutral: 'ellipse-outline',
};

export function StatusChip({ label, tone = 'neutral', icon }: StatusChipProps) {
  const theme = useTheme();

  const colours: Record<StatusTone, string> = {
    success: theme.colors.success,
    warning: theme.colors.warning,
    danger: theme.colors.danger,
    info: theme.colors.info,
    neutral: theme.colors.textSecondary,
  };
  const colour = colours[tone];

  return (
    <View
      // One label for the whole chip, so a screen reader reads it as a unit
      // rather than announcing a decorative icon separately.
      accessible
      accessibilityRole="text"
      accessibilityLabel={label}
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        alignSelf: 'flex-start',
        gap: spacing.xs,
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.sm,
        borderRadius: radius.pill,
        backgroundColor: theme.colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: theme.colors.border,
      }}
    >
      <Ionicons name={icon ?? DEFAULT_ICONS[tone]} size={iconSize.sm} color={colour} />
      <AppText variant="caption" style={{ color: colour }}>
        {label}
      </AppText>
    </View>
  );
}
