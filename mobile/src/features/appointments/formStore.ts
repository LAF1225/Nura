/**
 * The in-progress appointment form, held on the phone (PRD 7, sections 8 and 53).
 *
 * Zustand rather than component state, for three reasons that all matter:
 *
 *   1. **PRD 7 section 53 asks for appointment drafts to be preserved.** This is
 *      written to AsyncStorage, so somebody interrupted half-way through typing
 *      an appointment comes back to it.
 *   2. **One store serves both the new and the edit form.** They collect the same
 *      fields and validate the same way, so they cannot disagree about what a
 *      valid appointment is.
 *   3. **A store update re-renders under React 19 where a local `useState`
 *      update from a fired event does not** -- which is what makes the form
 *      testable at all in this project. The same decision PRD 6 made for the
 *      symptom draft, for the same reason.
 *
 * What it deliberately is *not*: an appointment. Nothing here has been sent
 * anywhere until the user presses Save.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { draftFrom, newDraft } from './draft';
import type { Appointment, AppointmentDraft, AppointmentType } from './types';

interface FormState {
  /** Null when no appointment is part-way through being written. */
  draft: AppointmentDraft | null;
  /** Set when the draft edits an existing appointment rather than adding one. */
  editingId: string | null;
  /** False until the persisted draft has been read back from disk. */
  hydrated: boolean;

  /** Begins a new appointment, or resumes the one already in progress. */
  startNew: () => void;
  /** Begins editing, replacing whatever was in progress. */
  startEdit: (appointment: Appointment) => void;
  patch: (fields: Partial<AppointmentDraft>) => void;
  setType: (appointmentType: AppointmentType) => void;
  setClinician: (clinicianId: string | null) => void;
  clear: () => void;
}

export const useAppointmentFormStore = create<FormState>()(
  persist(
    (set, get) => ({
      draft: null,
      editingId: null,
      hydrated: false,

      startNew: () => {
        const { draft, editingId } = get();
        // Resume only a draft that is also a new appointment: coming back to Add
        // after editing something else should not show that appointment's fields.
        if (draft !== null && editingId === null) return;
        set({ draft: newDraft(), editingId: null });
      },

      startEdit: (appointment) => {
        if (get().editingId === appointment.id) return;
        set({ draft: draftFrom(appointment), editingId: appointment.id });
      },

      patch: (fields) =>
        set((state) =>
          state.draft === null ? state : { draft: { ...state.draft, ...fields } }
        ),

      setType: (appointmentType) =>
        set((state) =>
          state.draft === null ? state : { draft: { ...state.draft, appointmentType } }
        ),

      setClinician: (clinicianId) =>
        set((state) =>
          state.draft === null ? state : { draft: { ...state.draft, clinicianId } }
        ),

      clear: () => set({ draft: null, editingId: null }),
    }),
    {
      name: 'nura-appointment-form',
      storage: createJSONStorage(() => AsyncStorage),
      /** Only the draft itself reaches disk -- not the hydration flag. */
      partialize: (state) => ({ draft: state.draft, editingId: state.editingId }),
      onRehydrateStorage: () => () => {
        useAppointmentFormStore.setState({ hydrated: true });
      },
    }
  )
);

/** True when there is an appointment part-way through being written. */
export function useHasAppointmentDraft(): boolean {
  return useAppointmentFormStore((state) => state.draft !== null);
}
