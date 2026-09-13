/**
 * A pairing problem, explained, with its recovery actions as real buttons
 * (PRD 2, section 50: every error has a way forward).
 */
import { View } from 'react-native';

import {
  FLOW_ERRORS,
  type FlowErrorKind,
  type RecoveryAction,
} from '../services/provisioning/flowErrors';
import { spacing } from '../theme/tokens';
import { AppText } from './AppText';
import { Button } from './Button';
import { Card } from './Card';

const ACTION_LABELS: Record<RecoveryAction, string> = {
  turnOnBluetooth: 'Turn on Bluetooth',
  openSettings: 'Open settings',
  findAgain: 'Find Nura again',
  pairingHelp: 'Pairing help',
  retryPassword: 'Retry password',
  chooseNetwork: 'Choose another network',
  tryAgain: 'Try again',
  checkAgain: 'Check again',
  done: 'Back to Nura',
};

interface FlowErrorCardProps {
  error: FlowErrorKind;
  onAction: (action: RecoveryAction) => void;
  /** Hide actions that can't work in the current state. */
  exclude?: RecoveryAction[];
  busy?: boolean;
}

export function FlowErrorCard({ error, onAction, exclude = [], busy }: FlowErrorCardProps) {
  const info = FLOW_ERRORS[error];
  const actions = info.actions.filter((action) => !exclude.includes(action));

  return (
    <View style={{ gap: spacing.md }}>
      <Card style={{ gap: spacing.xs }}>
        <AppText variant="heading" accessibilityRole="header" accessibilityLiveRegion="polite">
          {info.title}
        </AppText>
        <AppText variant="body" tone="secondary">
          {info.message}
        </AppText>
      </Card>
      <View style={{ gap: spacing.sm }}>
        {actions.map((action, index) => (
          <Button
            key={action}
            label={ACTION_LABELS[action]}
            variant={index === 0 ? 'primary' : 'secondary'}
            onPress={() => onAction(action)}
            disabled={busy}
          />
        ))}
      </View>
    </View>
  );
}
