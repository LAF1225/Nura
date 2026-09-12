/**
 * A rounded surface for grouping content (PRD 0, section 11: generous white
 * space and rounded cards).
 *
 * In Light mode the card sits slightly above the background with a soft
 * shadow. In Dark mode it relies on surface colour and a border instead --
 * shadows read as muddy smudges on dark backgrounds.
 */
import { View, type ViewProps } from 'react-native';

import { useTheme } from '../theme';
import { elevation, radius, spacing } from '../theme/tokens';

interface CardProps extends ViewProps {
  /** Set false for a flush card with no inner padding. */
  padded?: boolean;
}

export function Card({ padded = true, style, ...rest }: CardProps) {
  const theme = useTheme();

  return (
    <View
      style={[
        {
          backgroundColor: theme.colors.surface,
          borderRadius: radius.lg,
          borderWidth: 1,
          borderColor: theme.colors.border,
          padding: padded ? spacing.md : 0,
        },
        theme.isDark ? elevation.none : elevation.card,
        style,
      ]}
      {...rest}
    />
  );
}
