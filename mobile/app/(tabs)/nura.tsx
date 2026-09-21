/**
 * Nura -- a small static introduction, plus the robot's status (PRD 0
 * section 8; PRD 3 section 36).
 *
 * Still no chat, no voice and no language model. The one thing added in PRD 3
 * is the connection status, because "is my Nura there?" is the question this
 * tab is most likely to be opened for. It reuses the same card as Today, so
 * the two can never describe the robot differently.
 */
import { Image, View } from 'react-native';

import { AppText, Card, Screen } from '../../src/components';
import { NuraStatusCard } from '../../src/components/today';
import { useToday } from '../../src/hooks/useToday';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function NuraScreen() {
  const today = useToday();

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

      <View style={{ gap: spacing.md }}>
        {/* Nothing is shown until the status is known: a "not connected"
            prompt that turns out to be wrong is worse than a moment's wait. */}
        {today.data ? <NuraStatusCard device={today.data.device} /> : null}

        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            Nura is a calm companion for everyday health and routines, built to sit on
            your desk and help you keep track of the small things.
          </AppText>
          <AppText variant="body" tone="secondary">
            Conversation, voice and memory arrive in later updates. This is where you will
            shape how Nura talks with you.
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
