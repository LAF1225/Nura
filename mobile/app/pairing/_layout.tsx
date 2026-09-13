/**
 * The pairing screens (PRD 2). They share one provisioning flow, which keeps
 * the Bluetooth connection alive while the user moves between steps.
 */
import { Stack } from 'expo-router';

import { useTheme } from '../../src/theme';

export default function PairingLayout() {
  const theme = useTheme();

  return (
    <Stack
      screenOptions={{
        title: '',
        contentStyle: { backgroundColor: theme.colors.background },
        headerStyle: { backgroundColor: theme.colors.background },
        headerTintColor: theme.colors.textPrimary,
        headerShadowVisible: false,
      }}
    >
      <Stack.Screen name="discover" />
      <Stack.Screen name="verify" />
      <Stack.Screen name="wifi" />
      {/* Once Wi-Fi details are on their way, going "back" would mean nothing. */}
      <Stack.Screen
        name="progress"
        options={{ headerBackVisible: false, gestureEnabled: false }}
      />
      <Stack.Screen name="name" options={{ headerBackVisible: false, gestureEnabled: false }} />
      <Stack.Screen
        name="success"
        options={{ headerBackVisible: false, gestureEnabled: false }}
      />
      <Stack.Screen name="help" options={{ title: 'Pairing help' }} />
    </Stack>
  );
}
