/**
 * The top of Today (PRD 3, sections 8 and 58).
 *
 * A greeting, the person's name if we have one, and a small way into their
 * account. No mascot, no exclamation marks, nothing medical. The brand mark is
 * there but small -- Today is the user's day, not a logo screen.
 */
import { useRouter } from 'expo-router';
import { Image, Pressable, View } from 'react-native';

import { useTheme } from '../../theme';
import { minTouchTarget, radius, spacing } from '../../theme/tokens';
import { greetingFor, initialsFor } from '../../utils/date';
import { AppText } from '../AppText';

const BRAND_MARK = require('../../../assets/branding/nura-mark-transparent.png');

interface GreetingHeaderProps {
  preferredName: string | null;
  /** Rendered as a still placeholder while the name is still loading. */
  isLoading?: boolean;
}

export function GreetingHeader({
  preferredName,
  isLoading = false,
}: GreetingHeaderProps) {
  const theme = useTheme();
  const router = useRouter();
  const initials = initialsFor(preferredName);

  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        marginBottom: spacing.lg,
      }}
    >
      <Image
        source={BRAND_MARK}
        // Decorative: the word "Nura" is not in the greeting, and the mark
        // adds nothing a screen reader needs to hear.
        accessibilityElementsHidden
        importantForAccessibility="no"
        style={{ width: 32, height: 32 }}
        resizeMode="contain"
      />

      <View style={{ flex: 1 }}>
        <AppText variant="title" accessibilityRole="header">
          {isLoading ? 'Hello' : greetingFor(preferredName)}
        </AppText>
      </View>

      {initials ? (
        <Pressable
          onPress={() => router.push('/more')}
          accessibilityRole="button"
          accessibilityLabel="Your account"
          accessibilityHint="Opens account and app settings"
          style={({ pressed }) => ({
            width: minTouchTarget,
            height: minTouchTarget,
            borderRadius: radius.pill,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: theme.colors.surfaceSecondary,
            borderWidth: 1,
            borderColor: theme.colors.border,
            opacity: pressed ? 0.85 : 1,
          })}
        >
          {/* Hidden from the reader: the button already has a clear label, and
              announcing "SA" as well would say nothing useful. */}
          <AppText
            variant="bodyStrong"
            accessibilityElementsHidden
            importantForAccessibility="no"
          >
            {initials}
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}
