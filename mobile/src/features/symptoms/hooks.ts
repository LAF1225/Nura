/**
 * Server state for symptoms (PRD 6, sections 50-53, 59 and 61).
 *
 * Every query key carries the profile id, for the same reason the health record
 * and medication keys do: an account can hold more than one profile, and a cache
 * keyed only by "symptoms" would happily show one person's description under
 * another's name.
 *
 * Three things here are worth reading rather than skimming.
 *
 * `useSaveSymptom` never rejects for a network failure -- it queues. "Saved on
 * this phone" is a success from the user's point of view, and the outcome says
 * which happened (PRD 6, section 59).
 *
 * `useSyncPendingSymptoms` drains that queue when a symptom screen is focused or
 * the phone comes back online. Every send carries the same client id, so the
 * queue can retry as often as it likes without creating a second record
 * (section 61).
 *
 * `useSymptomPhotoSource` resolves a photo's URL *and* its bearer token through
 * TanStack Query rather than component state. That is not incidental: private
 * media is fetched with an Authorization header, and a query is both the honest
 * shape for an async lookup and the one that re-renders reliably.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useFocusEffect } from 'expo-router';
import { useCallback } from 'react';

import { useOnReconnect } from '../../hooks/useNetworkStatus';
import { todayQueryKey } from '../../hooks/useToday';
import { localDateString } from '../../utils/date';
import { useAppStore } from '../../store/appStore';
import { healthSummaryQueryKey, useHealthProfileId } from '../health/hooks';
import {
  deleteEpisode,
  deletePhoto,
  fetchEpisode,
  fetchEpisodes,
  fetchSymptomSummary,
  photoSource,
  resolveEpisode,
  updateEntry,
  updateEpisode,
  type EntrySaved,
  type EpisodeFilter,
  type EpisodePatch,
} from './api';
import { entryPayload, episodePayload } from './draft';
import {
  loadPendingEntries,
  submitOrQueueEntry,
  syncPendingEntries,
  type SaveOutcome,
} from './pendingEntries';
import type {
  EntryPayload,
  PendingSymptomEntry,
  SymptomDraft,
  SymptomEpisode,
  SymptomSummary,
} from './types';

/**
 * Whose symptoms these are.
 *
 * The same person the health record belongs to. A symptom is something that
 * person is experiencing, so it cannot be about anybody else (PRD 6, s53).
 */
export const useSymptomProfileId = useHealthProfileId;

export const symptomEpisodesQueryKey = (profileId: string, scope = 'all') =>
  ['symptom-episodes', profileId, scope] as const;
export const symptomEpisodeQueryKey = (profileId: string, episodeId: string) =>
  ['symptom-episode', profileId, episodeId] as const;
export const symptomSummaryQueryKey = (profileId: string) =>
  ['symptom-summary', profileId] as const;
export const pendingSymptomsQueryKey = ['symptom-entries', 'pending'] as const;
export const symptomPhotoQueryKey = (photoId: string) =>
  ['symptom-photo-source', photoId] as const;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

// --- reading ----------------------------------------------------------------

/**
 * Episodes, filtered the four ways PRD 6 section 49 asks for.
 *
 * The filter is part of the cache key, so the active list and the full history
 * are separate entries rather than one that keeps being refetched with different
 * parameters.
 */
export function useSymptomEpisodes(filter: EpisodeFilter = {}) {
  const profileId = useSymptomProfileId();
  const enabled = useEnabled(profileId);
  const scope = filter.active
    ? 'active'
    : (filter.status ?? (filter.name ? `name:${filter.name}` : 'all'));

  const query = useQuery<SymptomEpisode[]>({
    queryKey: symptomEpisodesQueryKey(profileId ?? '', scope),
    queryFn: ({ signal }) => fetchEpisodes(profileId ?? '', filter, signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useActiveSymptoms() {
  return useSymptomEpisodes({ active: true });
}

export function useSymptomEpisode(episodeId: string | undefined) {
  const profileId = useSymptomProfileId();
  const enabled = useEnabled(profileId) && Boolean(episodeId);

  const query = useQuery<SymptomEpisode>({
    queryKey: symptomEpisodeQueryKey(profileId ?? '', episodeId ?? ''),
    queryFn: ({ signal }) => fetchEpisode(profileId ?? '', episodeId ?? '', signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useSymptomSummary() {
  const profileId = useSymptomProfileId();
  const enabled = useEnabled(profileId);

  return useQuery<SymptomSummary>({
    queryKey: symptomSummaryQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchSymptomSummary(profileId ?? '', signal),
    enabled,
  });
}

/** Symptoms saved on this phone but not yet accepted by the backend. */
export function usePendingSymptoms() {
  return useQuery<PendingSymptomEntry[]>({
    queryKey: pendingSymptomsQueryKey,
    queryFn: () => loadPendingEntries(),
    // Local storage; it only changes when this app changes it, and every such
    // change invalidates the key.
    staleTime: Infinity,
  });
}

/**
 * An authenticated `<Image>` source for one symptom photo.
 *
 * Null while signing in or when there is no API URL, which the component renders
 * as a placeholder rather than a broken image (PRD 6, section 63).
 */
export function useSymptomPhotoSource(
  episodeId: string,
  entryId: string,
  photoId: string
) {
  const profileId = useSymptomProfileId();
  const enabled = useEnabled(profileId);

  return useQuery({
    queryKey: symptomPhotoQueryKey(photoId),
    queryFn: () => photoSource(profileId ?? '', episodeId, entryId, photoId),
    enabled,
    // The URL does not change; only the token does, and it is re-read whenever
    // the cache entry is dropped.
    staleTime: 5 * 60 * 1000,
  });
}

// --- writing ----------------------------------------------------------------

/**
 * Everything a symptom change can affect.
 *
 * Deliberately broad. Saving an entry changes the episode, the active list, the
 * summary, the Today response and the Health overview's counts -- refreshing only
 * the obvious one is how a screen ends up disagreeing with itself.
 */
function useRefreshSymptoms(profileId: string | null) {
  const queryClient = useQueryClient();

  return useCallback(async () => {
    if (profileId === null) return;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['symptom-episodes', profileId] }),
      queryClient.invalidateQueries({ queryKey: ['symptom-episode', profileId] }),
      queryClient.invalidateQueries({ queryKey: symptomSummaryQueryKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: pendingSymptomsQueryKey }),
      queryClient.invalidateQueries({ queryKey: healthSummaryQueryKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: todayQueryKey(localDateString()) }),
    ]);
  }, [profileId, queryClient]);
}

/**
 * Turns a draft into the record the queue and the API both work from.
 *
 * A follow-up carries an episode id; a new symptom carries the episode body. One
 * shape covers both, which is what lets the offline queue hold either
 * (PRD 6, section 59).
 */
export function pendingRecordFor(
  draft: SymptomDraft,
  options: { savedAt?: Date; displayName?: string; recurOf?: string } = {}
): PendingSymptomEntry {
  const savedAt = options.savedAt ?? new Date();
  const entry = entryPayload(draft, savedAt);

  return {
    clientEntryId: draft.clientEntryId,
    episodeId: draft.episodeId,
    episode: draft.episodeId === undefined ? episodePayload(draft, savedAt) : undefined,
    recurOf: draft.episodeId === undefined ? options.recurOf : undefined,
    entry,
    photos: draft.photos ?? [],
    savedAt: savedAt.toISOString(),
    displayName: options.displayName ?? draft.mainSymptom ?? 'Symptom',
  };
}

/**
 * Saves a draft, queueing it if the phone cannot reach the backend.
 *
 * Resolves whether the save reached the server or was queued; it rejects only
 * when the server refuses the description itself, which is something the user
 * needs to hear about rather than a failure to retry.
 */
export function useSaveSymptom() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);

  return useMutation<
    SaveOutcome,
    unknown,
    { draft: SymptomDraft; displayName?: string; recurOf?: string }
  >({
    mutationFn: ({ draft, displayName, recurOf }) =>
      submitOrQueueEntry(
        profileId ?? '',
        pendingRecordFor(draft, { displayName, recurOf })
      ),
    onSuccess: refresh,
  });
}

export function useUpdateSymptomEntry(episodeId: string) {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);

  return useMutation<
    EntrySaved,
    unknown,
    { entryId: string; patch: Partial<EntryPayload> }
  >({
    mutationFn: ({ entryId, patch }) =>
      updateEntry(profileId ?? '', episodeId, entryId, patch),
    onSuccess: refresh,
  });
}

export function useUpdateSymptomEpisode() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);

  return useMutation({
    mutationFn: ({ episodeId, patch }: { episodeId: string; patch: EpisodePatch }) =>
      updateEpisode(profileId ?? '', episodeId, patch),
    onSuccess: refresh,
  });
}

export function useResolveSymptom() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);

  return useMutation({
    mutationFn: (episodeId: string) => resolveEpisode(profileId ?? '', episodeId),
    onSuccess: refresh,
  });
}

export function useDeleteSymptom() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);

  return useMutation({
    mutationFn: (episodeId: string) => deleteEpisode(profileId ?? '', episodeId),
    onSuccess: refresh,
  });
}

export function useDeleteSymptomPhoto() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      episodeId,
      entryId,
      photoId,
    }: {
      episodeId: string;
      entryId: string;
      photoId: string;
    }) => deletePhoto(profileId ?? '', episodeId, entryId, photoId),
    onSuccess: async (_result, variables) => {
      queryClient.removeQueries({ queryKey: symptomPhotoQueryKey(variables.photoId) });
      await refresh();
    },
  });
}

// --- background work --------------------------------------------------------

/**
 * Sends anything queued: when a symptom screen is focused, and again whenever
 * the phone comes back online (PRD 6, sections 59 and 61).
 */
export function useSyncPendingSymptoms() {
  const profileId = useSymptomProfileId();
  const refresh = useRefreshSymptoms(profileId);
  const authStatus = useAppStore((state) => state.authStatus);

  const sync = useCallback(async () => {
    if (authStatus !== 'authenticated' || profileId === null) return;
    const summary = await syncPendingEntries(profileId);
    if (summary.sent > 0 || summary.discarded > 0) {
      await refresh();
    }
  }, [authStatus, profileId, refresh]);

  useOnReconnect(() => void sync());

  useFocusEffect(
    useCallback(() => {
      void sync();
    }, [sync])
  );

  return sync;
}
