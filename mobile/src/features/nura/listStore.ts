/**
 * Whether the history list is showing archived threads (PRD 8, section 8).
 *
 * Not persisted: coming back to the app should show the threads you are
 * actually using, not whatever you were sorting out last time.
 *
 * A store rather than `useState` for the reason that keeps recurring in this
 * project: a store update re-renders under React 19 where a local `useState`
 * update from a fired event does not, which is what makes the toggle
 * testable. The same decision PRD 7 made for the appointment scope tabs, in
 * `features/appointments/listStore.ts`.
 */
import { create } from 'zustand';

interface HistoryListState {
  showArchived: boolean;
  setShowArchived: (showArchived: boolean) => void;
}

export const useHistoryListStore = create<HistoryListState>()((set) => ({
  showArchived: false,
  setShowArchived: (showArchived) => set({ showArchived }),
}));
