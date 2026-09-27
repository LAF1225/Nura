/**
 * One symptom, and everything logged about it (PRD 6, ss30, 35, 36, 37 and 38).
 *
 * The history PRD 6 section 36 asks for -- date, severity, how it changed, newest
 * first -- with the episode's own details above it and the three things that can
 * be done to it below.
 *
 * Two of those three are destructive in different ways, and the screen is careful
 * to say which is which:
 *
 *   **Mark as ended** keeps everything and takes the symptom out of the active
 *   list (PRD 6, section 37). This is what somebody wants when a symptom is over.
 *
 *   **Delete** removes the description, the history and the photos. It is offered
 *   because a symptom logged by mistake should be removable, and the confirmation
 *   says plainly what goes and points at the other option.
 *
 * A symptom that has ended offers **It has come back**, which starts a new linked
 * episode rather than reopening this one -- so each bout keeps its own onset and
 * its own history (PRD 6, section 38).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Alert, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SkeletonCard,
  StatusChip,
} from '../../../src/components';
import { SafetyNotice } from '../../../src/features/symptoms/components/SafetyNotice';
import { SymptomPhotoView } from '../../../src/features/symptoms/components/SymptomPhotoView';
import { SymptomTimelineRow } from '../../../src/features/symptoms/components/SymptomTimelineRow';
import {
  DELETE_EPISODE_BODY,
  DELETE_EPISODE_TITLE,
  EMPTY_HISTORY,
  episodeTitle,
  HISTORY_HEADING,
  isActiveStatus,
  joined,
  onsetSentence,
  PENDING_EXPLANATION,
  PENDING_LABEL,
  RECUR_BODY,
  RECUR_TITLE,
  RESOLVE_BODY,
  RESOLVE_TITLE,
  STATUS_LABEL,
} from '../../../src/features/symptoms/copy';
import { useSymptomDraftStore } from '../../../src/features/symptoms/draftStore';
import {
  useDeleteSymptom,
  useDeleteSymptomPhoto,
  usePendingSymptoms,
  useResolveSymptom,
  useSymptomEpisode,
} from '../../../src/features/symptoms/hooks';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

export default function SymptomDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const episodeId = typeof id === 'string' ? id : '';

  const episode = useSymptomEpisode(episodeId);
  const pending = usePendingSymptoms();
  const resolve = useResolveSymptom();
  const remove = useDeleteSymptom();
  const removePhoto = useDeleteSymptomPhoto();
  const start = useSymptomDraftStore((state) => state.start);
  const patch = useSymptomDraftStore((state) => state.patch);

  const data = episode.data;
  const queued = (pending.data ?? []).filter((record) => record.episodeId === episodeId);

  const confirmResolve = () => {
    Alert.alert(RESOLVE_TITLE, RESOLVE_BODY, [
      { text: 'Not yet', style: 'cancel' },
      { text: 'Mark as ended', onPress: () => resolve.mutate(episodeId) },
    ]);
  };

  const confirmDelete = () => {
    Alert.alert(DELETE_EPISODE_TITLE, DELETE_EPISODE_BODY, [
      { text: 'Keep it', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: () =>
          remove.mutate(episodeId, { onSuccess: () => router.replace('/symptoms') }),
      },
    ]);
  };

  const confirmRecurrence = () => {
    if (data === undefined) return;
    Alert.alert(RECUR_TITLE, RECUR_BODY, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Yes, it has',
        onPress: () => {
          // A recurrence starts a fresh description of *this* bout, so it goes
          // through the normal log flow. `recurOf` is what links the new episode
          // to the one it follows, and it survives an offline save
          // (PRD 6, section 38).
          start('manual_app', { episodeName: data.name, recurOf: episodeId });
          // The name carries over so the new bout is recognisably the same
          // symptom; the server keeps the authoritative name either way.
          patch({ mainSymptom: data.name, site: data.bodySite ?? undefined });
          router.push('/symptoms/log');
        },
      },
    ]);
  };

  return (
    <Screen
      onRefresh={() => void episode.refetch()}
      refreshing={episode.isRefetching && !episode.isLoading}
    >
      {episode.isLoading ? (
        <Card>
          <SkeletonCard lines={4} label="Loading this symptom" />
        </Card>
      ) : episode.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura can’t load this symptom</AppText>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(episode.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => episode.refetch()}
          />
        </Card>
      ) : data === undefined ? null : (
        <View style={{ gap: spacing.lg, paddingBottom: spacing.xl }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="title" accessibilityRole="header">
              {episodeTitle(data.name, data.latestEntry?.severity)}
            </AppText>
            <AppText variant="body" tone="secondary">
              {joined([
                isActiveStatus(data.status) ? null : STATUS_LABEL[data.status],
                data.bodySite,
                onsetSentence(data),
              ]) ?? 'No details recorded yet'}
            </AppText>
            {data.previousEpisodeId !== null ? (
              <AppText variant="caption" tone="secondary">
                This is a later bout. The earlier one is kept separately.
              </AppText>
            ) : null}
          </View>

          <SafetyNotice notice={data.safety.notice} urgent={data.safety.urgent} />

          {queued.length > 0 ? (
            <Card style={{ gap: spacing.xxs }}>
              <StatusChip
                label={PENDING_LABEL}
                tone="info"
                icon="cloud-offline-outline"
              />
              <AppText variant="caption" tone="secondary">
                {PENDING_EXPLANATION}
              </AppText>
            </Card>
          ) : null}

          {isActiveStatus(data.status) ? (
            <Button
              label="Add an update"
              onPress={() =>
                router.push({
                  pathname: '/symptoms/[id]/update',
                  params: { id: episodeId },
                })
              }
              accessibilityHint={`Records how your ${data.name.toLowerCase()} is doing now`}
            />
          ) : (
            <Button
              label="It has come back"
              onPress={confirmRecurrence}
              accessibilityHint="Starts a new record for this time round"
            />
          )}

          <View style={{ gap: spacing.xs }}>
            <AppText variant="bodyStrong">{HISTORY_HEADING}</AppText>
            <Card>
              {(data.entries ?? []).length === 0 ? (
                <AppText variant="body" tone="secondary">
                  {EMPTY_HISTORY}
                </AppText>
              ) : (
                (data.entries ?? []).map((entry, index, all) => (
                  <View key={entry.id}>
                    <SymptomTimelineRow entry={entry} last={index === all.length - 1} />
                    {entry.photos.length > 0 ? (
                      <View
                        style={{
                          flexDirection: 'row',
                          flexWrap: 'wrap',
                          gap: spacing.xs,
                          paddingBottom: spacing.sm,
                        }}
                      >
                        {entry.photos.map((photo, photoIndex) => (
                          <SymptomPhotoView
                            key={photo.id}
                            episodeId={episodeId}
                            photo={photo}
                            index={photoIndex}
                            onRemove={(photoId) =>
                              removePhoto.mutate({
                                episodeId,
                                entryId: entry.id,
                                photoId,
                              })
                            }
                          />
                        ))}
                      </View>
                    ) : null}
                  </View>
                ))
              )}
            </Card>
          </View>

          <View style={{ gap: spacing.sm }}>
            {isActiveStatus(data.status) ? (
              <Button
                label="Mark as ended"
                variant="secondary"
                onPress={confirmResolve}
                accessibilityHint="Moves it out of your active list and keeps the history"
              />
            ) : null}
            <Button
              label="Delete this symptom"
              variant="ghost"
              onPress={confirmDelete}
              accessibilityHint="Removes it and everything logged about it"
            />
          </View>
        </View>
      )}
    </Screen>
  );
}
