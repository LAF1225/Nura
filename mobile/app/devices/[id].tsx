/**
 * One Nura: its connection, recovery, and developer diagnostics
 * (PRD 2, sections 43-48).
 *
 * Offline is described calmly and never unpairs anything. Diagnostics appear
 * only in development builds and never include Wi-Fi passwords or tokens.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  ConnectionChip,
  connectionSentence,
  ListGroup,
  ListRow,
  Screen,
} from '../../src/components';
import { config } from '../../src/constants/config';
import { useDevice, useDeviceStatus } from '../../src/hooks/useDevices';
import { useProvisioningFlow } from '../../src/hooks/useProvisioning';
import { spacing } from '../../src/theme/tokens';

function Diagnostics({ deviceId }: { deviceId: string }) {
  const device = useDevice(deviceId);
  const status = useDeviceStatus(deviceId);
  const { state } = useProvisioningFlow();
  const data = device.data;

  const rows: [string, string][] = [
    ['hardware_id', data?.hardwareId ?? '—'],
    ['firmware version', data?.firmwareVersion ?? '—'],
    ['provisioning status', data?.provisioningStatus ?? '—'],
    ['connection status', status.data?.connectionStatus ?? '—'],
    ['checked in since claim', String(status.data?.checkedInSinceClaim ?? '—')],
    ['last_seen_at', data?.lastSeenAt ?? 'never'],
    ['claimed_at', data?.claimedAt ?? '—'],
    ['introduced_at', data?.introducedAt ?? '—'],
    ['last app flow phase', state.phase],
    ['last app flow error', state.phase === 'failed' ? state.error : 'none'],
  ];

  return (
    <Card style={{ gap: spacing.xs }}>
      <AppText variant="bodyStrong">Developer diagnostics</AppText>
      <AppText variant="caption" tone="secondary">
        Development builds only. Passwords and tokens are never shown.
      </AppText>
      {rows.map(([label, value]) => (
        <View key={label} style={{ flexDirection: 'row', gap: spacing.sm }}>
          <AppText variant="caption" tone="secondary" style={{ flex: 1 }}>
            {label}
          </AppText>
          <AppText variant="caption" style={{ flex: 1 }} selectable>
            {value}
          </AppText>
        </View>
      ))}
    </Card>
  );
}

export default function DeviceScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const device = useDevice(id);

  if (!device.data) {
    return (
      <Screen>
        <AsyncState
          status={device.isError ? 'error' : 'loading'}
          error={device.error}
          loadingLabel="Loading your Nura"
          onRetry={() => void device.refetch()}
        >
          {null}
        </AsyncState>
      </Screen>
    );
  }

  const nura = device.data;
  const offline = nura.connectionStatus !== 'online';

  return (
    <Screen>
      <AppText
        variant="title"
        accessibilityRole="header"
        style={{ marginBottom: spacing.sm }}
      >
        {nura.displayName}
      </AppText>

      <Card style={{ gap: spacing.sm }}>
        <ConnectionChip status={nura.connectionStatus} />
        <AppText variant="body" tone="secondary">
          {connectionSentence(nura.displayName, nura.connectionStatus, nura.lastSeenAt)}
        </AppText>
      </Card>

      <View style={{ gap: spacing.md, marginTop: spacing.lg }}>
        {offline ? (
          <Button
            label="Troubleshoot connection"
            onPress={() => router.push('/pairing/help')}
          />
        ) : null}

        <ListGroup>
          <ListRow
            label="Reconnect or change Wi-Fi"
            description="Hold Nura’s button for 3 seconds first"
            leadingIcon="refresh-outline"
            showChevron
            onPress={() => router.push('/pairing/discover')}
          />
        </ListGroup>

        {config.isDev ? <Diagnostics deviceId={nura.id} /> : null}
      </View>
    </Screen>
  );
}
