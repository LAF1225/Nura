/**
 * A caregiver's safety alerts (PRD 10, sections 37, 38, 50, 83, 84 and 97).
 *
 * **This is the whole of a caregiver's view of safety.** Section 50 allows
 * permitted safety events only, and the alert carries what section 85
 * permits: what was observed, when, whether there was a response, and how the
 * escalation went. No health record, no symptoms, no medications, and no
 * sight of the emergency-contact chain.
 *
 * **An alert is a record, not a notification.** The subtitle says so,
 * because section 38 is explicit that creating one does not mean anybody saw
 * it -- and this screen is where the caregiver finds out that a push would
 * have been sent if there were anything to send it with.
 *
 * **Acknowledging does not resolve anything** (section 125). The control
 * says what it records, and the person's own screens are unchanged by it.
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen } from '../../src/components';
import { useCareMode } from '../../src/features/caregivers/hooks';
import { CaregiverAlertCard } from '../../src/features/safety/components/SafetyCards';
import {
  ALERTS_EMPTY,
  ALERTS_SUBTITLE,
  ALERTS_TITLE,
  unreadAlertsSentence,
} from '../../src/features/safety/copy';
import {
  useAcknowledgeSafetyAlert,
  useSafetyAlerts,
} from '../../src/features/safety/hooks';
import { spacing } from '../../src/theme/tokens';

export default function CaregiverSafetyAlertsScreen() {
  const mode = useCareMode();
  // Caregiver mode only: this is somebody else's safety history, and the
  // owner's own is on the Safety screen (section 50).
  const profileId = mode.isCaregiverMode ? mode.profileId : null;
  const alerts = useSafetyAlerts(profileId);
  const acknowledge = useAcknowledgeSafetyAlert(profileId);

  const rows = alerts.data?.alerts ?? [];

  return (
    <Screen
      onRefresh={() => void alerts.refetch()}
      refreshing={alerts.isRefetching && !alerts.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <View style={{ gap: spacing.xxs }}>
          <AppText variant="heading">{ALERTS_TITLE}</AppText>
          <AppText variant="body" tone="secondary">
            {ALERTS_SUBTITLE}
          </AppText>
        </View>

        <AsyncState
          status={alerts.isError ? 'error' : alerts.data ? 'success' : 'loading'}
          error={alerts.error}
          isEmpty={rows.length === 0}
          emptyMessage={ALERTS_EMPTY}
          loadingLabel="Loading safety alerts"
          onRetry={() => void alerts.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            <Card>
              <AppText variant="body" tone="secondary">
                {unreadAlertsSentence(alerts.data?.unreadCount ?? 0)}
              </AppText>
            </Card>
            {rows.map((alert) => (
              <CaregiverAlertCard
                key={alert.id}
                alert={alert}
                busy={acknowledge.isPending}
                onAcknowledge={() => acknowledge.mutate(alert.id)}
              />
            ))}
          </View>
        </AsyncState>
      </View>
    </Screen>
  );
}
