/**
 * Server state for the Nura assistant (PRD 8, sections 8, 55 and 89).
 *
 * Every query key carries the profile id, for the same reason the health
 * record, medication, symptom and appointment keys do: an account can hold
 * more than one profile, and a cache keyed only by "conversations" would
 * happily show one person's thread under another's name.
 *
 * Three things here are worth reading rather than skimming.
 *
 * **`useSendMessage` resolves on a failure.** A provider that could not be
 * reached is a 201 with `reply: null` and a `failure` code, not a rejection:
 * the user's message *was* recorded, and the screen needs to show it with a
 * Retry rather than an error page (section 55).
 *
 * **A retry carries the same client id.** So a message that timed out and is
 * sent again is answered rather than recorded twice. The id is generated
 * before the first attempt and kept until one succeeds.
 *
 * **Nothing here queues.** Section 56 is explicit that there must be no fake
 * assistant reply, and a queued message whose answer arrives an hour later,
 * out of context, is a worse version of the same problem. The draft is kept;
 * the send is not retried in the background.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef } from 'react';

import { useAppStore } from '../../store/appStore';
import { localDateString } from '../../utils/date';
import { useHealthProfileId } from '../health/hooks';
import {
  confirmAction,
  createConversation,
  createMemory,
  deleteConversation,
  deleteMemory,
  dismissPrompt,
  fetchConversation,
  fetchConversations,
  fetchHome,
  fetchMemories,
  fetchPreferences,
  sendMessage,
  updateConversation,
  updateMemory,
  updatePreferences,
} from './api';
import { useComposerStore } from './composerStore';
import type {
  ActionConfirmed,
  AssistantHome,
  Conversation,
  ConversationDetail,
  ConversationList,
  Memory,
  MemoryCategory,
  MemoryList,
  MemorySource,
  MessageSent,
  Preferences,
  PreferencesPatch,
  PromptKind,
} from './types';

/**
 * Whose assistant this is.
 *
 * The same person the health record belongs to. A conversation is about that
 * person's own care, so it cannot be about anybody else (PRD 8, section 60).
 */
export const useAssistantProfileId = useHealthProfileId;

export const assistantHomeKey = (profileId: string) =>
  ['assistant-home', profileId] as const;
export const conversationsKey = (profileId: string, archived: boolean) =>
  ['assistant-conversations', profileId, archived] as const;
export const conversationKey = (profileId: string, conversationId: string) =>
  ['assistant-conversation', profileId, conversationId] as const;
export const preferencesKey = (profileId: string) =>
  ['assistant-preferences', profileId] as const;
export const memoriesKey = (profileId: string) =>
  ['assistant-memories', profileId] as const;

function useEnabled(profileId: string | null): boolean {
  const authStatus = useAppStore((state) => state.authStatus);
  return authStatus === 'authenticated' && profileId !== null;
}

// --- reading ----------------------------------------------------------------

export function useAssistantHome() {
  const profileId = useAssistantProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<AssistantHome>({
    queryKey: assistantHomeKey(profileId ?? 'none'),
    queryFn: () => fetchHome(profileId as string, localDateString()),
    enabled,
  });
}

export function useConversations(includeArchived = false) {
  const profileId = useAssistantProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<ConversationList>({
    queryKey: conversationsKey(profileId ?? 'none', includeArchived),
    queryFn: () => fetchConversations(profileId as string, includeArchived),
    enabled,
  });
}

export function useConversation(conversationId: string | null) {
  const profileId = useAssistantProfileId();
  const enabled = useEnabled(profileId) && conversationId !== null;
  return useQuery<ConversationDetail>({
    queryKey: conversationKey(profileId ?? 'none', conversationId ?? 'none'),
    queryFn: () => fetchConversation(profileId as string, conversationId as string),
    enabled,
  });
}

export function useAssistantPreferences() {
  const profileId = useAssistantProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<Preferences>({
    queryKey: preferencesKey(profileId ?? 'none'),
    queryFn: () => fetchPreferences(profileId as string),
    enabled,
  });
}

export function useMemories() {
  const profileId = useAssistantProfileId();
  const enabled = useEnabled(profileId);
  return useQuery<MemoryList>({
    queryKey: memoriesKey(profileId ?? 'none'),
    queryFn: () => fetchMemories(profileId as string),
    enabled,
  });
}

// --- writing ----------------------------------------------------------------

export function useUpdatePreferences() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<Preferences, Error, PreferencesPatch>({
    mutationFn: (patch) => updatePreferences(profileId as string, patch),
    onSuccess: (preferences) => {
      // Written straight into the cache as well as invalidated: a dial that
      // snaps back for a moment while a refetch lands reads as a control that
      // did not work.
      queryClient.setQueryData(preferencesKey(profileId as string), preferences);
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

export function useStartConversation() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<Conversation, Error, void>({
    mutationFn: () => createConversation(profileId as string),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['assistant-conversations', profileId],
      });
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

export function useUpdateConversation(conversationId: string) {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<Conversation, Error, { title?: string; archived?: boolean }>({
    mutationFn: (patch) => updateConversation(profileId as string, conversationId, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ['assistant-conversations', profileId],
      });
      void queryClient.invalidateQueries({
        queryKey: conversationKey(profileId as string, conversationId),
      });
    },
  });
}

export function useDeleteConversation() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  const forget = useComposerStore((state) => state.forget);
  return useMutation<void, Error, string>({
    mutationFn: (conversationId) =>
      deleteConversation(profileId as string, conversationId),
    onSuccess: (_result, conversationId) => {
      // The draft goes with the thread. A half-written message reappearing
      // under a conversation the user deleted would be startling.
      forget(conversationId);
      void queryClient.invalidateQueries({
        queryKey: ['assistant-conversations', profileId],
      });
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

export function useAddMemory() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<
    Memory,
    Error,
    { content: string; category: MemoryCategory; source?: MemorySource }
  >({
    mutationFn: (input) => createMemory(profileId as string, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: memoriesKey(profileId as string),
      });
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

export function useUpdateMemory() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<
    Memory,
    Error,
    { id: string; content?: string; category?: MemoryCategory; isActive?: boolean }
  >({
    mutationFn: ({ id, ...patch }) => updateMemory(profileId as string, id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: memoriesKey(profileId as string),
      });
    },
  });
}

export function useRemoveMemory() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (memoryId) => deleteMemory(profileId as string, memoryId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: memoriesKey(profileId as string),
      });
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

export function useDismissPrompt() {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<void, Error, { kind: PromptKind; subjectKey: string }>({
    mutationFn: ({ kind, subjectKey }) =>
      dismissPrompt(profileId as string, kind, subjectKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });
}

// --- talking ----------------------------------------------------------------

/**
 * Sends one message, keeping the client id stable across retries.
 *
 * The id is minted on the first attempt and kept in a ref until a send comes
 * back with a reply. A retry after a timeout therefore carries the id the
 * backend already stored the question under, so it is *answered* rather than
 * asked again (PRD 8, section 55).
 */
export function useSendMessage(conversationId: string) {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  const pendingId = useRef<string | null>(null);

  const mutation = useMutation<MessageSent, Error, string>({
    mutationFn: (content) => {
      if (pendingId.current === null) {
        pendingId.current = newClientId();
      }
      return sendMessage(profileId as string, conversationId, {
        content,
        clientMessageId: pendingId.current,
        localDate: localDateString(),
      });
    },
    onSuccess: (result) => {
      // Only a real reply retires the id. A failure leaves it in place so the
      // next attempt is a retry of the same question.
      if (result.reply !== null) {
        pendingId.current = null;
      }
      void queryClient.invalidateQueries({
        queryKey: conversationKey(profileId as string, conversationId),
      });
      void queryClient.invalidateQueries({
        queryKey: ['assistant-conversations', profileId],
      });
      void queryClient.invalidateQueries({
        queryKey: assistantHomeKey(profileId as string),
      });
    },
  });

  const reset = useCallback(() => {
    pendingId.current = null;
    mutation.reset();
  }, [mutation]);

  return { ...mutation, reset };
}

export function useConfirmAction(conversationId: string) {
  const profileId = useAssistantProfileId();
  const queryClient = useQueryClient();
  return useMutation<ActionConfirmed, Error, { messageId: string; confirmed: boolean }>({
    mutationFn: ({ messageId, confirmed }) =>
      confirmAction(
        profileId as string,
        conversationId,
        messageId,
        confirmed,
        localDateString()
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: conversationKey(profileId as string, conversationId),
      });
      // A confirmed write changes an appointment, so the screens that show
      // one need to hear about it.
      void queryClient.invalidateQueries({ queryKey: ['appointment'] });
      void queryClient.invalidateQueries({ queryKey: ['appointments'] });
    },
  });
}

/** A client id for one message. Generated before the first attempt. */
export function newClientId(): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `msg-${Date.now().toString(36)}-${random}`;
}
