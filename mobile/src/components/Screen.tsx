/**
 * Standard screen wrapper: themed background, safe areas and scrollable
 * content (PRD 0, section 25).
 *
 * Content scrolls by default so screens survive small phones and large system
 * font sizes. The bottom edge is left to the tab bar, which already insets
 * itself, so only the top and sides are padded here.
 */
import { ScrollView, View, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { ReactNode } from 'react';

import { useTheme } from '../theme';
import { spacing } from '../theme/tokens';

interface ScreenProps {
  children: ReactNode;
  /** Set false for screens that manage their own scrolling. */
  scrollable?: boolean;
  /** Set false to run content to the screen edges. */
  padded?: boolean;
  contentStyle?: ViewStyle;
}

export function Screen({
  children,
  scrollable = true,
  padded = true,
  contentStyle,
}: ScreenProps) {
  const theme = useTheme();

  const padding: ViewStyle = padded
    ? {
        paddingHorizontal: spacing.md,
        paddingTop: spacing.md,
        paddingBottom: spacing.xxl,
      }
    : {};

  return (
    <SafeAreaView
      edges={['top', 'left', 'right']}
      style={{ flex: 1, backgroundColor: theme.colors.background }}
    >
      {scrollable ? (
        <ScrollView
          contentContainerStyle={[padding, contentStyle]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[{ flex: 1 }, padding, contentStyle]}>{children}</View>
      )}
    </SafeAreaView>
  );
}
