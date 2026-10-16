/**
 * Unsent messages, held on the phone (PRD 8, sections 56 and 57).
 *
 * Section 57 asks for a long message not to be lost when the app backgrounds,
 * and section 56 asks for the draft to survive being offline. Both are the
 * same requirement: what somebody typed belongs to them until it has been
 * sent, so it goes to AsyncStorage and comes back.
 *
 * Kept per conversation. Two threads open in a day is normal, and a single
 * shared draft would put a half-written question about medication into a
 * conversation about something else.
 *
 * Zustand rather than component state for the second reason this project keeps
 * finding: a store update re-renders under React 19 where a local `useState`
 * update from a fired event does not, which is what makes the composer
 * testable at all. The same decision PRD 6 made for the symptom draft and
 * PRD 7 for the appointment form.
 *
 * What this is **not**: a send queue. A message cannot be sent later, because
 * the reply comes from a model the phone cannot reach, and section 56 forbids
 * pretending otherwise. The text is kept; nothing is promised about it.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

interface ComposerState {
  /** Conversation id -> the text typed but not sent. */
  drafts: Record<string, string>;
  /** False until the persisted drafts have been read back from disk. */
  hydrated: boolean;

  setDraft: (conversationId: string, text: string) => void;
  clearDraft: (conversationId: string) => void;
  /** Used when a conversation is deleted, so its draft does not outlive it. */
  forget: (conversationId: string) => void;
}

export const useComposerStore = create<ComposerState>()(
  persist(
    (set) => ({
      drafts: {},
      hydrated: false,

      setDraft: (conversationId, text) =>
        set((state) => ({ drafts: { ...state.drafts, [conversationId]: text } })),

      clearDraft: (conversationId) =>
        set((state) => {
          const { [conversationId]: _sent, ...rest } = state.drafts;
          return { drafts: rest };
        }),

      forget: (conversationId) =>
        set((state) => {
          const { [conversationId]: _gone, ...rest } = state.drafts;
          return { drafts: rest };
        }),
    }),
    {
      name: 'nura-assistant-composer',
      storage: createJSONStorage(() => AsyncStorage),
      /** Only the drafts reach disk -- not the hydration flag. */
      partialize: (state) => ({ drafts: state.drafts }),
      onRehydrateStorage: () => () => {
        useComposerStore.setState({ hydrated: true });
      },
    }
  )
);

/** The text waiting in one conversation's composer. */
export function useDraft(conversationId: string): string {
  return useComposerStore((state) => state.drafts[conversationId] ?? '');
}

/** Whether there is anything unsent anywhere, for a "you have a draft" hint. */
export function useHasDrafts(): boolean {
  return useComposerStore((state) =>
    Object.values(state.drafts).some((text) => text.trim().length > 0)
  );
}
