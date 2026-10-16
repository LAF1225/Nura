/**
 * What the user chose to put in a report, held on the phone (PRD 7, ss25, 32, 53).
 *
 * Zustand rather than component state, for three reasons that all matter:
 *
 *   1. **The selection outlives the screen.** Review, choose, preview and export
 *      are four routes editing one thing, and a selection in component state
 *      would be lost on every navigation -- including on the Back that PRD 7
 *      section 32 explicitly requires to work.
 *   2. **It survives the app being closed.** PRD 7 section 53 asks for drafts to
 *      be preserved where practical, so this is written to AsyncStorage. Somebody
 *      interrupted half-way through preparing comes back to their choices.
 *   3. **Nothing is locked.** Every switch can be changed and the report
 *      regenerated, which is section 32's requirement, and a single store makes
 *      "go back and change it" a state change rather than a re-derivation.
 *
 * What it deliberately is *not*: a report. Nothing here has been sent anywhere.
 * The report exists only once the user presses Generate, and it is the backend
 * that freezes the content (PRD 7, section 30).
 *
 * One selection at a time, keyed by appointment. Starting on a different
 * appointment replaces it: preparing for two visits at once is not a thing
 * anybody does, and remembering several would mean a store that never empties.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { REPORT_SECTION_KEYS } from './api';
import type { ReportPeriodPreset, ReportSectionKey, ReportSelection } from './types';

/** Every section on except medical notes, matching the server's own default. */
export function defaultInclude(): Record<ReportSectionKey, boolean> {
  const include = {} as Record<ReportSectionKey, boolean>;
  for (const key of REPORT_SECTION_KEYS) {
    include[key] = key !== 'medical_notes';
  }
  return include;
}

export function emptySelection(): ReportSelection {
  return {
    include: defaultInclude(),
    symptomEpisodeIds: [],
    symptomNoteEntryIds: [],
    medicationIds: null,
    checkinNoteDates: [],
    medicalNoteIds: [],
    focus: null,
    includeAppendix: false,
    includeSkipReasonNotes: false,
  };
}

function toggleIn(values: string[], value: string): string[] {
  return values.includes(value)
    ? values.filter((entry) => entry !== value)
    : [...values, value];
}

interface SelectionState {
  /** Null when nothing is part-way through being prepared. */
  appointmentId: string | null;
  preset: ReportPeriodPreset;
  customStart: string | null;
  customEnd: string | null;
  selection: ReportSelection;
  /** False until the persisted selection has been read back from disk. */
  hydrated: boolean;

  /**
   * Begins preparing, or resumes if this is the same appointment.
   *
   * ``defaults`` is the server's own default selection -- every section, every
   * symptom in the review -- which is what a first visit to the screen starts
   * from (PRD 7, section 25).
   */
  start: (appointmentId: string, defaults?: ReportSelection) => void;
  /** Replaces the selection wholesale, e.g. from a report being regenerated. */
  load: (appointmentId: string, selection: ReportSelection) => void;
  setPreset: (preset: ReportPeriodPreset) => void;
  setCustomRange: (start: string | null, end: string | null) => void;
  toggleSection: (key: ReportSectionKey) => void;
  toggleSymptom: (episodeId: string) => void;
  setSymptoms: (episodeIds: string[]) => void;
  toggleSymptomNote: (entryId: string) => void;
  /**
   * Turns one medication on or off.
   *
   * ``allIds`` is every medication in the review, needed because null means "the
   * active ones": unticking one has to turn the implicit list into an explicit
   * one first, or the server would still include it.
   */
  toggleMedication: (medicationId: string, allIds: string[]) => void;
  toggleCheckinNote: (date: string) => void;
  toggleMedicalNote: (noteId: string) => void;
  setAppendix: (value: boolean) => void;
  setSkipReasonNotes: (value: boolean) => void;
  setFocus: (value: string) => void;
  clear: () => void;
}

export const useReportSelectionStore = create<SelectionState>()(
  persist(
    (set, get) => ({
      appointmentId: null,
      preset: 'since_last_visit',
      customStart: null,
      customEnd: null,
      selection: emptySelection(),
      hydrated: false,

      start: (appointmentId, defaults) => {
        if (get().appointmentId === appointmentId) return;
        set({
          appointmentId,
          preset: 'since_last_visit',
          customStart: null,
          customEnd: null,
          selection: defaults ?? emptySelection(),
        });
      },

      load: (appointmentId, selection) =>
        set({ appointmentId, selection: { ...selection } }),

      setPreset: (preset) => set({ preset }),

      setCustomRange: (customStart, customEnd) =>
        set({ preset: 'custom', customStart, customEnd }),

      toggleSection: (key) =>
        set((state) => ({
          selection: {
            ...state.selection,
            include: {
              ...state.selection.include,
              [key]: !state.selection.include[key],
            },
          },
        })),

      toggleSymptom: (episodeId) =>
        set((state) => ({
          selection: {
            ...state.selection,
            symptomEpisodeIds: toggleIn(state.selection.symptomEpisodeIds, episodeId),
          },
        })),

      setSymptoms: (episodeIds) =>
        set((state) => ({
          selection: { ...state.selection, symptomEpisodeIds: [...episodeIds] },
        })),

      toggleSymptomNote: (entryId) =>
        set((state) => ({
          selection: {
            ...state.selection,
            symptomNoteEntryIds: toggleIn(state.selection.symptomNoteEntryIds, entryId),
          },
        })),

      toggleMedication: (medicationId, allIds) =>
        set((state) => {
          const current = state.selection.medicationIds ?? [...allIds];
          return {
            selection: {
              ...state.selection,
              medicationIds: toggleIn(current, medicationId),
            },
          };
        }),

      toggleCheckinNote: (date) =>
        set((state) => ({
          selection: {
            ...state.selection,
            checkinNoteDates: toggleIn(state.selection.checkinNoteDates, date),
          },
        })),

      toggleMedicalNote: (noteId) =>
        set((state) => ({
          selection: {
            ...state.selection,
            medicalNoteIds: toggleIn(state.selection.medicalNoteIds, noteId),
            // Attaching a note has to switch the section on, or a ticked note
            // would quietly not appear.
            include: { ...state.selection.include, medical_notes: true },
          },
        })),

      setAppendix: (value) =>
        set((state) => ({
          selection: { ...state.selection, includeAppendix: value },
        })),

      setSkipReasonNotes: (value) =>
        set((state) => ({
          selection: { ...state.selection, includeSkipReasonNotes: value },
        })),

      setFocus: (value) =>
        set((state) => ({
          selection: {
            ...state.selection,
            focus: value.trim().length === 0 ? null : value,
          },
        })),

      clear: () =>
        set({
          appointmentId: null,
          preset: 'since_last_visit',
          customStart: null,
          customEnd: null,
          selection: emptySelection(),
        }),
    }),
    {
      name: 'nura-report-selection',
      storage: createJSONStorage(() => AsyncStorage),
      /** Only the choices reach disk -- not the hydration flag. */
      partialize: (state) => ({
        appointmentId: state.appointmentId,
        preset: state.preset,
        customStart: state.customStart,
        customEnd: state.customEnd,
        selection: state.selection,
      }),
      onRehydrateStorage: () => () => {
        useReportSelectionStore.setState({ hydrated: true });
      },
    }
  )
);

/** Whether a medication is in the selection, honouring null as "all active". */
export function isMedicationSelected(
  selection: ReportSelection,
  medicationId: string
): boolean {
  return (
    selection.medicationIds === null || selection.medicationIds.includes(medicationId)
  );
}

/** How many sections are switched on, for the "3 of 9 included" line. */
export function selectedSectionCount(selection: ReportSelection): number {
  return Object.values(selection.include).filter(Boolean).length;
}
