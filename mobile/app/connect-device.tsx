/**
 * Device pairing placeholder (PRD 1, sections 46 and 47).
 *
 * PRD 2 implements BLE discovery and Wi-Fi provisioning. Until then this
 * screen exists so "Connect Nura" leads somewhere honest, and it states
 * plainly that pairing is not available rather than fabricating a connected
 * robot.
 */
import { useRouter } from 'expo-router';

import { AppText, Button, Card, Screen } from '../src/components';
import { spacing } from '../src/theme/tokens';

export default function ConnectDeviceScreen() {
  const router = useRouter();

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        Connecting your Nura
      </AppText>

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="bodyStrong" tone="warning">
          Not available yet
        </AppText>
        <AppText variant="body" tone="secondary">
          Pairing with the Nura device is not built yet. It arrives in the next stage,
          which covers Bluetooth discovery and Wi-Fi setup.
        </AppText>
        <AppText variant="caption" tone="secondary">
          You can keep using the rest of the app in the meantime.
        </AppText>
      </Card>

      <Button
        label="Back to Nura"
        onPress={() => router.replace('/')}
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
