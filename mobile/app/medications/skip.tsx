/**
 * Skipping a dose, with an optional reason (PRD 5, sections 19, 20 and 57).
 *
 * A separate screen rather than an inline choice, for one reason: the reason
 * is *optional*, and "Skip without a reason" has to be as easy to reach as any
 * of the answers. On a sheet it is one button among the others; folded into a
 * card it would end up as the thing you do by dismissing, which is not the
 * same as choosing.
 *
 * Nothing here interprets the answer. Choosing "Feeling unwell" changes
 * nothing about what Nura says or does, raises nothing with anybody, and
 * produces no advice (PRD 5, sections 19 and 57).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, Screen, TextField } from '../../src/components';
import { MISSED_DOSE_GUIDANCE, SKIP_REASONS } from '../../src/features/medications/doses';
import { useDoseAction } from '../../src/features/medications/hooks';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';
import type { SkipReasonCode } from '../../src/features/medications/types';

/** Matches `skip_reason_text` in the database. */
const REASON_TEXT_MAX_LENGTH = 200;

export default function SkipDoseScreen() {
  const { doseId } = useLocalSearchParams<{ doseId: string }>();
  const router = useRouter();
  const action = useDoseAction();
  const [note, setNote] = useState('');

  const skip = (reasonCode: SkipReasonCode) => {
    if (!doseId) return;
    const trimmed = note.trim();
    action.mutate(
      {
        doseId,
        input: {
          action: 'skip',
          reasonCode,
          reasonText: trimmed.length > 0 ? trimmed : null,
        },
      },
      { onSuccess: () => router.back() }
    );
  };

  return (
    <Screen>
      <View style={{ gap: spacing.lg }}>
        <View style={{ gap: spacing.xxs }}>
          <AppText variant="heading">Why are you skipping this dose?</AppText>
          <AppText variant="body" tone="secondary">
            This is optional. Nura records what you choose and nothing more.
          </AppText>
        </View>

        <View
          accessibilityRole="radiogroup"
          accessibilityLabel="Reason for skipping"
          style={{ gap: spacing.xs }}
        >
          {SKIP_REASONS.filter((reason) => reason.code !== 'none').map((reason) => (
            <Button
              key={reason.code}
              label={reason.label}
              variant="secondary"
              disabled={action.isPending}
              onPress={() => skip(reason.code)}
            />
          ))}
        </View>

        <TextField
          label="Anything you want to remember (optional)"
          value={note}
          onChangeText={setNote}
          placeholder="Only you will see this"
          maxLength={REASON_TEXT_MAX_LENGTH}
          multiline
          editable={!action.isPending}
        />

        <View style={{ gap: spacing.sm }}>
          <Button
            label="Skip without a reason"
            disabled={action.isPending}
            onPress={() => skip('none')}
          />
          <Button
            label="Cancel"
            variant="ghost"
            disabled={action.isPending}
            onPress={() => router.back()}
          />
        </View>

        {action.isError ? (
          <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(action.error)}
          </AppText>
        ) : null}

        <Card>
          <AppText variant="caption" tone="secondary">
            {MISSED_DOSE_GUIDANCE}
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
