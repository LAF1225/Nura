/**
 * Pending care requests, on Today (PRD 9, sections 48, 87 and 102).
 *
 * Section 87 asks for a waiting care request to be visible on Today, with a way
 * in to Review and -- its own sentence -- *never* auto-applied. This card has one
 * button and it navigates.
 *
 * **It draws nothing when there is nothing.** A card that said "no care requests"
 * every morning would be the opposite of PRD 3 section 3's calm Today. Like the
 * symptom card, it is simply absent until it is relevant.
 *
 * **No notification preference gates it** (section 48). An approval request has to
 * stay visible in the app even when push is off, so this reads the care summary
 * and nothing else.
 *
 * It reads its own summary rather than being handed one, the same way the health
 * profile card does: Today should not pay for a request when the card is hidden.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card } from '../../../components';
import { spacing } from '../../../theme/tokens';
import { pendingRequestsSentence } from '../copy';
import { useCareSummary } from '../hooks';

export function CareRequestsTodayCard() {
  const router = useRouter();
  const summary = useCareSummary();
  const pending = summary.data?.pendingSuggestionCount ?? 0;

  if (pending === 0) return null;

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading" accessibilityRole="header">
          Care request
        </AppText>
        <AppText variant="body" tone="secondary">
          {pendingRequestsSentence(pending)}
        </AppText>
      </View>
      <Button
        label="Review"
        onPress={() => router.push('/caregivers/requests')}
        accessibilityHint="Opens the changes someone has suggested"
      />
    </Card>
  );
}
