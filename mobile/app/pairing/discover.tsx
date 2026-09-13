/**
 * Looking for Nura (PRD 2, sections 8, 18 and 19).
 *
 * Starts as soon as the screen opens, which is the moment the user tapped
 * "Find my Nura" -- so that is when the permission prompt appears. Scans for
 * about 12 seconds, then stops; trying again is always the user's choice.
 */
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';

import { AppText, Button, Card, FlowErrorCard, Screen } from '../../src/components';
import { usePairingRecovery } from '../../src/hooks/usePairingRecovery';
import { useNuraDiscovery, useProvisioningFlow } from '../../src/hooks/useProvisioning';
import type { DiscoveredNura } from '../../src/services/provisioning';
import { SIGNAL_LABELS, signalStrength } from '../../src/services/provisioning/discovery';
import { useTheme } from '../../src/theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../src/theme/tokens';

function DeviceRow({ device, onPress }: { device: DiscoveredNura; onPress: () => void }) {
  const theme = useTheme();
  const name = device.shortId ? `Nura • ${device.shortId}` : 'Nura';
  const signal = SIGNAL_LABELS[signalStrength(device.rssi)];

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${name}, ${signal}`}
      accessibilityHint="Connects to this Nura"
      style={({ pressed }) => ({
        minHeight: minTouchTarget + spacing.md,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        padding: spacing.md,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: theme.colors.surface,
        opacity: pressed ? 0.85 : 1,
      })}
    >
      <Ionicons name="radio-outline" size={iconSize.md} color={theme.colors.accent} />
      <View style={{ flex: 1 }}>
        <AppText variant="bodyStrong">{name}</AppText>
        <AppText variant="caption" tone="secondary">
          {signal}
        </AppText>
      </View>
      <Ionicons name="chevron-forward" size={iconSize.sm} color={theme.colors.textSecondary} />
    </Pressable>
  );
}

export default function DiscoverScreen() {
  const router = useRouter();
  const theme = useTheme();
  const { state, start } = useNuraDiscovery();
  const { flow } = useProvisioningFlow();
  const recovery = usePairingRecovery();

  useEffect(() => {
    void start();
  }, [start]);

  function choose(device: DiscoveredNura) {
    void flow.connect(device);
    router.push('/pairing/verify');
  }

  const scanning = state.status === 'checking' || state.status === 'scanning';
  const devices = state.status === 'scanning' || state.status === 'finished' ? state.devices : [];

  if (state.status === 'blocked') {
    return (
      <Screen>
        <FlowErrorCard
          error={state.reason}
          busy={recovery.busy}
          onAction={(action) => (action === 'findAgain' ? void start() : void recovery.handle(action))}
        />
      </Screen>
    );
  }

  if (state.status === 'finished' && devices.length === 0) {
    return (
      <Screen>
        <FlowErrorCard
          error="noNuraFound"
          onAction={(action) => (action === 'findAgain' ? void start() : void recovery.handle(action))}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header" style={{ marginBottom: spacing.xs }}>
        {scanning ? 'Looking for Nura…' : 'Choose your Nura'}
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        Pick the one whose four characters match the screen on your Nura.
      </AppText>

      {scanning ? (
        <View
          accessible
          accessibilityLabel="Searching for Nura nearby"
          accessibilityLiveRegion="polite"
          style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: spacing.md }}
        >
          <ActivityIndicator color={theme.colors.accent} />
          <AppText variant="body" tone="secondary">
            Searching nearby…
          </AppText>
        </View>
      ) : null}

      {devices.length > 0 ? (
        <View style={{ gap: spacing.sm }}>
          <AppText variant="bodyStrong">Nearby devices</AppText>
          {devices.map((device) => (
            <DeviceRow key={device.peripheralId} device={device} onPress={() => choose(device)} />
          ))}
        </View>
      ) : null}

      {state.status === 'finished' ? (
        <View style={{ gap: spacing.sm, marginTop: spacing.xl }}>
          <Button label="Search again" variant="secondary" onPress={() => void start()} />
        </View>
      ) : null}

      <Card style={{ marginTop: spacing.xl }}>
        <Button
          label="Nura not appearing?"
          variant="ghost"
          onPress={() => router.push('/pairing/help')}
        />
      </Card>
    </Screen>
  );
}
