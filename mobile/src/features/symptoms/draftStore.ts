/**
 * The in-progress symptom draft, held on the phone (PRD 6, sections 29, 59, 67).
 *
 * Zustand rather than component state, for three reasons that all matter:
 *
 *   1. **The draft outlives the screen.** The manual form, the guided
 *      conversation and the review screen are three routes editing one thing, and
 *      a draft in component state would be lost on every navigation.
 *   2. **It survives the app being closed.** PRD 6 section 59 requires a draft
 *      to persist locally, so this is written to AsyncStorage. Somebody who
 *      starts describing a symptom and is interrupted comes back to it.
 *   3. **Nothing is locked.** Every answer can be changed from the review
 *      screen, which is section 67's requirement, and a single store is what
 *      makes "go back and edit" a state change rather than a re-derivation.
 *
 * What it deliberately is *not*: a record. Nothing here has been sent anywhere.
 * PRD 6 section 29 forbids persisting an incomplete draft as a medical record,
 * and this is on the device only until the user presses Save.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { localDateString } from '../../utils/date';
import {
  answer as answerConversation,
  choose as chooseConversation,
  finish as finishConversation,
  startConversation,
} from './conversation/engine';
import { newDraft, withoutPhoto, withPhoto } from './draft';
import type {
  ConversationChoice,
  ConversationState,
  LocalPhotoDraft,
  SymptomDraft,
  SymptomSourceInput,
} from './types';

interface StartOptions {
  /** Set for a follow-up on an existing episode. */
  episodeId?: string;
  /** The episode's name, so a follow-up can be worded about it. */
  episodeName?: string;
  /**
   * The resolved episode this draft follows, when the user has said a symptom
   * has come back. Kept beside the draft rather than in it: it changes where the
   * save goes, not what is being described (PRD 6, section 38).
   */
  recurOf?: string;
}

interface SymptomDraftState {
  /** Null when nothing is part-way through being written. */
  draft: SymptomDraft | null;
  /** Null for the manual flow, which has no conversation. */
  conversation: ConversationState | null;
  episodeName: string | null;
  /** Set when this draft is a recurrence of a resolved episode. */
  recurOf: string | null;
  /** False until the persisted draft has been read back from disk. */
  hydrated: boolean;

  start: (mode: SymptomSourceInput, options?: StartOptions) => void;
  /**
   * Names the symptom a follow-up is about, once it is known.
   *
   * A follow-up screen starts its draft as soon as it is focused, which can be
   * before the episode has loaded -- so the name arrives second, and the review
   * screen needs it to head the summary with the symptom rather than "Update".
   */
  setEpisodeName: (name: string) => void;
  /** Applies whatever the user just changed, from either flow. */
  patch: (values: Partial<SymptomDraft>) => void;
  addPhoto: (photo: LocalPhotoDraft) => void;
  removePhoto: (clientPhotoId: string) => void;
  /** The user typed a message in the guided flow. */
  say: (message: string) => void;
  /** The user tapped one of the offered answers. */
  tap: (choice: ConversationChoice) => void;
  /** Ends the conversation early and goes to the review screen. */
  endConversation: () => void;
  clear: () => void;
}

export const useSymptomDraftStore = create<SymptomDraftState>()(
  persist(
    (set, get) => ({
      draft: null,
      conversation: null,
      episodeName: null,
      recurOf: null,
      hydrated: false,

      start: (mode, options = {}) => {
        const draft = newDraft({ mode, episodeId: options.episodeId });
        set({
          draft,
          episodeName: options.episodeName ?? null,
          recurOf: options.recurOf ?? null,
          conversation:
            mode === 'guided_app'
              ? startConversation(draft, { episodeName: options.episodeName })
              : null,
        });
      },

      setEpisodeName: (name) => {
        if (get().episodeName === name) return;
        set({ episodeName: name });
      },

      patch: (values) => {
        const current = get().draft;
        if (current === null) return;
        set({ draft: { ...current, ...values } });
      },

      addPhoto: (photo) => {
        const current = get().draft;
        if (current === null) return;
        set({ draft: { ...current, photos: withPhoto(current, photo) } });
      },

      removePhoto: (clientPhotoId) => {
        const current = get().draft;
        if (current === null) return;
        set({ draft: { ...current, photos: withoutPhoto(current, clientPhotoId) } });
      },

      say: (message) => {
        const { draft, conversation } = get();
        if (draft === null || conversation === null) return;
        const next = answerConversation(conversation, draft, message, {
          today: localDateString(),
        });
        set({ draft: next.draft, conversation: next.state });
      },

      tap: (choice) => {
        const { draft, conversation } = get();
        if (draft === null || conversation === null) return;
        const next = chooseConversation(conversation, draft, choice, {
          today: localDateString(),
        });
        set({ draft: next.draft, conversation: next.state });
      },

      endConversation: () => {
        const { conversation } = get();
        if (conversation === null) return;
        set({ conversation: finishConversation(conversation) });
      },

      clear: () =>
        set({ draft: null, conversation: null, episodeName: null, recurOf: null }),
    }),
    {
      name: 'nura-symptom-draft',
      storage: createJSONStorage(() => AsyncStorage),
      /** Only the draft itself reaches disk -- not the hydration flag. */
      partialize: (state) => ({
        draft: state.draft,
        conversation: state.conversation,
        episodeName: state.episodeName,
        recurOf: state.recurOf,
      }),
      onRehydrateStorage: () => () => {
        useSymptomDraftStore.setState({ hydrated: true });
      },
    }
  )
);

/** True when there is something part-way through being written. */
export function useHasSymptomDraft(): boolean {
  return useSymptomDraftStore((state) => state.draft !== null);
}
