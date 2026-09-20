/**
 * Nura is ready (PRD 2, sections 38-40 and 44).
 *
 * The status shown is the backend's, fetched fresh -- not an assumption carried
 * over from the setup screens.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Image, View } from 'react-native';

import { AppText, Button, Card, ConnectionChip, Screen } from '../../src/components';
import { useDevice } from '../../src/hooks/useDevices';
import { spacing } from '../../src/theme/tokens';

const BRAND_MARK = require('../../assets/branding/nura-mark-transparent.png');

export default function SuccessScreen() {
  const router = useRouter();
  const { deviceId, mode } = useLocalSearchParams<{ deviceId: string; mode?: string }>();
  const device = useDevice(deviceId);
  const reconnected = mode === 'reconnected';

  return (
    <Screen>
      <View style={{ alignItems: 'center', gap: spacing.sm, marginVertical: spacing.xl }}>
        <Image
          source={BRAND_MARK}
          accessibilityElementsHidden
          importantForAccessibility="no"
          style={{ width: 80, height: 80 }}
          resizeMode="contain"
        />
        <AppText
          variant="title"
          accessibilityRole="header"
          style={{ textAlign: 'center' }}
        >
          {reconnected ? 'Nura is back online' : 'Nura is ready'}
        </AppText>
      </View>

      <Card style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {reconnected
            ? 'Nura is connected to the new Wi-Fi network and still linked to your account.'
            : 'Your Nura is connected to Wi-Fi and linked to your account.'}
        </AppText>

        <View style={{ gap: spacing.xxs }}>
          <AppText variant="caption" tone="secondary">
            Device
          </AppText>
          <AppText variant="bodyStrong">{device.data?.displayName ?? 'Nura'}</AppText>
        </View>

        <View style={{ gap: spacing.xxs }}>
          <AppText variant="caption" tone="secondary">
            Status
          </AppText>
          {device.data ? (
            <ConnectionChip status={device.data.connectionStatus} />
          ) : (
            <AppText variant="body" tone="secondary">
              Checking…
            </AppText>
          )}
        </View>
      </Card>

      {!reconnected ? (
        <AppText variant="body" tone="secondary" style={{ marginTop: spacing.md }}>
          Nura is about to say hello.
        </AppText>
      ) : null}

      <Button
        label="Continue"
        onPress={() => {
          router.dismissAll();
          router.replace('/');
        }}
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
