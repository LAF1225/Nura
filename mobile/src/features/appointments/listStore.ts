/**
 * Which appointment list is on screen (PRD 7, section 41).
 *
 * A single piece of UI state, in a store rather than in the screen, for two
 * reasons:
 *
 *   1. **It should survive a trip into an appointment and back.** Somebody
 *      looking through Past who opens one and returns should still be in Past,
 *      not thrown back to Upcoming.
 *   2. **A store update re-renders under React 19 where a local `useState`
 *      update from a fired event does not**, which is what makes the tabs
 *      testable at all in this project -- the same reason the symptom draft and
 *      the report selection live in stores.
 *
 * Not persisted: which list you were reading is a fact about this session, and
 * reopening the app should start where the feature starts.
 */
import { create } from 'zustand';

import type { AppointmentScope } from './types';

interface ListState {
  scope: AppointmentScope;
  setScope: (scope: AppointmentScope) => void;
}

export const useAppointmentListStore = create<ListState>()((set) => ({
  scope: 'upcoming',
  setScope: (scope) => set({ scope }),
}));
