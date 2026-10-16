/**
 * The two banners that say what mode Nura is in (PRD 8, sections 37 and 68).
 *
 * Both exist because the PRD asks for the state to be *visible*. Section 68
 * says Privacy Mode must be clearly indicated; section 37 describes serious
 * mode as a behaviour change, and a behaviour change nobody can see reads as
 * an assistant that has become inexplicably terse.
 *
 * Neither is an alert. They are quiet, they carry no icon that implies
 * urgency, and the serious one explains itself in a sentence rather than
 * announcing a state the user did not ask for.
 */
import { View } from 'react-native';

import { AppText } from '../../../components';
import { useTheme } from '../../../theme';
import { radius, spacing } from '../../../theme/tokens';
import { PRIVACY_BANNER, SERIOUS_BANNER } from '../copy';

interface BannerProps {
  text: string;
  accent: string;
  background: string;
}

function Banner({ text, accent, background }: BannerProps) {
  return (
    <View
      accessible
      accessibilityRole="alert"
      accessibilityLabel={text}
      style={{
        backgroundColor: background,
        borderLeftWidth: 3,
        borderLeftColor: accent,
        borderRadius: radius.md,
        paddingHorizontal: spacing.sm,
        paddingVertical: spacing.xs,
      }}
    >
      <AppText variant="caption" tone="secondary">
        {text}
      </AppText>
    </View>
  );
}

/** Shown above a reply that was answered in serious mode (section 37). */
export function SeriousModeBanner() {
  const theme = useTheme();
  return (
    <Banner
      text={SERIOUS_BANNER}
      accent={theme.colors.accentStrong}
      background={theme.colors.surfaceSecondary}
    />
  );
}

/** Shown whenever Privacy mode is on (section 68). */
export function PrivacyModeBanner() {
  const theme = useTheme();
  return (
    <Banner
      text={PRIVACY_BANNER}
      accent={theme.colors.accentStrong}
      background={theme.colors.surfaceSecondary}
    />
  );
}
