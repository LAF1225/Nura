/**
 * A placeholder block for content that is still loading (PRD 3, section 29).
 *
 * Deliberately still. A shimmering skeleton is decoration that runs
 * continuously, which is the one thing PRD 3 section 43 asks us to avoid, and
 * it would need a reduced-motion path to be safe anyway. A calm grey block
 * says "something is coming here" just as clearly.
 *
 * The whole group is announced once as "Loading", so a screen reader hears a
 * single useful sentence instead of a row of empty views.
 */
import { View, type DimensionValue } from 'react-native';

import { useTheme } from '../theme';
import { radius, spacing } from '../theme/tokens';

interface SkeletonProps {
  height?: number;
  width?: DimensionValue;
}

export function Skeleton({ height = 16, width = '100%' }: SkeletonProps) {
  const theme = useTheme();
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no"
      style={{
        height,
        width,
        borderRadius: radius.sm,
        backgroundColor: theme.colors.surfaceSecondary,
      }}
    />
  );
}

/** A card-sized group of placeholder lines. */
export function SkeletonCard({
  lines = 3,
  label = 'Loading',
}: {
  lines?: number;
  label?: string;
}) {
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      style={{ gap: spacing.sm }}
    >
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton
          key={index}
          height={index === 0 ? 20 : 14}
          // A slightly short last line reads as text rather than as a block.
          width={index === lines - 1 ? '60%' : '100%'}
        />
      ))}
    </View>
  );
}
