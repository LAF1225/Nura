/**
 * What has been recorded, day by day (PRD 5, sections 24, 26 and 27).
 *
 * A record, not a report. Every row says what happened and when; nothing is
 * scored, no day is marked good or bad, and there is no streak. A dose nobody
 * recorded reads as "wasn't marked as taken", which is the fact, rather than
 * as a miss, which would be a judgement (PRD 5, section 24).
 *
 * The range chips are the filter PRD 5 section 26 asks for. Filtering by
 * medication is done from that medication's own row on the supply screen, so
 * this screen stays a plain chronological list.
 */
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, Screen, SkeletonCard } from '../../src/components';
import {
  AdherenceSummaryCard,
  MedicationHistoryRow,
} from '../../src/features/medications/components/MedicationSummaryCards';
import {
  formatDoseDay,
  groupByDay,
  MISSED_DOSE_GUIDANCE,
} from '../../src/features/medications/doses';
import {
  HISTORY_RANGES,
  useAdherence,
  useDoseHistory,
} from '../../src/features/medications/hooks';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function MedicationHistoryScreen() {
  const [days, setDays] = useState<number>(HISTORY_RANGES[0]);
  const history = useDoseHistory(days);
  const adherence = useAdherence(days);

  const grouped = groupByDay(history.data);

  return (
    <Screen
      onRefresh={() => void history.refetch()}
      refreshing={history.isRefetching && !history.isLoading}
    >
      <View style={{ gap: spacing.lg }}>
        <View
          accessibilityRole="radiogroup"
          accessibilityLabel="How far back to show"
          style={{ flexDirection: 'row', gap: spacing.xs }}
        >
          {HISTORY_RANGES.map((range) => (
            <Button
              key={range}
              label={`Last ${range} days`}
              variant={range === days ? 'primary' : 'secondary'}
              onPress={() => setDays(range)}
              style={{ flex: 1 }}
            />
          ))}
        </View>

        {adherence.data ? (
          <AdherenceSummaryCard adherence={adherence.data} days={days} />
        ) : null}

        {history.isLoading ? (
          <Card>
            <SkeletonCard lines={4} label="Loading your medication history" />
          </Card>
        ) : history.isError ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(history.error)}
            </AppText>
            <Button
              label="Try again"
              variant="secondary"
              onPress={() => history.refetch()}
            />
          </Card>
        ) : grouped.length === 0 ? (
          <Card>
            <AppText variant="body" tone="secondary">
              Nothing has been recorded in this period.
            </AppText>
          </Card>
        ) : (
          grouped.map((day) => (
            <View key={day.localDate} style={{ gap: spacing.xs }}>
              <AppText variant="bodyStrong">{formatDoseDay(day.localDate)}</AppText>
              <Card style={{ gap: spacing.xxs }}>
                {day.doses.map((dose) => (
                  <MedicationHistoryRow key={dose.id} dose={dose} />
                ))}
              </Card>
            </View>
          ))
        )}

        <AppText variant="caption" tone="secondary">
          {MISSED_DOSE_GUIDANCE}
        </AppText>
      </View>
    </Screen>
  );
}
