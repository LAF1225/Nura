/**
 * Medication management (PRD 5, sections 5, 7, 28 and 62).
 *
 * The operational screen: what is due today and the three things you can do
 * about each one, then a way into schedules, refills and history. Concise on
 * purpose -- everything deeper has its own screen (PRD 5, section 7).
 *
 * Three things this screen is responsible for beyond drawing:
 *
 * **Draining the offline queue.** Anything recorded while the phone had no
 * signal is sent when this screen is focused or the connection returns, and
 * until then the row says it is saved on this phone (PRD 5, section 62).
 *
 * **Keeping the reminders honest.** Whatever doses are on screen are mirrored
 * into the OS scheduler, so a schedule edited on another device, a pause, or
 * a medication marked inactive all take effect here (sections 42 and 55).
 *
 * **Saying nothing clinical.** The only guidance on the whole screen is the
 * sentence pointing at a clinician, and it appears exactly once
 * (section 57).
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
import { OfflineBanner } from '../../src/components/today';
import { DoseCard } from '../../src/features/medications/components/DoseCard';
import { AdherenceSummaryCard } from '../../src/features/medications/components/MedicationSummaryCards';
import {
  doseStatusLine,
  doseTitle,
  isWaiting,
  MISSED_DOSE_GUIDANCE,
} from '../../src/features/medications/doses';
import {
  DEFAULT_HISTORY_DAYS,
  useAdherence,
  useDoseAction,
  useMedicationReminders,
  useMedicationSchedules,
  useSyncPendingDoseActions,
  useTodayDoses,
} from '../../src/features/medications/hooks';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function MedicationsScreen() {
  const router = useRouter();
  const isOffline = useIsOffline();

  const doses = useTodayDoses();
  const schedules = useMedicationSchedules();
  const adherence = useAdherence(DEFAULT_HISTORY_DAYS);
  const action = useDoseAction();

  useSyncPendingDoseActions();
  useMedicationReminders(doses.data);

  const today = doses.data;
  const waiting = today.filter(isWaiting);
  const recorded = today.filter((dose) => !isWaiting(dose));
  const scheduleCount = schedules.data?.length ?? 0;

  const run = (doseId: string, input: Parameters<typeof action.mutate>[0]['input']) =>
    action.mutate({ doseId, input });

  return (
    <Screen
      onRefresh={() => void doses.refetch()}
      refreshing={doses.isRefetching && !doses.isLoading}
    >
      {isOffline ? <OfflineBanner /> : null}

      {doses.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label="Loading today’s medications" />
        </Card>
      ) : doses.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura can’t load your medications</AppText>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(doses.error)}
          </AppText>
          <Button label="Try again" variant="secondary" onPress={() => doses.refetch()} />
        </Card>
      ) : scheduleCount === 0 ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">No reminders set up yet</AppText>
          <AppText variant="body" tone="secondary">
            Choose a medication you have already added and tell Nura when to remind you.
            You can change or pause a reminder at any time.
          </AppText>
          <Button
            label="Set up a reminder"
            onPress={() => router.push('/medications/schedules')}
          />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          <View style={{ gap: spacing.sm }}>
            <AppText variant="bodyStrong">Today</AppText>

            {waiting.length === 0 ? (
              <Card>
                <AppText variant="body" tone="secondary">
                  {today.length === 0
                    ? 'Nothing is scheduled for today.'
                    : 'Everything scheduled for today has been recorded.'}
                </AppText>
              </Card>
            ) : (
              waiting.map((dose) => (
                <DoseCard
                  key={dose.id}
                  title={doseTitle(dose)}
                  dueAt={dose.scheduledFor}
                  window={dose.window}
                  canSnooze={dose.canSnooze}
                  busy={action.isPending}
                  pending={dose.syncStatus === 'pending'}
                  onTaken={() => run(dose.id, { action: 'taken' })}
                  onSnooze={(minutes) => run(dose.id, { action: 'snooze', minutes })}
                  onSkip={() =>
                    router.push({
                      pathname: '/medications/skip',
                      params: { doseId: dose.id },
                    })
                  }
                />
              ))
            )}

            {recorded.length > 0 ? (
              <Card style={{ gap: spacing.xs }}>
                <AppText variant="bodyStrong">Recorded today</AppText>
                {recorded.map((dose) => (
                  <AppText key={dose.id} variant="body" tone="secondary">
                    {doseTitle(dose)} — {doseStatusLine(dose).toLowerCase()}
                  </AppText>
                ))}
              </Card>
            ) : null}
          </View>

          {adherence.data ? (
            <AdherenceSummaryCard
              adherence={adherence.data}
              days={DEFAULT_HISTORY_DAYS}
            />
          ) : null}

          <ListGroup>
            <ListRow
              label="Reminder schedules"
              value={scheduleCount === 1 ? '1 schedule' : `${scheduleCount} schedules`}
              showChevron
              onPress={() => router.push('/medications/schedules')}
              accessibilityHint="Opens your reminder schedules"
            />
            <ListRow
              label="Supply and refills"
              showChevron
              onPress={() => router.push('/medications/supply')}
              accessibilityHint="Opens how many doses you have left"
            />
            <ListRow
              label="History"
              showChevron
              onPress={() => router.push('/medications/history')}
              accessibilityHint="Opens what you have recorded over the last few weeks"
            />
          </ListGroup>

          {/* The only sentence on this screen that comes close to advice, and
              it points at a person rather than giving any (PRD 5, s57). */}
          <AppText variant="caption" tone="secondary">
            {MISSED_DOSE_GUIDANCE}
          </AppText>
        </View>
      )}
    </Screen>
  );
}
