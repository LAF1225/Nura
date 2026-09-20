/**
 * Connect Nura to Wi-Fi (PRD 2, sections 21-23).
 *
 * The password is obscured by default, never logged, never stored, and lives
 * only in this screen's memory until it is encrypted and sent to the verified
 * robot. Manual entry of the network name always works; the phone's own
 * network is only offered when the OS is willing to share it.
 */
import NetInfo from '@react-native-community/netinfo';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  FlowErrorCard,
  Screen,
  TextField,
} from '../../src/components';
import { usePairingRecovery } from '../../src/hooks/usePairingRecovery';
import { useProvisioningFlow } from '../../src/hooks/useProvisioning';
import { FLOW_ERRORS } from '../../src/services/provisioning';
import {
  validateSsid,
  validateWifiPassword,
} from '../../src/services/provisioning/wifiPayload';
import { spacing } from '../../src/theme/tokens';

/** Android reports this placeholder when it declines to share the SSID. */
const UNKNOWN_SSID = '<unknown ssid>';

export default function WifiScreen() {
  const router = useRouter();
  const { flow, state } = useProvisioningFlow();
  const recovery = usePairingRecovery();

  const [ssid, setSsid] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<{ ssid: string | null; password: string | null }>({
    ssid: null,
    password: null,
  });
  const [phoneOn5GHz, setPhoneOn5GHz] = useState(false);

  useEffect(() => {
    let cancelled = false;
    NetInfo.fetch()
      .then((net) => {
        if (cancelled || net.type !== 'wifi') return;
        const details = net.details as {
          ssid?: string | null;
          frequency?: number | null;
        };
        if (details.ssid && details.ssid !== UNKNOWN_SSID) {
          setSsid((current) => current || details.ssid || '');
        }
        setPhoneOn5GHz(typeof details.frequency === 'number' && details.frequency > 4900);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (state.phase === 'provisioning') {
      router.push('/pairing/progress');
    }
  }, [state.phase, router]);

  useEffect(() => {
    // Leaving setup drops the password from memory.
    return () => setPassword('');
  }, []);

  function submit() {
    const next = { ssid: validateSsid(ssid), password: validateWifiPassword(password) };
    setErrors(next);
    if (next.ssid || next.password) return;
    void flow.submitWifi({ ssid, password });
  }

  if (state.phase === 'failed' && !state.canRetryWifi) {
    return (
      <Screen>
        <FlowErrorCard
          error={state.error}
          busy={recovery.busy}
          onAction={recovery.handle}
        />
      </Screen>
    );
  }

  const lastError = state.phase === 'awaitingWifi' ? state.lastError : null;

  return (
    <Screen>
      <AppText
        variant="title"
        accessibilityRole="header"
        style={{ marginBottom: spacing.xs }}
      >
        Connect Nura to Wi-Fi
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        Nura uses 2.4 GHz Wi-Fi. Many home routers automatically support both 2.4 GHz and
        5 GHz.
      </AppText>

      {lastError ? (
        <Card style={{ marginBottom: spacing.md, gap: spacing.xxs }}>
          <AppText variant="bodyStrong" tone="warning" accessibilityLiveRegion="polite">
            {FLOW_ERRORS[lastError].title}
          </AppText>
          <AppText variant="body" tone="secondary">
            {FLOW_ERRORS[lastError].message}
          </AppText>
        </Card>
      ) : null}

      {phoneOn5GHz ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="caption" tone="secondary">
            Your phone is using a 5 GHz network right now. That’s fine if your router also
            offers 2.4 GHz under the same or a similar name.
          </AppText>
        </Card>
      ) : null}

      <View style={{ gap: spacing.md }}>
        <TextField
          label="Network name"
          value={ssid}
          onChangeText={(value) => {
            setSsid(value);
            if (errors.ssid) setErrors((current) => ({ ...current, ssid: null }));
          }}
          error={errors.ssid}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="off"
          returnKeyType="next"
        />
        <TextField
          label="Wi-Fi password"
          value={password}
          onChangeText={(value) => {
            setPassword(value);
            if (errors.password) setErrors((current) => ({ ...current, password: null }));
          }}
          error={errors.password}
          secureTextEntry={!showPassword}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete="off"
          // Keeps password managers and the keyboard from saving it.
          textContentType="none"
          importantForAutofill="no"
          returnKeyType="done"
          onSubmitEditing={submit}
        />
        <Button
          label={showPassword ? 'Hide password' : 'Show password'}
          variant="ghost"
          onPress={() => setShowPassword((current) => !current)}
          accessibilityHint={
            showPassword ? 'Hides the Wi-Fi password' : 'Shows the Wi-Fi password'
          }
          style={{ alignSelf: 'flex-start' }}
        />
      </View>

      <Button label="Connect" onPress={submit} style={{ marginTop: spacing.xl }} />
      <Button
        label="Cancel setup"
        variant="ghost"
        onPress={() => {
          void flow.cancel();
          router.dismissAll();
          router.replace('/connect-device');
        }}
        style={{ marginTop: spacing.sm }}
      />
    </Screen>
  );
}
