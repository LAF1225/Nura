/**
 * Server state for the health record (PRD 4, sections 25 and 36).
 *
 * Health data hangs off a profile, so every query key carries the profile id.
 * That is not decoration: an account can hold more than one profile, and a
 * cache keyed only by section would happily show one person's records under
 * another's name.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useAccount } from '../../hooks/useOnboarding';
import { useAppStore } from '../../store/appStore';
import {
  createRecord,
  deleteRecord,
  fetchHealthSetup,
  fetchHealthSummary,
  fetchRecords,
  updateHealthSetup,
  updateRecord,
  type HealthSetupPatch,
} from './api';
import type { HealthRecord, HealthSetup, HealthSummary, SectionSpec } from './types';

export const healthSummaryQueryKey = (profileId: string) =>
  ['health', 'summary', profileId] as const;
export const healthSetupQueryKey = (profileId: string) =>
  ['health', 'setup', profileId] as const;
export const healthRecordsQueryKey = (profileId: string, section: string) =>
  ['health', 'records', profileId, section] as const;

/**
 * Whose health record this is.
 *
 * The person Nura is for, which in assisted setup is not the account holder.
 * This mirrors the server's own choice, so the app and the backend always mean
 * the same person (PRD 4, section 8).
 */
export function useHealthProfileId(): string | null {
  const account = useAccount();
  const profiles = account.data?.profiles ?? [];
  const chosen =
    profiles.find((profile) => profile.role === 'setup_helper') ??
    profiles.find((profile) => profile.role === 'self') ??
    profiles[0];
  return chosen?.id ?? null;
}

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

export function useHealthSummary() {
  const profileId = useHealthProfileId();
  const enabled = useEnabled(profileId);

  const query = useQuery<HealthSummary>({
    queryKey: healthSummaryQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchHealthSummary(profileId ?? '', signal),
    enabled,
  });

  return { ...query, profileId };
}

export function useHealthSetup() {
  const profileId = useHealthProfileId();
  const enabled = useEnabled(profileId);

  return useQuery<HealthSetup>({
    queryKey: healthSetupQueryKey(profileId ?? ''),
    queryFn: ({ signal }) => fetchHealthSetup(profileId ?? '', signal),
    enabled,
  });
}

export function useHealthRecords(spec: SectionSpec) {
  const profileId = useHealthProfileId();
  const enabled = useEnabled(profileId);

  const query = useQuery<HealthRecord[]>({
    queryKey: healthRecordsQueryKey(profileId ?? '', spec.key),
    queryFn: ({ signal }) => fetchRecords(profileId ?? '', spec, signal),
    enabled,
  });

  return { ...query, profileId };
}

/** Invalidates the section's list and the summary, which counts it. */
function useRefreshSection(profileId: string | null, section: string) {
  const queryClient = useQueryClient();
  return async () => {
    if (profileId === null) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: healthRecordsQueryKey(profileId, section),
      }),
      queryClient.invalidateQueries({ queryKey: healthSummaryQueryKey(profileId) }),
      queryClient.invalidateQueries({ queryKey: healthSetupQueryKey(profileId) }),
    ]);
  };
}

export function useSaveRecord(spec: SectionSpec) {
  const profileId = useHealthProfileId();
  const refresh = useRefreshSection(profileId, spec.key);

  return useMutation({
    mutationFn: ({
      recordId,
      payload,
    }: {
      /** Absent for a new record. */
      recordId?: string;
      payload: Record<string, unknown>;
    }) =>
      recordId
        ? updateRecord(profileId ?? '', spec, recordId, payload)
        : createRecord(profileId ?? '', spec, payload),
    onSuccess: refresh,
  });
}

export function useDeleteRecord(spec: SectionSpec) {
  const profileId = useHealthProfileId();
  const refresh = useRefreshSection(profileId, spec.key);

  return useMutation({
    mutationFn: (recordId: string) => deleteRecord(profileId ?? '', spec, recordId),
    onSuccess: refresh,
  });
}

export function useUpdateHealthSetup() {
  const profileId = useHealthProfileId();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (patch: HealthSetupPatch) => updateHealthSetup(profileId ?? '', patch),
    onSuccess: async (setup) => {
      if (profileId === null) return;
      // The server's answer goes straight into the cache, so the screen does
      // not flicker back to the previous value while a refetch lands.
      queryClient.setQueryData(healthSetupQueryKey(profileId), setup);
      await queryClient.invalidateQueries({
        queryKey: healthSummaryQueryKey(profileId),
      });
    },
  });
}
