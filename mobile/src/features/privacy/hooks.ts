/**
 * Server state for the privacy layer (PRD 13, sections 4, 17-22, 45).
 *
 * **The hub is one query.** Section 4 gathers caregivers, memory counts,
 * capability states and the export state onto one screen, and a screen that
 * assembled those from six requests would show somebody a half-answer about
 * who can see their data while the rest arrived. One request, one loading
 * state.
 *
 * **It does not poll.** Nothing on this screen changes on its own; it changes
 * because the person changed it, and a refetch on focus is enough.
 *
 * **Deletion is deliberately two mutations.** `useRequestDeletion` is a read
 * that returns what would go, and `useConfirmDeletion` is the irreversible
 * one. They are separate hooks rather than one with a flag, so a screen cannot
 * reach the second by passing a different argument to the first.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useOwnProfileId } from '../caregivers/hooks';
import {
  confirmDeletion,
  createExport,
  deleteAllConversations,
  deleteExport,
  fetchExports,
  fetchPrivacySummary,
  requestDeletion,
} from './api';
import type {
  ConversationsDeleted,
  DataExport,
  DeletionInventory,
  DeletionResult,
  ExportList,
  PrivacySummary,
} from './types';

export const privacySummaryKey = (profileId: string) =>
  ['privacy-summary', profileId] as const;
export const privacyExportsKey = (profileId: string) =>
  ['privacy-exports', profileId] as const;
export const privacyDeletionInventoryKey = (profileId: string) =>
  ['privacy-deletion-inventory', profileId] as const;

/** Everything the Privacy & Security hub shows. */
export function usePrivacySummary() {
  const profileId = useOwnProfileId();
  return useQuery<PrivacySummary>({
    queryKey: privacySummaryKey(profileId ?? 'none'),
    queryFn: () => fetchPrivacySummary(profileId as string),
    enabled: profileId !== null,
  });
}

export function useExports() {
  const profileId = useOwnProfileId();
  return useQuery<ExportList>({
    queryKey: privacyExportsKey(profileId ?? 'none'),
    queryFn: () => fetchExports(profileId as string),
    enabled: profileId !== null,
  });
}

export function useCreateExport() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<DataExport, Error, void>({
    mutationFn: () => createExport(profileId as string),
    onSuccess: () => {
      if (profileId === null) return;
      // Both keys: the list it belongs to, and the hub that shows the latest.
      void client.invalidateQueries({ queryKey: privacyExportsKey(profileId) });
      void client.invalidateQueries({ queryKey: privacySummaryKey(profileId) });
    },
  });
}

export function useDeleteExport() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (exportId) => deleteExport(profileId as string, exportId),
    onSuccess: () => {
      if (profileId === null) return;
      void client.invalidateQueries({ queryKey: privacyExportsKey(profileId) });
      void client.invalidateQueries({ queryKey: privacySummaryKey(profileId) });
    },
  });
}

export function useDeleteAllConversations() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<ConversationsDeleted, Error, void>({
    mutationFn: () => deleteAllConversations(profileId as string),
    onSuccess: () => {
      if (profileId === null) return;
      // The conversation list and its detail keys, plus the hub's count.
      void client.invalidateQueries({ queryKey: ['assistant-conversations'] });
      void client.invalidateQueries({ queryKey: ['assistant-conversation'] });
      void client.invalidateQueries({ queryKey: ['assistant-home'] });
      void client.invalidateQueries({ queryKey: privacySummaryKey(profileId) });
    },
  });
}

/** What a delete would remove. Changes nothing. */
export function useRequestDeletion() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<DeletionInventory, Error, void>({
    mutationFn: () => requestDeletion(profileId as string),
    onSuccess: (inventory) => {
      if (profileId === null) return;
      // Cached so the confirmation screen can read it back without asking
      // again -- the counts somebody agreed to are the counts they saw.
      client.setQueryData(privacyDeletionInventoryKey(profileId), inventory);
    },
  });
}

/**
 * The irreversible one.
 *
 * On success the whole cache goes, not a list of keys: the profile this app
 * was showing no longer exists, so every query about it would 404 and every
 * cached answer is about something that is gone. `clear()` is the honest
 * response to that, and it is what leaves the app in the state a fresh
 * sign-in would be in.
 */
export function useConfirmDeletion() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<DeletionResult, Error, string>({
    mutationFn: (confirmationPhrase) =>
      confirmDeletion(profileId as string, confirmationPhrase),
    onSuccess: () => {
      client.clear();
    },
  });
}
