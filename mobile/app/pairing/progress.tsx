/**
 * Setting Nura up (PRD 2, sections 36, 52 and 53).
 *
 * Shows the real stage in words. Success is decided by the flow, which only
 * reaches `online` once the backend has heard from the robot -- never merely
 * because the Wi-Fi details were sent.
 */
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Card,
  FlowErrorCard,
  ProgressSteps,
  Screen,
  type ProgressStepItem,
} from '../../src/components';
import { usePairingRecovery } from '../../src/hooks/usePairingRecovery';
import { useProvisioningFlow } from '../../src/hooks/useProvisioning';
import { fetchDevice } from '../../src/services/api/devices';
import { spacing } from '../../src/theme/tokens';

const STEPS: ProgressStepItem[] = [
  { key: 'connecting', label: 'Connecting to Nura…' },
  { key: 'verifying', label: 'Verifying device…' },
  { key: 'sendingWifi', label: 'Sending Wi-Fi details…' },
  { key: 'joiningWifi', label: 'Connecting Nura to Wi-Fi…' },
  { key: 'linking', label: 'Linking Nura to your account…' },
  { key: 'checking', label: 'Checking connection…' },
];

export default function ProgressScreen() {
  const router = useRouter();
  const { state } = useProvisioningFlow();
  const recovery = usePairingRecovery();

  useEffect(() => {
    if (state.phase !== 'online') return;
    let cancelled = false;
    const deviceId = state.deviceId;
    // First-time setup continues to naming; a Wi-Fi change is already named.
    fetchDevice(deviceId)
      .then((device) => {
        if (cancelled) return;
        if (device.setupCompletedAt) {
          router.replace({ pathname: '/pairing/success', params: { deviceId, mode: 'reconnected' } });
        } else {
          router.replace({ pathname: '/pairing/name', params: { deviceId } });
        }
      })
      .catch(() => {
        if (!cancelled) router.replace({ pathname: '/pairing/name', params: { deviceId } });
      });
    return () => {
      cancelled = true;
    };
  }, [state, router]);

  if (state.phase === 'failed') {
    return (
      <Screen>
        <FlowErrorCard
          error={state.error}
          busy={recovery.busy}
          onAction={recovery.handle}
          exclude={state.canCheckAgain ? [] : ['checkAgain']}
        />
      </Screen>
    );
  }

  const currentKey = state.phase === 'provisioning' ? state.step : 'checking';
  const bleDropped = state.phase === 'provisioning' && !state.bleConnected;

  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header" style={{ marginBottom: spacing.lg }}>
        Setting up Nura
      </AppText>

      <Card>
        <ProgressSteps steps={STEPS} currentKey={currentKey} />
      </Card>

      <View style={{ marginTop: spacing.lg, gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          This usually takes under a minute. Keep Nura plugged in and nearby.
        </AppText>
        {bleDropped ? (
          <AppText variant="body" tone="secondary" accessibilityLiveRegion="polite">
            Your phone’s Bluetooth link to Nura has ended, which is normal at this point. We’re
            checking with Nura services instead.
          </AppText>
        ) : null}
      </View>
    </Screen>
  );
}
