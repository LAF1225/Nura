/**
 * Nura -- a small static introduction (PRD 0, section 8).
 *
 * Deliberately no chat, no voice and no language model. This screen only
 * explains what the companion will become, and avoids any suggestion that Nura
 * interprets symptoms or offers medical advice (PRD 0, section 35).
 */
import { Image, View } from 'react-native';

import { AppText, Card, Screen } from '../../src/components';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function NuraScreen() {
  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: spacing.sm, marginVertical: spacing.xl }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 72, height: 72 }}
          resizeMode="contain"
        />
        <AppText variant="title">Nura</AppText>
      </View>

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          Nura is a calm companion for everyday health and routines, built to sit on your
          desk and help you keep track of the small things.
        </AppText>
        <AppText variant="body" tone="secondary">
          Conversation, voice and memory arrive in later updates. This is where you will
          shape how Nura talks with you.
        </AppText>
      </Card>
    </Screen>
  );
}
