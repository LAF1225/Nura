/**
 * How much of each medication is left (PRD 5, sections 31-35).
 *
 * Opt-in per medication. A count nobody keeps up to date is worse than no
 * count at all, so Nura never turns this on by itself and never estimates a
 * number -- it only ever shows back what the user entered, and says so
 * (section 34).
 *
 * Nothing here orders anything, contacts a pharmacy, or suggests changing a
 * dose. It counts tablets (PRD 5, section 57).
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
} from '../../../src/components';
import { useHealthRecords } from '../../../src/features/health/hooks';
import { SECTIONS } from '../../../src/features/health/sections';
import { RefillStatusCard } from '../../../src/features/medications/components/MedicationSummaryCards';
import { useMedicationSupply } from '../../../src/features/medications/hooks';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

function name(record: Record<string, unknown>): string {
  return typeof record.name === 'string' && record.name.length > 0
    ? record.name
    : 'Medication';
}

export default function MedicationSupplyScreen() {
  const router = useRouter();
  const supply = useMedicationSupply();
  const medications = useHealthRecords(SECTIONS.medications);

  const tracked = supply.data ?? [];
  const trackedIds = new Set(tracked.map((entry) => entry.medicationId));
  const untracked = (medications.data ?? []).filter(
    (record) => record.is_active !== false && !trackedIds.has(String(record.id))
  );

  const open = (medicationId: string) =>
    router.push({
      pathname: '/medications/supply/[medicationId]',
      params: { medicationId },
    });

  return (
    <Screen
      onRefresh={() => void supply.refetch()}
      refreshing={supply.isRefetching && !supply.isLoading}
    >
      {supply.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label="Loading your supply counts" />
        </Card>
      ) : supply.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(supply.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => supply.refetch()}
          />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          {tracked.length === 0 ? (
            <Card>
              <AppText variant="body" tone="secondary">
                You aren’t tracking any supplies yet. Choose a medication below and tell
                Nura roughly how many you have.
              </AppText>
            </Card>
          ) : (
            <View style={{ gap: spacing.sm }}>
              {tracked.map((entry) => (
                <RefillStatusCard
                  key={entry.medicationId}
                  supply={entry}
                  onAdjust={() => open(entry.medicationId)}
                  onRefilled={() => open(entry.medicationId)}
                />
              ))}
            </View>
          )}

          {untracked.length > 0 ? (
            <View style={{ gap: spacing.xs }}>
              <AppText variant="bodyStrong">Start tracking</AppText>
              <ListGroup>
                {untracked.map((record) => (
                  <ListRow
                    key={record.id}
                    label={name(record)}
                    showChevron
                    onPress={() => open(String(record.id))}
                    accessibilityHint={`Starts counting doses of ${name(record)}`}
                  />
                ))}
              </ListGroup>
            </View>
          ) : null}

          <AppText variant="caption" tone="secondary">
            Nura takes one off the count when you mark a dose as taken. Snoozing or
            skipping doesn’t change it, and you can correct the number at any time.
          </AppText>
        </View>
      )}
    </Screen>
  );
}
