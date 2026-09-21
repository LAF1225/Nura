/**
 * The robot's connection, as Today shows it (PRD 3, sections 23, 54 and 57).
 *
 * Every state here is a normal state. An account with no robot has not gone
 * wrong -- the hardware may simply not be built yet -- so the card offers a
 * next step rather than an error (PRD 3, section 54).
 *
 * The status itself always comes from the backend. The app never infers that
 * a robot is online (PRD 2, section 34).
 */
import { useRouter } from 'expo-router';

import { spacing } from '../../theme/tokens';
import type { TodayDevice } from '../../types/today';
import { AppText } from '../AppText';
import { Button } from '../Button';
import { Card } from '../Card';
import { ConnectionChip, connectionSentence } from '../DeviceStatus';
import { StatusChip } from '../StatusChip';

interface NuraStatusCardProps {
  device: TodayDevice | null;
  /**
   * True when the screen is showing saved information. Presence is the one
   * thing a cache cannot honestly carry: offline we do not know whether the
   * robot is connected, and a stale "Online" would break the rule that this
   * only ever comes from the backend.
   */
  statusUnavailable?: boolean;
}

export function NuraStatusCard({
  device,
  statusUnavailable = false,
}: NuraStatusCardProps) {
  const router = useRouter();

  if (device === null) {
    return (
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading">Your Nura isn’t connected yet</AppText>
        <AppText variant="body" tone="secondary">
          You can keep setting up the app now and connect the robot when it’s ready.
        </AppText>
        <Button
          label="Connect"
          onPress={() => router.push('/connect-device')}
          accessibilityHint="Starts setting up a Nura robot"
        />
      </Card>
    );
  }

  if (statusUnavailable) {
    return (
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading">{device.displayName}</AppText>
        <StatusChip
          label="Status unavailable"
          tone="neutral"
          icon="cloud-offline-outline"
        />
        <AppText variant="body" tone="secondary">
          Nura can’t check the connection while you’re offline.
        </AppText>
      </Card>
    );
  }

  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="heading">{device.displayName}</AppText>
      {/* Chip carries an icon and a word, so the state never depends on colour
          alone (PRD 3, section 42). */}
      <ConnectionChip status={device.connectionStatus} />
      <AppText variant="body" tone="secondary">
        {connectionSentence(
          device.displayName,
          device.connectionStatus,
          device.lastSeenAt
        )}
      </AppText>
      <Button
        label={
          device.connectionStatus === 'online' ? 'View connection' : 'Check connection'
        }
        variant="secondary"
        onPress={() =>
          router.push({ pathname: '/devices/[id]', params: { id: device.deviceId } })
        }
        accessibilityHint="Opens this Nura’s status and settings"
      />
    </Card>
  );
}
