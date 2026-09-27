/**
 * One medication's supply, and recording a refill (PRD 5, sections 32-35).
 *
 * Two different things that look similar and are kept apart on purpose:
 *
 * **Adjust** corrects the count Nura is holding, because it has drifted -- a
 * dose taken out of the packet without being recorded, a miscount last time.
 * It does not touch the refill date.
 *
 * **Mark refilled** says a new supply has been picked up, and records both the
 * new count and the date. The new number replaces the old rather than being
 * added to it, because people count what is in front of them rather than what
 * they added to what they thought was left (PRD 5, section 35).
 *
 * Both are the user's own numbers. Nura never estimates one, never works out
 * how long a supply will last, and never suggests ordering anything.
 */
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { useLayoutEffect, useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, Screen, TextField } from '../../../src/components';
import { useHealthRecords } from '../../../src/features/health/hooks';
import { SECTIONS } from '../../../src/features/health/sections';
import { SUPPLY_CAVEAT } from '../../../src/features/medications/doses';
import {
  useMedicationSupply,
  useRecordRefill,
  useUpdateSupply,
} from '../../../src/features/medications/hooks';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

/** Digits only, and never negative -- the server refuses those anyway. */
function parseCount(value: string): number | null {
  if (!/^\d+$/.test(value.trim())) return null;
  const parsed = Number(value.trim());
  return Number.isSafeInteger(parsed) ? parsed : null;
}

export default function MedicationSupplyDetailScreen() {
  const { medicationId } = useLocalSearchParams<{ medicationId: string }>();
  const router = useRouter();
  const navigation = useNavigation();

  const supply = useMedicationSupply();
  const medications = useHealthRecords(SECTIONS.medications);
  const update = useUpdateSupply();
  const refill = useRecordRefill();

  const record = supply.data?.find((entry) => entry.medicationId === medicationId);
  const medication = medications.data?.find((entry) => entry.id === medicationId);
  const title =
    record?.medicationName ??
    (typeof medication?.name === 'string' ? medication.name : 'Medication');

  const [remaining, setRemaining] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<string | null>(null);

  const remainingValue = remaining ?? String(record?.remainingDoses ?? '');
  const thresholdValue = threshold ?? String(record?.refillThresholdDoses ?? '');
  const busy = update.isPending || refill.isPending;

  useLayoutEffect(() => {
    navigation.setOptions({ title });
  }, [navigation, title]);

  const save = () => {
    if (!medicationId) return;
    const count = parseCount(remainingValue);
    const warnAt = thresholdValue.trim().length === 0 ? null : parseCount(thresholdValue);
    if (count === null || warnAt === undefined) return;

    update.mutate(
      {
        medicationId,
        patch: {
          trackingEnabled: true,
          remainingDoses: count,
          refillThresholdDoses: warnAt,
        },
      },
      { onSuccess: () => router.back() }
    );
  };

  const markRefilled = () => {
    if (!medicationId) return;
    const count = parseCount(remainingValue);
    if (count === null) return;
    refill.mutate(
      { medicationId, remainingDoses: count },
      { onSuccess: () => router.back() }
    );
  };

  const invalid = parseCount(remainingValue) === null;

  return (
    <Screen>
      <View style={{ gap: spacing.lg }}>
        <Card style={{ gap: spacing.xxs }}>
          <AppText variant="heading">{title}</AppText>
          <AppText variant="body" tone="secondary">
            {record?.remainingDoses === undefined || record.remainingDoses === null
              ? 'No count recorded yet.'
              : `Nura currently has ${record.remainingDoses} recorded.`}
          </AppText>
          {record?.lastRefillDate ? (
            <AppText variant="caption" tone="secondary">
              Last refilled {record.lastRefillDate}.
            </AppText>
          ) : null}
        </Card>

        <TextField
          label="Doses remaining"
          value={remainingValue}
          onChangeText={setRemaining}
          placeholder="12"
          keyboardType="number-pad"
          editable={!busy}
          error={invalid && remainingValue.length > 0 ? 'Enter a whole number.' : null}
          hint={SUPPLY_CAVEAT}
        />

        <TextField
          label="Remind me when I have (optional)"
          value={thresholdValue}
          onChangeText={setThreshold}
          placeholder="5"
          keyboardType="number-pad"
          editable={!busy}
          hint="Leave blank and Nura won’t mention refills at all."
        />

        <View style={{ gap: spacing.sm }}>
          <Button label="Save" onPress={save} disabled={busy || invalid} />
          <Button
            label="Mark refilled"
            variant="secondary"
            onPress={markRefilled}
            disabled={busy || invalid}
            accessibilityHint="Records a new supply from today, with the count above"
          />
          <Button
            label="Cancel"
            variant="ghost"
            onPress={() => router.back()}
            disabled={busy}
          />
        </View>

        {update.isError || refill.isError ? (
          <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(update.error ?? refill.error)}
          </AppText>
        ) : null}
      </View>
    </Screen>
  );
}
