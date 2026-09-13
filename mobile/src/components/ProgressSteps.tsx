/**
 * An ordered list of setup stages with real text beside every indicator
 * (PRD 2, sections 52 and 57). No percentages: none exist to show.
 *
 * Done, current and pending are told apart by icon shape as well as colour,
 * and the current stage is announced to screen readers as it changes.
 */
import { Ionicons } from '@expo/vector-icons';
import { ActivityIndicator, View } from 'react-native';

import { useTheme } from '../theme';
import { iconSize, spacing } from '../theme/tokens';
import { AppText } from './AppText';

export interface ProgressStepItem {
  key: string;
  label: string;
}

interface ProgressStepsProps {
  steps: ProgressStepItem[];
  currentKey: string;
}

export function ProgressSteps({ steps, currentKey }: ProgressStepsProps) {
  const theme = useTheme();
  const currentIndex = Math.max(
    0,
    steps.findIndex((step) => step.key === currentKey)
  );

  return (
    <View style={{ gap: spacing.md }} accessibilityRole="list">
      {steps.map((step, index) => {
        const done = index < currentIndex;
        const current = index === currentIndex;
        const status = done ? 'done' : current ? 'in progress' : 'not started';

        return (
          <View
            key={step.key}
            accessible
            accessibilityLabel={`${step.label}, ${status}`}
            accessibilityLiveRegion={current ? 'polite' : 'none'}
            style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}
          >
            <View style={{ width: iconSize.md, alignItems: 'center' }}>
              {done ? (
                <Ionicons
                  name="checkmark-circle"
                  size={iconSize.md}
                  color={theme.colors.success}
                />
              ) : current ? (
                <ActivityIndicator color={theme.colors.accent} />
              ) : (
                <Ionicons
                  name="ellipse-outline"
                  size={iconSize.md}
                  color={theme.colors.textSecondary}
                />
              )}
            </View>
            <AppText
              variant={current ? 'bodyStrong' : 'body'}
              tone={current || done ? 'primary' : 'secondary'}
            >
              {step.label}
            </AppText>
          </View>
        );
      })}
    </View>
  );
}
