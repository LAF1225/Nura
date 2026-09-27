/**
 * The symptoms overview (PRD 6, sections 4, 7 and 49).
 *
 * Two equal ways in, exactly as PRD 6 section 4 requires: **Talk to Nura** and
 * **Log manually**, side by side, the same size, neither presented as the clever
 * option. They fill the same draft and end on the same review screen, so the
 * choice is about how somebody prefers to type, not about what gets recorded.
 *
 * Below that: what is active, and a way into the history. Nothing else -- PRD 6
 * section 7 asks specifically not to overload this screen with symptom detail,
 * and the detail screen is one tap away.
 *
 * It also drains the offline queue on focus, so a symptom described on a train
 * reaches the backend as soon as there is a signal (PRD 6, section 59).
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
  StatusChip,
} from '../../src/components';
import { OfflineBanner } from '../../src/components/today';
import { SymptomCard } from '../../src/features/symptoms/components/SymptomCard';
import {
  ACTIVE_HEADING,
  EMPTY_ACTIVE,
  MANUAL_ACTION,
  OVERVIEW_DESCRIPTION,
  PENDING_EXPLANATION,
  PENDING_LABEL,
  TALK_ACTION,
} from '../../src/features/symptoms/copy';
import { useSymptomDraftStore } from '../../src/features/symptoms/draftStore';
import {
  useActiveSymptoms,
  usePendingSymptoms,
  useSymptomSummary,
  useSyncPendingSymptoms,
} from '../../src/features/symptoms/hooks';
import { NOT_ADVICE } from '../../src/features/symptoms/safetyMessages';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';
import { localDateString } from '../../src/utils/date';

export default function SymptomsScreen() {
  const router = useRouter();
  const isOffline = useIsOffline();

  const active = useActiveSymptoms();
  const summary = useSymptomSummary();
  const pending = usePendingSymptoms();

  const start = useSymptomDraftStore((state) => state.start);
  const draft = useSymptomDraftStore((state) => state.draft);
  const hydrated = useSymptomDraftStore((state) => state.hydrated);

  useSyncPendingSymptoms();

  const today = localDateString();
  const episodes = active.data ?? [];
  const queued = pending.data ?? [];
  // Queued records that would create a new symptom -- the ones with no episode
  // to show them under yet.
  const newAndQueued = queued.filter((record) => record.episodeId === undefined);

  const beginGuided = () => {
    start('guided_app');
    router.push('/symptoms/talk');
  };

  const beginManual = () => {
    start('manual_app');
    router.push('/symptoms/log');
  };

  return (
    <Screen
      onRefresh={() => void active.refetch()}
      refreshing={active.isRefetching && !active.isLoading}
    >
      <AppText variant="body" tone="secondary">
        {OVERVIEW_DESCRIPTION}
      </AppText>

      <View style={{ height: spacing.lg }} />

      {isOffline ? <OfflineBanner /> : null}

      {/* Two equal options (PRD 6, section 4). */}
      <View style={{ flexDirection: 'row', gap: spacing.xs }}>
        <Button
          label={TALK_ACTION}
          onPress={beginGuided}
          style={{ flex: 1 }}
          accessibilityHint="Answers a few short questions in your own words"
        />
        <Button
          label={MANUAL_ACTION}
          variant="secondary"
          onPress={beginManual}
          style={{ flex: 1 }}
          accessibilityHint="Fills in a form yourself"
        />
      </View>

      <View style={{ height: spacing.lg }} />

      {/* Something part-way through, from before the app was closed
          (PRD 6, section 59). */}
      {hydrated && draft !== null ? (
        <Card style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
          <AppText variant="bodyStrong">You have an unfinished description</AppText>
          <AppText variant="body" tone="secondary">
            {draft.mainSymptom
              ? `You started describing ${draft.mainSymptom.toLowerCase()}.`
              : 'You started describing a symptom.'}
          </AppText>
          <Button
            label="Carry on"
            variant="secondary"
            onPress={() =>
              router.push(
                draft.mode === 'guided_app' ? '/symptoms/talk' : '/symptoms/log'
              )
            }
          />
        </Card>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        <AppText variant="bodyStrong">{ACTIVE_HEADING}</AppText>

        {active.isLoading ? (
          <Card>
            <SkeletonCard lines={3} label="Loading your symptoms" />
          </Card>
        ) : active.isError ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="heading">Nura can’t load your symptoms</AppText>
            <AppText variant="body" tone="secondary">
              {apiErrorMessage(active.error)}
            </AppText>
            <Button
              label="Try again"
              variant="secondary"
              onPress={() => active.refetch()}
            />
          </Card>
        ) : episodes.length === 0 && newAndQueued.length === 0 ? (
          <Card>
            <AppText variant="body" tone="secondary">
              {EMPTY_ACTIVE}
            </AppText>
          </Card>
        ) : (
          <View style={{ gap: spacing.sm }}>
            {episodes.map((episode) => (
              <SymptomCard
                key={episode.id}
                episode={episode}
                today={today}
                pending={queued.some((record) => record.episodeId === episode.id)}
                onUpdate={() =>
                  router.push({
                    pathname: '/symptoms/[id]/update',
                    params: { id: episode.id },
                  })
                }
                onPress={() =>
                  router.push({ pathname: '/symptoms/[id]', params: { id: episode.id } })
                }
              />
            ))}

            {/* A symptom saved with no signal has no id yet, so it is shown from
                the queue rather than being invisible until it syncs
                (PRD 6, section 59). */}
            {newAndQueued.map((record) => (
              <Card key={record.clientEntryId} style={{ gap: spacing.xs }}>
                <AppText variant="heading">{record.displayName}</AppText>
                <StatusChip
                  label={PENDING_LABEL}
                  tone="info"
                  icon="cloud-offline-outline"
                />
                <AppText variant="caption" tone="secondary">
                  {PENDING_EXPLANATION}
                </AppText>
              </Card>
            ))}
          </View>
        )}
      </View>

      <View style={{ height: spacing.lg }} />

      <ListGroup>
        <ListRow
          label="All symptoms"
          value={
            summary.data === undefined
              ? undefined
              : summary.data.activeCount === 1
                ? '1 active'
                : `${summary.data.activeCount} active`
          }
          showChevron
          onPress={() => router.push('/symptoms/history')}
          accessibilityHint="Opens everything you have logged, including what has ended"
        />
      </ListGroup>

      <View style={{ height: spacing.lg }} />

      {/* The one sentence on this screen that comes close to advice, and it
          points away from Nura rather than giving any (PRD 6, section 81). */}
      <AppText variant="caption" tone="secondary" style={{ marginBottom: spacing.md }}>
        {NOT_ADVICE}
      </AppText>
    </Screen>
  );
}
