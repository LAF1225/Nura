/**
 * Ready-to-pair handoff (PRD 1, section 46).
 *
 * The end of PRD 1 and the entry to PRD 2's pairing flow. "Set up later"
 * leaves pairing for the Today screen's "Connect your Nura" card
 * (PRD 2, section 42). Nothing here implies a robot is connected
 * (PRD 1, section 47).
 */
import { useRouter } from 'expo-router';
import { Image, View } from 'react-native';

import { AppText, Button, Card, Screen, StepIndicator } from '../../src/components';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function ReadyScreen() {
  const router = useRouter();

  return (
    <Screen>
      <StepIndicator step={5} totalSteps={5} />

      <View style={{ alignItems: 'center', gap: spacing.sm, marginVertical: spacing.xl }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 80, height: 80 }}
          resizeMode="contain"
        />
        <AppText variant="title" style={{ textAlign: 'center' }}>
          You are ready to connect Nura
        </AppText>
      </View>

      <Card>
        <AppText variant="body" tone="secondary">
          Your basic setup is complete. Next, we will connect your phone to your Nura
          device.
        </AppText>
      </Card>

      <View style={{ gap: spacing.sm, marginTop: spacing.xl }}>
        <Button
          label="Connect Nura"
          onPress={() => router.push('/connect-device')}
          accessibilityHint="Starts connecting your Nura device"
        />
        <Button
          label="Set up later"
          variant="secondary"
          onPress={() => router.replace('/')}
          accessibilityHint="Skips device setup and opens the app"
        />
      </View>
    </Screen>
  );
}
