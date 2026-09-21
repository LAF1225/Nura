/**
 * How much of the health profile has been filled in (PRD 4, section 7).
 *
 * Informational, and worded that way. There is no red state, no "incomplete"
 * warning and no nudge about what is missing: a profile someone has chosen not
 * to finish is a valid profile, and a progress bar that scolds is worse than
 * no progress bar (PRD 4, sections 7 and 19).
 *
 * Note it cannot reach 100% for someone with genuinely nothing to add in a
 * section -- there is no "I have no allergies" flag. The wording avoids
 * implying it should, saying how many sections have information rather than
 * how many are "done".
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { radius, spacing } from '../../../theme/tokens';

interface CompletenessProps {
  percent: number;
  completedSections: number;
  totalSections: number;
  /** Hides the sentence under the bar, e.g. on the compact Today card. */
  compact?: boolean;
}

export function Completeness({
  percent,
  completedSections,
  totalSections,
  compact = false,
}: CompletenessProps) {
  const theme = useTheme();
  const clamped = Math.max(0, Math.min(100, percent));

  return (
    <View style={{ gap: spacing.xs }}>
      <View
        // One label for the whole control: a screen reader should hear the
        // figure, not a decorative bar (PRD 4, section 44).
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel={`Health profile ${clamped}% filled in`}
        accessibilityValue={{ min: 0, max: 100, now: clamped }}
        style={{
          height: 8,
          borderRadius: radius.pill,
          backgroundColor: theme.colors.surfaceSecondary,
          overflow: 'hidden',
        }}
      >
        <View
          style={{
            width: `${clamped}%`,
            height: '100%',
            borderRadius: radius.pill,
            backgroundColor: theme.colors.accent,
          }}
        />
      </View>

      {compact ? null : (
        <AppText variant="caption" tone="secondary">
          {completedSections} of {totalSections} sections have information.
        </AppText>
      )}
    </View>
  );
}
