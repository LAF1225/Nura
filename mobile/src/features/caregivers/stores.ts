/**
 * The small bits of caregiver state the phone keeps (PRD 9, sections 71-73).
 *
 * Three stores, and each exists for a stated reason.
 *
 * `useCareFormStore`  -- the invite form, the permission toggles being edited and
 *                        the contact form. Zustand rather than component state
 *                        for the reason this project keeps rediscovering: a store
 *                        update re-renders under React 19 where a local
 *                        `useState` update from a fired event does not, which is
 *                        what makes a Save button that enables when you type
 *                        something testable at all.
 *
 * `useMessageDraftStore` -- unsent messages, persisted. Section 71 asks for
 *                        message drafts to survive going offline and section 72
 *                        for a message to be `pending` until the backend confirms
 *                        it. What is deliberately *not* here is a send queue: a
 *                        message that went out an hour later without the sender
 *                        knowing is worse than one they resend themselves, and
 *                        `copy.DRAFT_KEPT` says which of the two this is.
 *
 * `useSuggestionDraftStore` -- a suggestion being composed, persisted. Section 73
 *                        allows drafting one offline and is explicit that it must
 *                        **not** be applied locally to the primary user's real
 *                        records. It cannot be: a draft here is a proposed value
 *                        and a target id, and the only thing that can turn one
 *                        into a change is the primary user pressing Approve on
 *                        the server.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { PermissionKey, SuggestionActionType } from './types';

// --- forms -------------------------------------------------------------------

interface CareFormState {
  /** The invite form. */
  invitedName: string;
  inviteContact: string;
  inviteRole: string;
  invitePermissions: Partial<Record<PermissionKey, boolean>>;

  /** The permission screen being edited, keyed by relationship id. */
  editedPermissions: Record<string, Partial<Record<PermissionKey, boolean>>>;

  /** The emergency-contact form. */
  contactName: string;
  contactPhone: string;
  contactRelationship: string;
  contactActive: boolean;

  /** A note being typed while declining a suggestion. */
  declineNote: string;

  /**
   * The relationship whose Remove button has been pressed once.
   *
   * In the store rather than in component state for the reason this project
   * keeps meeting: under React 19 a local `useState` update from a fired event
   * does not re-render, so a two-press confirmation would be untestable -- and an
   * untested confirmation in front of "stop this person seeing anything" is the
   * wrong thing to leave untested.
   */
  confirmingRemoval: string | null;

  /**
   * The reminder change being composed by a caregiver, in the same store and for
   * the same reason. `suggestPause` and `suggestTime` drive which controls show,
   * so a press has to re-render for the screen to be usable at all.
   */
  suggestPause: boolean;
  suggestTime: string | null;

  setInvitedName: (value: string) => void;
  setInviteContact: (value: string) => void;
  setInviteRole: (value: string) => void;
  toggleInvitePermission: (key: PermissionKey) => void;
  resetInvite: () => void;

  setEditedPermission: (
    relationshipId: string,
    key: PermissionKey,
    allowed: boolean
  ) => void;
  clearEditedPermissions: (relationshipId: string) => void;

  setContactName: (value: string) => void;
  setContactPhone: (value: string) => void;
  setContactRelationship: (value: string) => void;
  setContactActive: (value: boolean) => void;
  loadContact: (fields: {
    name: string;
    phone: string;
    relationship: string;
    isActive: boolean;
  }) => void;
  resetContact: () => void;

  setDeclineNote: (value: string) => void;

  setConfirmingRemoval: (relationshipId: string | null) => void;
  setSuggestPause: (value: boolean) => void;
  setSuggestTime: (value: string | null) => void;
  resetSuggestion: () => void;
}

const EMPTY_INVITE = {
  invitedName: '',
  inviteContact: '',
  inviteRole: 'family',
  invitePermissions: {} as Partial<Record<PermissionKey, boolean>>,
};

/**
 * The object a selector returns when a relationship has no edits yet.
 *
 * A module-level constant rather than `?? {}` inline, because a selector that
 * builds a fresh object every render is never referentially equal to the last
 * one -- and Zustand 5 re-renders on inequality, which is an infinite loop
 * rather than a performance note. Found by a screen test hitting React's
 * maximum update depth.
 */
export const NO_EDITED_PERMISSIONS: Partial<Record<PermissionKey, boolean>> = {};

const EMPTY_CONTACT = {
  contactName: '',
  contactPhone: '',
  contactRelationship: '',
  contactActive: true,
};

export const useCareFormStore = create<CareFormState>()((set) => ({
  ...EMPTY_INVITE,
  ...EMPTY_CONTACT,
  editedPermissions: {},
  declineNote: '',
  confirmingRemoval: null,
  suggestPause: false,
  suggestTime: null,

  setInvitedName: (value) => set({ invitedName: value }),
  setInviteContact: (value) => set({ inviteContact: value }),
  setInviteRole: (value) => set({ inviteRole: value }),
  toggleInvitePermission: (key) =>
    set((state) => ({
      invitePermissions: {
        ...state.invitePermissions,
        [key]: !state.invitePermissions[key],
      },
    })),
  resetInvite: () => set({ ...EMPTY_INVITE }),

  setEditedPermission: (relationshipId, key, allowed) =>
    set((state) => ({
      editedPermissions: {
        ...state.editedPermissions,
        [relationshipId]: {
          ...(state.editedPermissions[relationshipId] ?? {}),
          [key]: allowed,
        },
      },
    })),
  clearEditedPermissions: (relationshipId) =>
    set((state) => {
      const { [relationshipId]: _saved, ...rest } = state.editedPermissions;
      return { editedPermissions: rest };
    }),

  setContactName: (value) => set({ contactName: value }),
  setContactPhone: (value) => set({ contactPhone: value }),
  setContactRelationship: (value) => set({ contactRelationship: value }),
  setContactActive: (value) => set({ contactActive: value }),
  loadContact: (fields) =>
    set({
      contactName: fields.name,
      contactPhone: fields.phone,
      contactRelationship: fields.relationship,
      contactActive: fields.isActive,
    }),
  resetContact: () => set({ ...EMPTY_CONTACT }),

  setDeclineNote: (value) => set({ declineNote: value }),

  setConfirmingRemoval: (relationshipId) => set({ confirmingRemoval: relationshipId }),
  setSuggestPause: (value) => set({ suggestPause: value }),
  setSuggestTime: (value) => set({ suggestTime: value }),
  resetSuggestion: () => set({ suggestPause: false, suggestTime: null }),
}));

// --- message drafts ----------------------------------------------------------

interface MessageDraftState {
  /** Thread id -> the text typed but not sent. */
  drafts: Record<string, string>;
  hydrated: boolean;

  setDraft: (threadId: string, text: string) => void;
  clearDraft: (threadId: string) => void;
}

export const useMessageDraftStore = create<MessageDraftState>()(
  persist(
    (set) => ({
      drafts: {},
      hydrated: false,

      setDraft: (threadId, text) =>
        set((state) => ({ drafts: { ...state.drafts, [threadId]: text } })),
      clearDraft: (threadId) =>
        set((state) => {
          const { [threadId]: _sent, ...rest } = state.drafts;
          return { drafts: rest };
        }),
    }),
    {
      name: 'nura-family-drafts',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({ drafts: state.drafts }),
      onRehydrateStorage: () => () => {
        useMessageDraftStore.setState({ hydrated: true });
      },
    }
  )
);

export function useMessageDraft(threadId: string): string {
  return useMessageDraftStore((state) => state.drafts[threadId] ?? '');
}

// --- suggestion drafts -------------------------------------------------------

export interface SuggestionDraft {
  actionType: SuggestionActionType;
  targetResourceId: string | null;
  /**
   * What is being proposed, in the action's own shape. Never applied locally
   * (section 73): the only thing that turns one of these into a change is the
   * primary user pressing Approve, on the server.
   */
  payload: Record<string, unknown>;
  /** Minted before the first attempt, so a retry is not a second request. */
  clientSuggestionId: string;
}

interface SuggestionDraftState {
  /** Profile id -> the suggestion being composed for that person. */
  drafts: Record<string, SuggestionDraft>;
  hydrated: boolean;

  setDraft: (profileId: string, draft: SuggestionDraft) => void;
  clearDraft: (profileId: string) => void;
}

export const useSuggestionDraftStore = create<SuggestionDraftState>()(
  persist(
    (set) => ({
      drafts: {},
      hydrated: false,

      setDraft: (profileId, draft) =>
        set((state) => ({ drafts: { ...state.drafts, [profileId]: draft } })),
      clearDraft: (profileId) =>
        set((state) => {
          const { [profileId]: _sent, ...rest } = state.drafts;
          return { drafts: rest };
        }),
    }),
    {
      name: 'nura-care-suggestion-drafts',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({ drafts: state.drafts }),
      onRehydrateStorage: () => () => {
        useSuggestionDraftStore.setState({ hydrated: true });
      },
    }
  )
);
