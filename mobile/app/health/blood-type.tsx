/**
 * Blood type (PRD 4, section 15).
 *
 * One answer rather than a list, so it gets a chooser rather than a form.
 * "I don't know" and "Prefer not to say" are offered as answers in their own
 * right: both are true things a person can say, and recording one is better
 * than leaving the field blank and not knowing which was meant.
 *
 * Nura never infers this from anything.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  SkeletonCard,
} from '../../src/components';
import { useHealthSummary, useUpdateHealthSetup } from '../../src/features/health/hooks';
import { BLOOD_TYPE_OPTIONS } from '../../src/features/health/sections';
import type { BloodType } from '../../src/features/health/types';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function BloodTypeScreen() {
  const router = useRouter();
  const summary = useHealthSummary();
  const setup = useUpdateHealthSetup();

  const current = summary.data?.bloodType ?? null;

  const choose = (value: BloodType) => {
    setup.mutate({ bloodType: value }, { onSuccess: () => router.back() });
  };

  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header">
        Blood type
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.xs }}>
        Only if you know it. Nura never works this out on its own.
      </AppText>

      <View style={{ height: spacing.lg }} />

      {summary.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label="Loading" />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          <ListGroup>
            {BLOOD_TYPE_OPTIONS.map((option) => (
              <ListRow
                key={option.value}
                label={option.label}
                role="radio"
                selected={current === option.value}
                onPress={
                  setup.isPending ? undefined : () => choose(option.value as BloodType)
                }
              />
            ))}
          </ListGroup>

          {current !== null ? (
            <Button
              label="Remove blood type"
              variant="ghost"
              onPress={() => setup.mutate({ bloodType: null })}
              accessibilityHint="Clears your blood type from your health profile"
            />
          ) : null}

          {setup.isError ? (
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(setup.error)}
            </AppText>
          ) : null}
        </View>
      )}
    </Screen>
  );
}
