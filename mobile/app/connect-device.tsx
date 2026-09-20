/**
 * Connect Nura -- the entry to pairing (PRD 2, sections 7, 42 and 43).
 *
 * If the account already has a Nura, that is shown first rather than jumping
 * straight into discovery. Bluetooth permission is not requested here: it is
 * asked for only once the user taps "Find my Nura" (PRD 2, section 8).
 */
import { useRouter } from 'expo-router';
import { Image, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ConnectionChip,
  connectionSentence,
  ListGroup,
  ListRow,
  Screen,
} from '../src/components';
import { useDevices } from '../src/hooks/useDevices';
import { spacing } from '../src/theme/tokens';

const BRAND_MARK = require('../assets/branding/nura-mark-transparent.png');

export default function ConnectDeviceScreen() {
  const router = useRouter();
  const devices = useDevices();
  const linked = devices.data ?? [];

  if (linked.length > 0) {
    return (
      <Screen>
        <AppText variant="title" style={{ marginBottom: spacing.md }}>
          Your Nura
        </AppText>

        <View style={{ gap: spacing.md }}>
          {linked.map((device) => (
            <Card key={device.id} style={{ gap: spacing.sm }}>
              <AppText variant="heading">{device.displayName}</AppText>
              <ConnectionChip status={device.connectionStatus} />
              <AppText variant="body" tone="secondary">
                {connectionSentence(
                  device.displayName,
                  device.connectionStatus,
                  device.lastSeenAt
                )}
              </AppText>
              <ListGroup>
                <ListRow
                  label="View connection"
                  leadingIcon="pulse-outline"
                  showChevron
                  onPress={() =>
                    router.push({ pathname: '/devices/[id]', params: { id: device.id } })
                  }
                />
                <ListRow
                  label="Reconnect"
                  description="Change Wi-Fi or reconnect over Bluetooth"
                  leadingIcon="refresh-outline"
                  showChevron
                  onPress={() => router.push('/pairing/discover')}
                />
              </ListGroup>
            </Card>
          ))}
        </View>

        <Button
          label="Add another Nura"
          variant="secondary"
          onPress={() => router.push('/pairing/discover')}
          style={{ marginTop: spacing.xl }}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: spacing.sm, marginVertical: spacing.lg }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 72, height: 72 }}
          resizeMode="contain"
        />
        <AppText
          variant="title"
          style={{ textAlign: 'center' }}
          accessibilityRole="header"
        >
          Connect your Nura
        </AppText>
      </View>

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body">Make sure Nura is powered on and nearby.</AppText>
        <AppText variant="body" tone="secondary">
          If this is the first time you’re setting it up, Nura should enter pairing mode
          automatically.
        </AppText>
      </Card>

      <View style={{ gap: spacing.sm, marginTop: spacing.xl }}>
        <Button
          label="Find my Nura"
          onPress={() => router.push('/pairing/discover')}
          accessibilityHint="Uses Bluetooth to look for Nura nearby"
        />
        <Button
          label="Nura not appearing?"
          variant="ghost"
          onPress={() => router.push('/pairing/help')}
        />
      </View>
    </Screen>
  );
}
