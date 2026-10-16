/**
 * Server state for caregivers, suggestions, messages and contacts (PRD 9).
 *
 * Every query key carries the profile id, for the reason every other feature's
 * does -- and here it matters more than anywhere else. A caregiver may support
 * two people. A cache keyed only by `caregiver-home` would show one person's
 * medications under the other's name, which is exactly what section 57 forbids.
 *
 * Four things are worth reading rather than skimming.
 *
 * **`useCareMode` validates the stored context against the server.** The mode
 * store holds a choice; this hook is what turns it into a usable scope, and it
 * refuses to if the server no longer lists that relationship. A caregiver whose
 * access was revoked while the app was closed comes back to their own Nura, not
 * to a screen full of 404s (section 52).
 *
 * **Switching contexts removes the previous person's cached data rather than
 * refetching over it.** Section 58 says not to briefly show the prior profile's
 * data; an invalidated query keeps serving its old value while it reloads.
 *
 * **A retried message carries the same client id.** So a send that timed out
 * after the server stored it comes back as the message already there, and the
 * app retires one optimistic row rather than showing two (sections 72 and 74).
 *
 * **Nothing here applies a suggestion.** `useApproveSuggestion` is the primary
 * user's mutation and it invalidates the medication and appointment caches,
 * because approval changed real records on the server. A caregiver's hooks have
 * no mutation that writes to either (sections 21 and 64).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useRef } from 'react';

import { useAppStore } from '../../store/appStore';
import { localDateString } from '../../utils/date';
import { useHealthProfileId } from '../health/hooks';
import {
  acceptInvitation,
  approveSuggestion,
  cancelSuggestion,
  createEmergencyContact,
  createInvitation,
  createSuggestion,
  createThread,
  declineInvitation,
  declineSuggestion,
  deleteEmergencyContact,
  fetchCaregiverHome,
  fetchCaregivers,
  fetchCareSummary,
  fetchEmergencyContacts,
  fetchInvitation,
  fetchPermissionCatalogue,
  fetchSuggestions,
  fetchSupportedProfiles,
  fetchThread,
  fetchThreads,
  reorderEmergencyContacts,
  revokeCaregiver,
  sendFamilyMessage,
  startCall,
  updateCaregiverNotifications,
  updateCaregiverPermissions,
  updateCaregiverRole,
  updateEmergencyContact,
} from './api';
import {
  clearProfileScopedQueries,
  SELF_CONTEXT,
  useCareModeStore,
  type CareContext,
} from './modeStore';
import { useMessageDraftStore } from './stores';
import type {
  CallSession,
  Caregiver,
  CaregiverHome,
  CaregiverList,
  CaregiverNotificationKey,
  CaregiverRole,
  CareSummary,
  CheckInCode,
  EmergencyContact,
  EmergencyContactInput,
  EmergencyContactList,
  FamilyMessage,
  FamilyThread,
  FamilyThreadDetail,
  FamilyThreadList,
  InvitationPreview,
  InviteCreated,
  InviteInput,
  OwnerSuggestion,
  Permission,
  PermissionKey,
  Suggestion,
  SuggestionInput,
  SuggestionList,
  SupportedProfile,
} from './types';

// --- keys --------------------------------------------------------------------

export const caregiversKey = (profileId: string, includeInactive: boolean) =>
  ['caregivers', profileId, includeInactive] as const;
export const careSummaryKey = (profileId: string) => ['care-summary', profileId] as const;
export const caregiverHomeKey = (profileId: string) =>
  ['caregiver-home', profileId] as const;
export const supportedProfilesKey = () => ['supported-profiles'] as const;
export const invitationKey = (token: string) => ['caregiver-invitation', token] as const;
export const permissionCatalogueKey = () => ['caregiver-permission-catalogue'] as const;
export const suggestionsKey = (profileId: string, openOnly: boolean) =>
  ['caregiver-suggestions', profileId, openOnly] as const;
export const threadsKey = (profileId: string) => ['family-threads', profileId] as const;
export const threadKey = (profileId: string, threadId: string) =>
  ['family-thread', profileId, threadId] as const;
export const contactsKey = (profileId: string) =>
  ['emergency-contacts', profileId] as const;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

/**
 * The permission categories, with the server's own wording.
 *
 * Not profile-scoped and the same for everybody, so it is cached indefinitely
 * and never cleared on a context switch.
 */
export function usePermissionCatalogue() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<Permission[]>({
    queryKey: permissionCatalogueKey(),
    queryFn: () => fetchPermissionCatalogue(),
    enabled: authStatus === 'authenticated',
    staleTime: Infinity,
  });
}

// --- the account's own profile ----------------------------------------------

/** The profile this account owns. The same one the health record belongs to. */
export const useOwnProfileId = useHealthProfileId;

// --- Caregiver Mode ----------------------------------------------------------

export function useSupportedProfiles() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<SupportedProfile[]>({
    queryKey: supportedProfilesKey(),
    queryFn: () => fetchSupportedProfiles(),
    enabled: authStatus === 'authenticated',
  });
}

export interface CareMode {
  context: CareContext;
  /** The profile every request should be about. Null before anything loads. */
  profileId: string | null;
  /** Null in self mode. */
  relationship: SupportedProfile | null;
  isCaregiverMode: boolean;
  /** The people this account could switch to. */
  supported: SupportedProfile[];
  /** True once the persisted choice has been read back. */
  ready: boolean;
}

/**
 * Which person the app is about, validated against what the server allows.
 *
 * The stored context is a choice, not a credential: if the relationship it names
 * is no longer in `/caregiver/profiles` -- revoked, declined, expired -- this
 * falls back to the account's own Nura rather than pointing every screen at a
 * profile the server will refuse (section 52).
 */
export function useCareMode(): CareMode {
  const stored = useCareModeStore((state) => state.context);
  const hydrated = useCareModeStore((state) => state.hydrated);
  const ownProfileId = useOwnProfileId();
  const supported = useSupportedProfiles();
  const rows = useMemo(() => supported.data ?? [], [supported.data]);

  const relationship = useMemo(() => {
    if (stored.kind !== 'caregiver') return null;
    return (
      rows.find(
        (row) =>
          row.relationshipId === stored.relationshipId &&
          row.profileId === stored.profileId
      ) ?? null
    );
  }, [stored, rows]);

  // Still in caregiver mode only while the server agrees the relationship is
  // there. While the list is loading, the stored choice is honoured: the
  // requests it drives are authorized server-side anyway.
  const stillSupported =
    stored.kind === 'caregiver' && (supported.isPending || relationship !== null);

  return {
    context: stillSupported ? stored : SELF_CONTEXT,
    profileId:
      stillSupported && stored.kind === 'caregiver' ? stored.profileId : ownProfileId,
    relationship,
    isCaregiverMode: stillSupported,
    supported: rows,
    ready: hydrated,
  };
}

/**
 * Switches which person the app is about (sections 16 and 58).
 *
 * Clears the previous person's cached data before changing the context, so no
 * screen renders one person's rows under another's name even for a frame.
 */
export function useSwitchCareContext() {
  const client = useQueryClient();
  const setContext = useCareModeStore((state) => state.setContext);

  return useCallback(
    (context: CareContext) => {
      clearProfileScopedQueries(client);
      setContext(context);
    },
    [client, setContext]
  );
}

// --- the primary user's caregiver list ---------------------------------------

export function useCaregivers(includeInactive = false) {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<CaregiverList>({
    queryKey: caregiversKey(profileId ?? 'none', includeInactive),
    queryFn: () => fetchCaregivers(profileId as string, includeInactive),
    enabled,
  });
}

export function useCareSummary() {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<CareSummary>({
    queryKey: careSummaryKey(profileId ?? 'none'),
    queryFn: () => fetchCareSummary(profileId as string),
    enabled,
  });
}

function useInvalidateCaregivers() {
  const client = useQueryClient();
  const profileId = useOwnProfileId();
  return useCallback(() => {
    if (profileId === null) return;
    void client.invalidateQueries({ queryKey: ['caregivers', profileId] });
    void client.invalidateQueries({ queryKey: careSummaryKey(profileId) });
  }, [client, profileId]);
}

export function useCreateInvitation() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateCaregivers();
  return useMutation<InviteCreated, Error, InviteInput>({
    mutationFn: (input) => createInvitation(profileId as string, input),
    onSuccess: invalidate,
  });
}

export function useUpdateCaregiverRole() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateCaregivers();
  return useMutation<Caregiver, Error, { relationshipId: string; role: CaregiverRole }>({
    mutationFn: ({ relationshipId, role }) =>
      updateCaregiverRole(profileId as string, relationshipId, role),
    onSuccess: invalidate,
  });
}

export function useUpdatePermissions() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateCaregivers();
  return useMutation<
    Caregiver,
    Error,
    { relationshipId: string; permissions: Partial<Record<PermissionKey, boolean>> }
  >({
    mutationFn: ({ relationshipId, permissions }) =>
      updateCaregiverPermissions(profileId as string, relationshipId, permissions),
    onSuccess: invalidate,
  });
}

export function useRevokeCaregiver() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateCaregivers();
  const client = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (relationshipId) => revokeCaregiver(profileId as string, relationshipId),
    onSuccess: () => {
      invalidate();
      // Their thread is no longer reachable, and the supported-profile list on
      // their own phone will drop it on its next read.
      if (profileId !== null) {
        void client.invalidateQueries({ queryKey: threadsKey(profileId) });
      }
      void client.invalidateQueries({ queryKey: supportedProfilesKey() });
    },
  });
}

// --- invitations -------------------------------------------------------------

export function useInvitation(token: string | null) {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<InvitationPreview>({
    queryKey: invitationKey(token ?? 'none'),
    queryFn: () => fetchInvitation(token as string),
    enabled: authStatus === 'authenticated' && token !== null && token.length > 0,
    // An invitation is single-use: a stale cached preview would offer Accept on
    // a token that has already been spent.
    staleTime: 0,
    retry: false,
  });
}

export function useAcceptInvitation() {
  const client = useQueryClient();
  return useMutation<SupportedProfile, Error, string>({
    mutationFn: (token) => acceptInvitation(token),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: supportedProfilesKey() });
    },
  });
}

export function useDeclineInvitation() {
  return useMutation<void, Error, string>({
    mutationFn: (token) => declineInvitation(token),
  });
}

// --- the caregiver's home ----------------------------------------------------

export function useCaregiverHome() {
  const mode = useCareMode();
  const profileId = mode.isCaregiverMode ? mode.profileId : null;
  const enabled = useEnabled(profileId);
  return useQuery<CaregiverHome>({
    queryKey: caregiverHomeKey(profileId ?? 'none'),
    queryFn: () => fetchCaregiverHome(profileId as string, localDateString()),
    enabled,
  });
}

export function useUpdateCaregiverNotifications() {
  const mode = useCareMode();
  const client = useQueryClient();
  return useMutation<
    SupportedProfile,
    Error,
    Partial<Record<CaregiverNotificationKey, boolean>>
  >({
    mutationFn: (notifications) =>
      updateCaregiverNotifications(mode.profileId as string, notifications),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: supportedProfilesKey() });
    },
  });
}

// --- suggestions -------------------------------------------------------------

/**
 * Care requests for whoever is on screen.
 *
 * One hook for both sides, because the server decides what each sees: the owner
 * gets everybody's, a caregiver gets their own (section 66).
 */
export function useSuggestions(openOnly = false) {
  const mode = useCareMode();
  const profileId = mode.profileId;
  const enabled = useEnabled(profileId);
  return useQuery<SuggestionList>({
    queryKey: suggestionsKey(profileId ?? 'none', openOnly),
    queryFn: () => fetchSuggestions(profileId as string, openOnly),
    enabled,
  });
}

function useAfterReview() {
  const client = useQueryClient();
  const profileId = useOwnProfileId();
  return useCallback(() => {
    if (profileId === null) return;
    void client.invalidateQueries({ queryKey: ['caregiver-suggestions', profileId] });
    void client.invalidateQueries({ queryKey: careSummaryKey(profileId) });
    // Approval changed real records through the ordinary services, so the
    // screens that show them are stale.
    void client.invalidateQueries({ queryKey: ['medication-schedules'] });
    void client.invalidateQueries({ queryKey: ['medication-doses'] });
    void client.invalidateQueries({ queryKey: ['appointments'] });
    void client.invalidateQueries({ queryKey: ['appointment-summary'] });
    void client.invalidateQueries({ queryKey: ['today'] });
  }, [client, profileId]);
}

export function useApproveSuggestion() {
  const profileId = useOwnProfileId();
  const after = useAfterReview();
  return useMutation<OwnerSuggestion, Error, string>({
    mutationFn: (suggestionId) => approveSuggestion(profileId as string, suggestionId),
    onSuccess: after,
  });
}

export function useDeclineSuggestion() {
  const profileId = useOwnProfileId();
  const after = useAfterReview();
  return useMutation<
    OwnerSuggestion,
    Error,
    { suggestionId: string; note?: string | null }
  >({
    mutationFn: ({ suggestionId, note }) =>
      declineSuggestion(profileId as string, suggestionId, note),
    onSuccess: after,
  });
}

export function useCreateSuggestion() {
  const mode = useCareMode();
  const client = useQueryClient();
  return useMutation<Suggestion, Error, SuggestionInput>({
    mutationFn: (input) => createSuggestion(mode.profileId as string, input),
    onSuccess: () => {
      if (mode.profileId === null) return;
      void client.invalidateQueries({
        queryKey: ['caregiver-suggestions', mode.profileId],
      });
      void client.invalidateQueries({ queryKey: caregiverHomeKey(mode.profileId) });
    },
  });
}

export function useCancelSuggestion() {
  const mode = useCareMode();
  const client = useQueryClient();
  return useMutation<Suggestion, Error, string>({
    mutationFn: (suggestionId) =>
      cancelSuggestion(mode.profileId as string, suggestionId),
    onSuccess: () => {
      if (mode.profileId === null) return;
      void client.invalidateQueries({
        queryKey: ['caregiver-suggestions', mode.profileId],
      });
    },
  });
}

// --- family messaging --------------------------------------------------------

export function useThreads() {
  const mode = useCareMode();
  const profileId = mode.profileId;
  const enabled = useEnabled(profileId);
  return useQuery<FamilyThreadList>({
    queryKey: threadsKey(profileId ?? 'none'),
    queryFn: () => fetchThreads(profileId as string),
    enabled,
  });
}

export function useThread(threadId: string | null) {
  const mode = useCareMode();
  const profileId = mode.profileId;
  const enabled = useEnabled(profileId) && threadId !== null;
  return useQuery<FamilyThreadDetail>({
    queryKey: threadKey(profileId ?? 'none', threadId ?? 'none'),
    queryFn: () => fetchThread(profileId as string, threadId as string),
    enabled,
  });
}

export function useCreateThread() {
  const mode = useCareMode();
  const client = useQueryClient();
  return useMutation<FamilyThread, Error, string>({
    mutationFn: (relationshipId) =>
      createThread(mode.profileId as string, relationshipId),
    onSuccess: () => {
      if (mode.profileId === null) return;
      void client.invalidateQueries({ queryKey: threadsKey(mode.profileId) });
    },
  });
}

export interface SendMessageInput {
  threadId: string;
  text?: string;
  checkInCode?: CheckInCode;
}

/**
 * Sends one line, keeping its client id across retries (sections 72 and 74).
 *
 * The id is minted before the first attempt and kept in a ref until a send
 * succeeds, so a request that timed out *after* the server stored it comes back
 * as the message already there. That is what lets the thread retire one
 * optimistic row instead of showing the message twice.
 */
export function useSendMessage() {
  const mode = useCareMode();
  const client = useQueryClient();
  const clearDraft = useMessageDraftStore((state) => state.clearDraft);
  const pendingId = useRef<string | null>(null);

  const mutation = useMutation<FamilyMessage, Error, SendMessageInput>({
    mutationFn: ({ threadId, text, checkInCode }) => {
      if (pendingId.current === null) {
        pendingId.current = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      }
      return sendFamilyMessage(mode.profileId as string, threadId, {
        messageType: checkInCode ? 'check_in' : 'text',
        text: text ?? null,
        checkInCode: checkInCode ?? null,
        clientMessageId: pendingId.current,
      });
    },
    onSuccess: (_message, { threadId }) => {
      pendingId.current = null;
      clearDraft(threadId);
      if (mode.profileId === null) return;
      void client.invalidateQueries({ queryKey: threadKey(mode.profileId, threadId) });
      void client.invalidateQueries({ queryKey: threadsKey(mode.profileId) });
      void client.invalidateQueries({ queryKey: caregiverHomeKey(mode.profileId) });
    },
  });

  return mutation;
}

// --- emergency contacts ------------------------------------------------------

export function useEmergencyContacts() {
  const profileId = useOwnProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<EmergencyContactList>({
    queryKey: contactsKey(profileId ?? 'none'),
    queryFn: () => fetchEmergencyContacts(profileId as string),
    enabled,
  });
}

function useInvalidateContacts() {
  const client = useQueryClient();
  const profileId = useOwnProfileId();
  return useCallback(() => {
    if (profileId === null) return;
    void client.invalidateQueries({ queryKey: contactsKey(profileId) });
    void client.invalidateQueries({ queryKey: careSummaryKey(profileId) });
  }, [client, profileId]);
}

export function useCreateContact() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateContacts();
  return useMutation<EmergencyContact, Error, EmergencyContactInput>({
    mutationFn: (input) => createEmergencyContact(profileId as string, input),
    onSuccess: invalidate,
  });
}

export function useUpdateContact() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateContacts();
  return useMutation<
    EmergencyContact,
    Error,
    { contactId: string; input: Partial<EmergencyContactInput> }
  >({
    mutationFn: ({ contactId, input }) =>
      updateEmergencyContact(profileId as string, contactId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteContact() {
  const profileId = useOwnProfileId();
  const invalidate = useInvalidateContacts();
  return useMutation<void, Error, string>({
    mutationFn: (contactId) => deleteEmergencyContact(profileId as string, contactId),
    onSuccess: invalidate,
  });
}

export function useReorderContacts() {
  const profileId = useOwnProfileId();
  const client = useQueryClient();
  return useMutation<EmergencyContactList, Error, string[]>({
    mutationFn: (order) => reorderEmergencyContacts(profileId as string, order),
    onSuccess: (result) => {
      if (profileId === null) return;
      // The server renumbered, so its answer is the order -- written straight
      // into the cache rather than refetched, which is what keeps the list from
      // jumping back to the old order for a frame.
      client.setQueryData(contactsKey(profileId), result);
    },
  });
}

// --- calling -----------------------------------------------------------------

/**
 * Asks for a call, which every deployment refuses (section 38).
 *
 * Here so the one place that changes when a provider arrives is the server. The
 * screens do not offer a Call control while `callingAvailable` is false, and this
 * exists for the case where one is reached anyway -- it surfaces the refusal
 * rather than a ringing screen.
 */
export function useStartCall() {
  const mode = useCareMode();
  return useMutation<CallSession, Error, string>({
    mutationFn: (relationshipId) => startCall(mode.profileId as string, relationshipId),
  });
}
