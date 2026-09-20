/**
 * What would you like to call this device? (PRD 2, sections 37-38.)
 *
 * The name is only a label; the robot's identity is unchanged. Saving also
 * completes setup, which asks the robot to introduce itself.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  TextField,
} from '../../src/components';
import { useCompleteDeviceSetup, useRenameDevice } from '../../src/hooks/useDevices';
import { isApiError } from '../../src/services/api/errors';
import { spacing } from '../../src/theme/tokens';

const SUGGESTIONS = ['Nura', 'Bedroom Nura', 'Living Room Nura', 'Desk Nura'];
const MAX_LENGTH = 40;

export default function NameScreen() {
  const router = useRouter();
  const { deviceId } = useLocalSearchParams<{ deviceId: string }>();
  const rename = useRenameDevice();
  const completeSetup = useCompleteDeviceSetup();

  const [name, setName] = useState('Nura');
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const busy = rename.isPending || completeSetup.isPending;

  async function save() {
    const trimmed = name.trim().replace(/\s+/g, ' ');
    if (!trimmed) {
      setError('Give Nura a name, or keep “Nura”.');
      return;
    }
    if (!deviceId || busy) return;
    setProblem(null);
    try {
      await rename.mutateAsync({ id: deviceId, displayName: trimmed });
      await completeSetup.mutateAsync(deviceId);
      router.replace({ pathname: '/pairing/success', params: { deviceId } });
    } catch (caught) {
      setProblem(
        isApiError(caught) && caught.code === 'device_not_online'
          ? 'Nura has gone offline. Check it’s powered on and connected, then try again.'
          : 'We couldn’t save that just now. Please try again.'
      );
    }
  }

  return (
    <Screen>
      <AppText
        variant="title"
        accessibilityRole="header"
        style={{ marginBottom: spacing.xs }}
      >
        Nura is connected
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        What would you like to call this device?
      </AppText>

      <TextField
        label="Device name"
        value={name}
        onChangeText={(value) => {
          setName(value);
          if (error) setError(null);
        }}
        error={error}
        maxLength={MAX_LENGTH}
        autoCapitalize="words"
        returnKeyType="done"
        onSubmitEditing={() => void save()}
      />

      <View style={{ marginTop: spacing.md, gap: spacing.xs }}>
        <AppText variant="caption" tone="secondary">
          Suggestions
        </AppText>
        <ListGroup>
          {SUGGESTIONS.map((suggestion) => (
            <ListRow
              key={suggestion}
              label={suggestion}
              role="radio"
              selected={name === suggestion}
              onPress={() => setName(suggestion)}
            />
          ))}
        </ListGroup>
      </View>

      {problem ? (
        <Card style={{ marginTop: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {problem}
          </AppText>
        </Card>
      ) : null}

      <Button
        label={busy ? 'Saving…' : 'Continue'}
        onPress={() => void save()}
        disabled={busy}
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
