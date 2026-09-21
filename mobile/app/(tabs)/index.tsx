/**
 * Today -- the everyday landing page (PRD 3, sections 5, 7 and 33).
 *
 * The screen's job is composition, not content. It fetches the day in one
 * request, decides which of the five states to show (loading, success, empty,
 * offline, error), and hands the rest to cards it looks up by key. Adding a
 * card in a later PRD should not mean editing this file.
 *
 * Refreshing: on focus when the data has gone stale, and on pull. Never on a
 * timer -- see `useToday` (PRD 3, sections 31, 55 and 56).
 */
import { useState } from 'react';

import { AppText, Button, Card, Screen, SkeletonCard } from '../../src/components';
import {
  DashboardCardList,
  GreetingHeader,
  ImportantTodaySection,
  OfflineBanner,
} from '../../src/components/today';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import {
  usePendingCheckIn,
  useRefreshOnFocus,
  useSubmitCheckIn,
  useSyncPendingCheckIn,
  useToday,
  useTodaySnapshot,
} from '../../src/hooks/useToday';
import { apiErrorMessage } from '../../src/services/api';
import { pendingAsCheckIn } from '../../src/services/checkins/pendingCheckIn';
import { spacing } from '../../src/theme/tokens';
import type { DailyCheckIn, WellbeingLevel } from '../../src/types/today';

export default function TodayScreen() {
  const today = useToday();
  const snapshot = useTodaySnapshot();
  const pending = usePendingCheckIn();
  const isOffline = useIsOffline();
  const submit = useSubmitCheckIn();
  // Sends anything queued, on focus and when the connection returns.
  useSyncPendingCheckIn();
  useRefreshOnFocus(today.refetch, today.dataUpdatedAt);

  const [isRefreshing, setIsRefreshing] = useState(false);

  /**
   * With no answer from the backend, fall back to the last one it gave -- but
   * only if it is for the same day. Yesterday's check-in shown as today's
   * would be a lie, and a wrong answer is worse than an honest blank
   * (PRD 3, section 26).
   */
  const saved =
    today.isError && snapshot.data?.localDate === today.localDate ? snapshot.data : null;
  const summary = today.data ?? saved;
  const isSaved = today.data === undefined && saved !== null;

  const preferredName = summary?.profile?.preferredName ?? null;

  /**
   * An answer saved on this phone wins over the server's, because it is what
   * the user last chose. It is replaced by the server's copy as soon as it
   * syncs (PRD 3, sections 27 and 28).
   */
  const pendingEntry =
    pending.data && (!summary || pending.data.localDate === summary.localDate)
      ? pending.data
      : null;
  const checkIn: DailyCheckIn | null = pendingEntry
    ? pendingAsCheckIn(pendingEntry)
    : (summary?.dailyCheckIn.checkIn ?? null);

  const refresh = async () => {
    setIsRefreshing(true);
    try {
      await today.refetch();
    } finally {
      setIsRefreshing(false);
    }
  };

  const onSubmitCheckIn = (wellbeingLevel: WellbeingLevel, note: string | null) => {
    submit.mutate({ wellbeingLevel, note });
  };

  return (
    <Screen onRefresh={() => void refresh()} refreshing={isRefreshing}>
      <GreetingHeader preferredName={preferredName} isLoading={today.isLoading} />

      {isOffline ? <OfflineBanner /> : null}

      {today.isLoading ? (
        <Card>
          <SkeletonCard lines={4} label="Loading today" />
        </Card>
      ) : summary ? (
        <>
          {isSaved ? (
            <AppText
              variant="caption"
              tone="secondary"
              style={{ marginBottom: spacing.sm }}
            >
              Showing what Nura last saved on this phone.
            </AppText>
          ) : null}

          <DashboardCardList
            cards={summary.cards}
            context={{
              device: summary.device,
              // Offline we genuinely do not know whether the robot is
              // connected, and a cached "Online" would break the rule that
              // presence only ever comes from the backend.
              statusUnavailable: isSaved,
              checkIn,
              recentCompletedCount: summary.dailyCheckIn.recentCompletedCount,
              isSavingCheckIn: submit.isPending,
              // A queued answer is not an error, so only a genuine refusal
              // reaches the card.
              checkInError: submit.isError ? apiErrorMessage(submit.error) : null,
              onSubmitCheckIn,
            }}
            // Directly under the check-in, as PRD 3 section 7 lays it out.
            insertAfter={{
              key: 'daily_checkin',
              node: <ImportantTodaySection items={summary.important} />,
            }}
          />
        </>
      ) : today.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura can’t load today’s information</AppText>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(today.error)}
          </AppText>
          <Button label="Try again" variant="secondary" onPress={() => today.refetch()} />
        </Card>
      ) : null}
    </Screen>
  );
}
