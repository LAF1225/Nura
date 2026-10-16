/**
 * "Nura is thinking" (PRD 8, sections 6 and 83).
 *
 * Text rather than animated dots. Section 83 asks for reduced motion and
 * clear loading states, and a sentence satisfies both: it reflows at larger
 * type sizes, a screen reader announces it, and it does not move.
 *
 * `accessibilityLiveRegion` is what makes it announce at all -- the indicator
 * appears without focus moving, so without it a screen reader user gets
 * silence between pressing Send and the reply arriving.
 */
import { View } from 'react-native';

import { AppText } from '../../../components';
import { useTheme } from '../../../theme';
import { radius, spacing } from '../../../theme/tokens';
import { SENDING } from '../copy';

export function AssistantTypingIndicator() {
  const theme = useTheme();

  return (
    <View
      accessibilityLiveRegion="polite"
      accessible
      accessibilityLabel={SENDING}
      style={{
        alignSelf: 'flex-start',
        backgroundColor: theme.colors.surfaceSecondary,
        borderRadius: radius.lg,
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.xs,
      }}
    >
      <AppText variant="body" tone="secondary">
        {`${SENDING}…`}
      </AppText>
    </View>
  );
}
