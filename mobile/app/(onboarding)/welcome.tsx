/**
 * Welcome screen (PRD 1, section 7).
 *
 * The copy is deliberately modest. Nura does not claim to prevent
 * emergencies, detect seizures, keep anyone safe, or monitor health
 * automatically -- none of that is true, and PRD 1 forbids implying it.
 */
import { useRouter } from 'expo-router';
import { Image, View } from 'react-native';

import { AppText, Button, Screen } from '../../src/components';
import { useTheme } from '../../src/theme';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function WelcomeScreen() {
  const router = useRouter();
  const theme = useTheme();

  return (
    <Screen contentStyle={{ flexGrow: 1, justifyContent: 'center' }}>
      <View style={{ alignItems: 'center', gap: spacing.sm, marginBottom: spacing.xxxl }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 96, height: 96 }}
          resizeMode="contain"
        />
        <AppText variant="title" style={{ textAlign: 'center' }}>
          Welcome to Nura
        </AppText>
        <AppText variant="body" tone="secondary" style={{ textAlign: 'center' }}>
          Your health and daily-life companion.
        </AppText>
      </View>

      <View style={{ gap: spacing.md }}>
        <Button
          label="Get started"
          onPress={() => router.push('/sign-in')}
          accessibilityHint="Opens sign-in options to create your account"
        />

        <View style={{ alignItems: 'center', gap: spacing.xxs }}>
          <AppText variant="caption" tone="secondary">
            Already have an account?
          </AppText>
          <Button
            label="Sign in"
            variant="ghost"
            onPress={() => router.push('/sign-in')}
            style={{ alignSelf: 'center' }}
          />
        </View>
      </View>

      {/* Keeps the layout balanced on tall screens without a decorative block. */}
      <View style={{ height: spacing.xxl, backgroundColor: theme.colors.background }} />
    </Screen>
  );
}
