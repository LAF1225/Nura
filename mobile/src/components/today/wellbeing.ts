/**
 * How the three wellbeing answers are presented (PRD 3, sections 9 and 45).
 *
 * Text is always present. An icon sits beside it, never instead of it: an
 * emoji alone is ambiguous, unreadable to a screen reader, and means different
 * things to different people.
 *
 * Nothing here interprets an answer. "Not great" produces the same calm
 * acknowledgement as "Good"; Nura does not diagnose, escalate or advise
 * (PRD 3, section 45).
 */
import type { Ionicons } from '@expo/vector-icons';

import type { WellbeingLevel } from '../../types/today';

export interface WellbeingOption {
  level: WellbeingLevel;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
}

/** In this order, always: best to worst reads naturally and never moves. */
export const WELLBEING_OPTIONS: readonly WellbeingOption[] = [
  { level: 'good', label: 'Good', icon: 'sunny-outline' },
  { level: 'okay', label: 'Okay', icon: 'partly-sunny-outline' },
  { level: 'not_great', label: 'Not great', icon: 'cloudy-outline' },
];

export function wellbeingLabel(level: WellbeingLevel): string {
  return WELLBEING_OPTIONS.find((option) => option.level === level)?.label ?? 'Okay';
}

/**
 * What the card says once someone has checked in.
 *
 * A pending answer says so plainly, because "saved on this phone" and "saved"
 * are different promises and the user is entitled to know which one they have
 * (PRD 3, sections 26 and 27).
 */
export function checkInSentence(level: WellbeingLevel, pending: boolean): string {
  const answer = `You checked in as “${wellbeingLabel(level)}” today.`;
  return pending ? `${answer} Saved on this phone.` : answer;
}
