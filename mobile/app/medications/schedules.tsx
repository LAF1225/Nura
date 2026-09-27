/**
 * Every reminder schedule, and where a new one starts (PRD 5, sections 4, 11).
 *
 * A schedule is always attached to a medication the user has already added in
 * Health, which is why the bottom half of this screen is a list of their own
 * medications rather than a free-text field. PRD 5 section 4 keeps the record
 * and the schedule separate, and this is where that shows: Nura never invents
 * a medication in order to remind somebody about it.
 *
 * A medication marked as no longer taken is not offered. Its schedules are
 * paused rather than deleted, so marking it active again brings the reminders
 * back (PRD 5, section 38).
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
import { useHealthRecords } from '../../src/features/health/hooks';
import { SECTIONS } from '../../src/features/health/sections';
import { MedicationScheduleRow } from '../../src/features/medications/components/MedicationScheduleRow';
import { useMedicationSchedules } from '../../src/features/medications/hooks';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

function name(record: Record<string, unknown>): string {
  return typeof record.name === 'string' && record.name.length > 0
    ? record.name
    : 'Medication';
}

function dose(record: Record<string, unknown>): string | undefined {
  const amount = typeof record.dose === 'string' ? record.dose : '';
  const unit = typeof record.dose_unit === 'string' ? record.dose_unit : '';
  const joined = `${amount} ${unit}`.trim();
  return joined.length > 0 ? joined : undefined;
}

export default function MedicationSchedulesScreen() {
  const router = useRouter();
  const schedules = useMedicationSchedules();
  const medications = useHealthRecords(SECTIONS.medications);

  const rows = schedules.data ?? [];
  const active = (medications.data ?? []).filter((record) => record.is_active !== false);

  return (
    <Screen
      onRefresh={() => void schedules.refetch()}
      refreshing={schedules.isRefetching && !schedules.isLoading}
    >
      {schedules.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label="Loading your reminder schedules" />
        </Card>
      ) : schedules.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(schedules.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => schedules.refetch()}
          />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          {rows.length === 0 ? (
            <Card>
              <AppText variant="body" tone="secondary">
                No reminders yet. Choose a medication below to set one up.
              </AppText>
            </Card>
          ) : (
            <View style={{ gap: spacing.sm }}>
              {rows.map((schedule) => (
                <MedicationScheduleRow
                  key={schedule.id}
                  schedule={schedule}
                  onPress={() =>
                    router.push({
                      pathname: '/medications/schedule/[id]',
                      params: { id: schedule.id },
                    })
                  }
                />
              ))}
            </View>
          )}

          <View style={{ gap: spacing.xs }}>
            <AppText variant="bodyStrong">Set a reminder for</AppText>

            {active.length === 0 ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="body" tone="secondary">
                  Nura reminds you about medications you have added to your health
                  profile. Add one there first, and it will appear here.
                </AppText>
                <Button
                  label="Add a medication"
                  variant="secondary"
                  onPress={() =>
                    router.push({
                      pathname: '/health/[section]',
                      params: { section: 'medications' },
                    })
                  }
                />
              </Card>
            ) : (
              <ListGroup>
                {active.map((record) => (
                  <ListRow
                    key={record.id}
                    label={name(record)}
                    description={dose(record)}
                    showChevron
                    onPress={() =>
                      router.push({
                        pathname: '/medications/schedule/[id]',
                        params: { id: 'new', medicationId: record.id },
                      })
                    }
                    accessibilityHint={`Sets a reminder for ${name(record)}`}
                  />
                ))}
              </ListGroup>
            )}
          </View>

          <AppText variant="caption" tone="secondary">
            Reminders can be paused or removed at any time. Pausing keeps everything you
            have already recorded.
          </AppText>
        </View>
      )}
    </Screen>
  );
}
