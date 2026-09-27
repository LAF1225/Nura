/**
 * Care -- the operational side of looking after yourself (PRD 5, sections 6, 30).
 *
 * The Health/Care boundary PRD 5 section 30 sets, and this screen is where it
 * becomes visible:
 *
 *     Health = what the medication is
 *     Care   = reminders, schedules, adherence, refills
 *
 * PRD 5 fills the first section of this tab. Appointments, caregivers,
 * routines and family communication stay named-but-absent, because none of
 * them exists and a screen full of disabled rows would promise things Nura
 * cannot do (PRD 3, section 35).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card, Screen } from '../../src/components';
import { doseTitle, lowSupplySentence } from '../../src/features/medications/doses';
import {
  useMedicationSchedules,
  useSyncPendingDoseActions,
} from '../../src/features/medications/hooks';
import { useToday } from '../../src/hooks/useToday';
import { spacing } from '../../src/theme/tokens';

export default function CareScreen() {
  const router = useRouter();
  const today = useToday();
  const schedules = useMedicationSchedules();

  // Care is a place somebody lands after being offline, so this is a second
  // chance to send whatever is queued (PRD 5, section 62).
  useSyncPendingDoseActions();

  const medications = today.data?.medications ?? null;
  const scheduleCount = schedules.data?.length ?? 0;
  const next = medications?.nextDue ?? null;
  const low = medications?.lowSupply[0];

  return (
    <Screen
      onRefresh={() => void today.refetch()}
      refreshing={today.isRefetching && !today.isLoading}
    >
      <AppText variant="title" accessibilityRole="header">
        Care
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.xxs }}>
        Reminders, schedules and the people who help care for you.
      </AppText>

      <View style={{ height: spacing.lg }} />

      <View style={{ gap: spacing.lg }}>
        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Medications</AppText>
            <AppText variant="body" tone="secondary">
              {scheduleCount === 0
                ? 'No reminders set up yet.'
                : scheduleCount === 1
                  ? '1 reminder schedule'
                  : `${scheduleCount} reminder schedules`}
            </AppText>
          </View>

          {next ? (
            <View style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">Next</AppText>
              <AppText variant="body" tone="secondary">
                {doseTitle(next)}
              </AppText>
            </View>
          ) : null}

          {medications && medications.overdueCount > 0 ? (
            // Stated plainly. Not an alert, not a warning colour, not an
            // emergency (PRD 5, sections 24 and 29).
            <AppText variant="body" tone="secondary">
              {medications.overdueCount === 1
                ? '1 dose hasn’t been marked as taken.'
                : `${medications.overdueCount} doses haven’t been marked as taken.`}
            </AppText>
          ) : null}

          {low ? (
            <AppText variant="body" tone="secondary">
              {lowSupplySentence(low.medicationName, low.remainingDoses)}
            </AppText>
          ) : null}

          <Button
            label={scheduleCount === 0 ? 'Set up reminders' : 'View all'}
            onPress={() => router.push('/medications')}
            accessibilityHint="Opens medication reminders, supply and history"
          />
        </Card>

        <Card style={{ gap: spacing.xs }}>
          <AppText variant="body" tone="secondary">
            Appointments, routines and the people who help care for you will live here as
            Nura grows.
          </AppText>
          <AppText variant="caption" tone="secondary">
            No caregivers are set up yet.
          </AppText>
        </Card>
      </View>
    </Screen>
  );
}
