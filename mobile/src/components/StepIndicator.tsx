/**
 * Onboarding progress (PRD 1, section 29).
 *
 * Subtle but visible: a short label plus a slim bar. Screen readers get the
 * label, and the bar is marked decorative so progress is not announced twice.
 */
import { View } from 'react-native';

import { useTheme } from '../theme';
import { radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

interface StepIndicatorProps {
  step: number;
  totalSteps: number;
}

export function StepIndicator({ step, totalSteps }: StepIndicatorProps) {
  const theme = useTheme();
  const safeTotal = Math.max(totalSteps, 1);
  const fraction = Math.min(Math.max(step / safeTotal, 0), 1);

  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={`Step ${step} of ${safeTotal}`}
      accessibilityValue={{ min: 0, max: safeTotal, now: step }}
      style={{ gap: spacing.xs, marginBottom: spacing.lg }}
    >
      <AppText variant="caption" tone="secondary">
        Step {step} of {safeTotal}
      </AppText>

      <View
        importantForAccessibility="no-hide-descendants"
        style={{
          height: 4,
          borderRadius: radius.pill,
          backgroundColor: theme.colors.surfaceSecondary,
          overflow: 'hidden',
        }}
      >
        <View
          style={{
            width: `${fraction * 100}%`,
            height: '100%',
            borderRadius: radius.pill,
            backgroundColor: theme.colors.accent,
          }}
        />
      </View>
    </View>
  );
}
