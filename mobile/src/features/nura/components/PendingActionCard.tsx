/**
 * The Confirm / Cancel card for a change Nura offered (PRD 8, section 14).
 *
 * Section 14's mock is the whole design: Nura says what it would do, and two
 * buttons decide. Nothing has been changed when this appears -- the backend
 * returned a *pending* action, and the write happens only when Confirm is
 * pressed (sections 14 and 53).
 *
 * Once the offer has been answered the buttons go and the outcome is shown as
 * plain text, so scrolling back through a conversation never presents a live
 * Confirm for something already done.
 */
import { View } from 'react-native';

import { AppText, Button, Card } from '../../../components';
import { spacing } from '../../../theme/tokens';
import { ACTION_CANCELLED, ACTION_CONFIRMED, CANCEL, CONFIRM } from '../copy';
import type { PendingAction } from '../types';

interface PendingActionCardProps {
  action: PendingAction;
  onRespond: (confirmed: boolean) => void;
  busy: boolean;
}

export function PendingActionCard({ action, onRespond, busy }: PendingActionCardProps) {
  if (action.state !== 'pending') {
    return (
      <AppText variant="caption" tone="secondary">
        {action.state === 'confirmed' ? ACTION_CONFIRMED : ACTION_CANCELLED}
      </AppText>
    );
  }

  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="bodyStrong">{action.summary}</AppText>

      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label={CONFIRM}
          onPress={() => onRespond(true)}
          disabled={busy}
          accessibilityHint="Makes the change Nura described"
          style={{ flex: 1 }}
        />
        <Button
          label={CANCEL}
          variant="secondary"
          onPress={() => onRespond(false)}
          disabled={busy}
          accessibilityHint="Leaves everything as it is"
          style={{ flex: 1 }}
        />
      </View>
    </Card>
  );
}
