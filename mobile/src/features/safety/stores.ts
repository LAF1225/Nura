/**
 * Interactive state for the safety screens, in a store rather than in a screen.
 *
 * The reason is the one that keeps recurring in this project: under React 19
 * with the testing library, a local `useState` update from a fired event does
 * not re-render, so anything that decides what is on screen and has to be
 * *tested* lives here instead. That is not a workaround -- it is why the
 * Remove confirmation in PRD 9 ended up legible, and the same applies here to
 * controls that start or stop an emergency.
 *
 * Two shapes of state:
 *
 * **Draft monitoring settings.** What the Start screen has selected before
 * anything is sent. The server decides when monitoring ends (section 61); this
 * only holds what the person picked.
 *
 * **Confirmation steps.** Section 13 wants an accidental SOS to be hard, and
 * sections 45 and 62 want cancelling and stopping to be deliberate. Each is a
 * two-step flow, and the second step names what it will do rather than
 * repeating the first button's label -- the PRD 9 lesson about two presses of
 * "Remove" giving no feedback.
 *
 * A selector that built a new object every render would be an infinite loop
 * under Zustand 5, so nothing here is selected as a fresh object.
 */
import { create } from 'zustand';

import { DEFAULT_TIMEOUT } from './copy';
import type { DurationMode, FalsePositiveReason, ResponseTimeout } from './types';

/** Which two-step flow, if any, is waiting for its second press. */
export type SafetyConfirm = 'none' | 'sos' | 'cancel' | 'stop_with_event';

interface SafetyFormState {
  durationMode: DurationMode;
  responseTimeout: ResponseTimeout;
  secondPrompt: boolean;
  confirming: SafetyConfirm;
  /** The false-alarm answer being composed, per event. */
  falseAlarmReason: FalsePositiveReason | null;

  setDurationMode: (mode: DurationMode) => void;
  setResponseTimeout: (seconds: ResponseTimeout) => void;
  setSecondPrompt: (enabled: boolean) => void;
  confirm: (step: SafetyConfirm) => void;
  setFalseAlarmReason: (reason: FalsePositiveReason | null) => void;
  reset: () => void;
}

const INITIAL = {
  durationMode: '1_hour' as DurationMode,
  responseTimeout: DEFAULT_TIMEOUT,
  secondPrompt: false,
  confirming: 'none' as SafetyConfirm,
  falseAlarmReason: null,
};

export const useSafetyFormStore = create<SafetyFormState>((set) => ({
  ...INITIAL,
  setDurationMode: (durationMode) => set({ durationMode }),
  setResponseTimeout: (responseTimeout) => set({ responseTimeout }),
  setSecondPrompt: (secondPrompt) => set({ secondPrompt }),
  confirm: (confirming) => set({ confirming }),
  setFalseAlarmReason: (falseAlarmReason) => set({ falseAlarmReason }),
  reset: () => set({ ...INITIAL }),
}));
