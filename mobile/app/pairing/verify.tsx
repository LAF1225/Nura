/**
 * Is this your Nura? (PRD 2, sections 14-16.)
 *
 * The robot shows a six-digit code; typing it here runs the SPAKE2 exchange.
 * Nothing about Wi-Fi is possible until this succeeds.
 */
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

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
import { shortIdFor } from '../../src/services/provisioning/protocol';
import { normaliseCode, validateCode } from '../../src/services/provisioning/wifiPayload';
import { useTheme } from '../../src/theme';
import { spacing } from '../../src/theme/tokens';

function Busy({ label }: { label: string }) {
  const theme = useTheme();
  return (
    <View
      accessible
      accessibilityLabel={label}
      accessibilityLiveRegion="polite"
      style={{ alignItems: 'center', gap: spacing.md, marginVertical: spacing.xxl }}
    >
      <ActivityIndicator size="large" color={theme.colors.accent} />
      <AppText variant="heading">{label}</AppText>
    </View>
  );
}

export default function VerifyScreen() {
  const router = useRouter();
  const { flow, state } = useProvisioningFlow();
  const recovery = usePairingRecovery();
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (state.phase === 'awaitingWifi') {
      router.replace('/pairing/wifi');
    }
  }, [state.phase, router]);

  function submit() {
    const problem = validateCode(code);
    setError(problem);
    if (problem) return;
    void flow.submitCode(normaliseCode(code));
    // Cleared on submit so a rejected code does not have to be deleted by
    // hand before trying the new one Nura is showing.
    setCode('');
  }

  if (state.phase === 'failed') {
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

  if (state.phase === 'connecting' || state.phase === 'idle') {
    return (
      <Screen>
        <Busy label="Connecting to Nura…" />
      </Screen>
    );
  }

  if (state.phase === 'verifying' || state.phase === 'awaitingWifi') {
    return (
      <Screen>
        <Busy label="Verifying device…" />
      </Screen>
    );
  }

  if (state.phase !== 'awaitingCode') {
    return null;
  }

  const notice =
    state.notice === 'wrongCode'
      ? `That code didn’t match. Check the code on Nura’s screen and try again. ${
          state.attemptsLeft === 1 ? '1 attempt' : `${state.attemptsLeft} attempts`
        } left.`
      : state.notice === 'codeExpired'
        ? 'That code expired. Nura is now showing a new one.'
        : null;

  return (
    <Screen>
      <AppText
        variant="title"
        accessibilityRole="header"
        style={{ marginBottom: spacing.xs }}
      >
        Is this your Nura?
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        Connected to Nura • {shortIdFor(state.info.hardwareId)}. Enter the 6-digit code
        shown on Nura’s screen.
      </AppText>

      {notice ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="body" tone="warning" accessibilityLiveRegion="polite">
            {notice}
          </AppText>
        </Card>
      ) : null}

      <TextField
        label="Code shown on Nura"
        value={code}
        onChangeText={(value) => {
          setCode(value);
          if (error) setError(null);
        }}
        error={error}
        keyboardType="number-pad"
        maxLength={7}
        autoFocus
        autoComplete="off"
        // Not "oneTimeCode": that would offer codes from text messages.
        textContentType="none"
        returnKeyType="done"
        onSubmitEditing={submit}
        hint="The code changes every couple of minutes."
      />

      <View style={{ gap: spacing.sm, marginTop: spacing.xl }}>
        <Button label="Verify" onPress={submit} />
        <Button
          label="Cancel"
          variant="ghost"
          onPress={() => {
            void flow.cancel();
            router.dismissTo('/pairing/discover');
          }}
        />
      </View>
    </Screen>
  );
}
