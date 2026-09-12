/**
 * Today -- the app shell prototype (PRD 0, section 26).
 *
 * This is intentionally a shell, not the final Today design. The real
 * dashboard (check-ins, medications, appointments, symptom follow-ups) arrives
 * in later PRDs.
 */
import { Image, View } from 'react-native';

import { AppText, Card, Screen, StatusChip } from '../../src/components';
import { config } from '../../src/constants/config';
import { useBackendHealth } from '../../src/hooks/useBackendHealth';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

function greetingForHour(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

/**
 * Development-only indicator that the app can reach the backend (PRD 0,
 * section 39). Hidden in release builds, and a backend that is down shows a
 * calm "unavailable" chip rather than an error.
 */
function BackendIndicator() {
  const { isSuccess, isError, isLoading, data } = useBackendHealth();

  if (isLoading) {
    return <StatusChip label="Checking Nura services" tone="neutral" />;
  }
  if (isError) {
    return <StatusChip label="Nura services unavailable" tone="warning" />;
  }
  if (isSuccess && data.status === 'ok') {
    return <StatusChip label="Nura services connected" tone="success" />;
  }
  return <StatusChip label="Nura services responded unexpectedly" tone="warning" />;
}

export default function TodayScreen() {
  const greeting = greetingForHour(new Date().getHours());

  return (
    <Screen>
      <View style={{ gap: spacing.xs, marginBottom: spacing.lg }}>
        <AppText variant="body" tone="secondary">
          {greeting}
        </AppText>

        {/* Branded greeting area. The mark is decorative next to the word
            "Nura", so it is hidden from screen readers to avoid a duplicate
            announcement. */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <Image
            source={BRAND_MARK}
            accessibilityElementsHidden
            importantForAccessibility="no"
            style={{ width: 36, height: 36 }}
            resizeMode="contain"
          />
          <AppText variant="title">Nura</AppText>
        </View>
      </View>

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          Your daily dashboard will appear here as we set up your companion.
        </AppText>
        {config.isDev ? <BackendIndicator /> : null}
      </Card>
    </Screen>
  );
}
