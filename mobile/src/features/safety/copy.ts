/**
 * Every safety sentence the app writes for itself, in one module (PRD 10, §120).
 *
 * Section 120 asks for this by name, and says why: it is the discipline that
 * caught three inline sentences during PRD 9's copy audit. `tests/safetyCopy`
 * reads every string here and checks the rules hold.
 *
 * **What is *not* here.** Anything describing what happened or what was tried
 * comes from the server -- the event labels, the escalation lines, the
 * standing warnings. One module writes the prose that could make a claim, and
 * it is `backend/app/services/safety/wording.py`. This file holds titles,
 * button labels and the confirm dialogs: the words that are about the app
 * rather than about somebody's emergency.
 *
 * **Three rules, each with a test.** Nothing here states a medical cause
 * (section 52). Nothing here claims anybody was reached (sections 38 and 42).
 * Nothing here guarantees a response (section 72).
 */
import type { DurationMode, FalsePositiveReason, ResponseTimeout } from './types';

export const SAFETY_TITLE = 'Safety';
export const SAFETY_SUBTITLE =
  'Safety Monitoring, emergency requests and what Nura can actually do.';

export const MONITORING_TITLE = 'Safety Monitoring';
export const START_MONITORING = 'Start monitoring';
export const STOP_MONITORING = 'Stop monitoring';
export const MONITORING_OFF_HINT =
  'Nura only checks on you while this is on. You choose how long for.';

export const DURATION_TITLE = 'Monitor for';
export const TIMEOUT_TITLE = 'How long to wait for your answer';
export const TIMEOUT_HINT =
  'If something happens, Nura asks whether you are okay and waits this long.';
export const SECOND_PROMPT_TITLE = 'Ask a second time';
export const SECOND_PROMPT_HINT =
  'Nura asks once more, waits 20 seconds, then starts escalation.';

export const BEDTIME_TITLE = 'Bedtime';
export const BEDTIME_HINT =
  'Nura does not work your bedtime out from anything. Set one here to use "Until bedtime".';
export const BEDTIME_MISSING =
  'Set a bedtime first, so Nura knows when "Until bedtime" ends.';

/** Section 5's locked presets, in the order the screen offers them. */
export const DURATION_LABELS: Record<DurationMode, string> = {
  '30_minutes': '30 minutes',
  '1_hour': '1 hour',
  until_bedtime: 'Until bedtime',
  until_turned_off: 'Until turned off',
  custom: 'A set time',
};

export const DURATION_ORDER: readonly DurationMode[] = [
  '30_minutes',
  '1_hour',
  'until_bedtime',
  'until_turned_off',
];

/** Section 7's options, with its default first in the selector's order. */
export const TIMEOUT_OPTIONS: readonly ResponseTimeout[] = [15, 30, 45, 60, 90];
export const DEFAULT_TIMEOUT: ResponseTimeout = 45;

export function timeoutLabel(seconds: number): string {
  return `${seconds} seconds`;
}

// --- SOS (sections 12, 13 and 45) -------------------------------------------

export const SOS_TITLE = 'Emergency';
export const SOS_BUTTON = 'Ask for help';
export const SOS_CONFIRM_TITLE = 'Ask for help now?';
/**
 * Section 13 wants protection against an accidental press, and section 42
 * wants the consequence stated truthfully rather than optimistically. Both in
 * two sentences: what will happen, and what will not.
 */
export const SOS_CONFIRM_BODY =
  'Nura will record an emergency request and create an in-app alert for any caregiver who can see safety alerts. It cannot call or text anyone.';
export const SOS_CONFIRM = 'Yes, ask for help';
export const SOS_KEEP = 'Not now';

export const CANCEL_TITLE = 'Cancel emergency request?';
export const CANCEL_BODY =
  'This stops anything that has not been sent yet. Alerts that already exist stay where they are.';
export const CANCEL_CONFIRM = 'Cancel request';
export const CANCEL_KEEP = 'Keep it active';

export const STOP_WITH_EVENT_TITLE = 'There is an emergency request in progress';
export const STOP_WITH_EVENT_BODY =
  'Stopping monitoring does not cancel it. Nura will keep showing it until you say you are okay or cancel it.';
export const STOP_WITH_EVENT_CONFIRM = 'Stop monitoring anyway';

// --- the check-in (sections 23, 25 and 26) ----------------------------------

export const CHECK_TITLE = 'Are you okay?';
export const CHECK_OKAY = 'I’m okay';
export const CHECK_HELP = 'I need help';
export const CHECK_FALSE_ALARM = 'Dismiss — false alarm';
export const CHECK_COUNTDOWN_PREFIX = 'Waiting for your answer:';
/** Section 118: a countdown in words, never only an animation. */
export function countdownSentence(seconds: number): string {
  if (seconds <= 0) return 'Time is up. Nura is starting escalation.';
  if (seconds === 1) return `${CHECK_COUNTDOWN_PREFIX} 1 second left.`;
  return `${CHECK_COUNTDOWN_PREFIX} ${seconds} seconds left.`;
}

export const EMERGENCY_TITLE = 'Emergency request';
export const EMERGENCY_SUBTITLE = 'What Nura has done so far.';
export const EMERGENCY_IM_OKAY = 'I’m okay now';
export const EMERGENCY_ACKNOWLEDGED =
  'Nura has stopped anything that had not been sent. What was already recorded stays in the history.';

// --- false alarms (sections 47 and 48) --------------------------------------

export const FALSE_ALARM_TITLE = 'Was this a false alarm?';
export const FALSE_ALARM_YES = 'Yes';
export const FALSE_ALARM_NO = 'No, or not sure';
export const FALSE_ALARM_REASON_TITLE = 'What happened?';
export const FALSE_ALARM_REASONS: Record<FalsePositiveReason, string> = {
  normal_movement: 'Normal movement',
  sensor_error: 'Something was misread',
  user_testing: 'I was testing it',
  other: 'Something else',
};
export const FALSE_ALARM_NOTE =
  'This is only a label on this event. Nothing is trained on it.';

// --- history and detail (sections 49 and 51) --------------------------------

export const HISTORY_TITLE = 'Safety history';
export const HISTORY_EMPTY = 'Nothing has happened yet.';
export const EVENT_TITLE = 'Safety event';
export const ESCALATION_TITLE = 'What Nura did';
export const ESCALATION_EMPTY = 'Nothing was sent.';
export const ALERT_COUNT_NONE = 'No caregiver alerts were created.';
export function alertCountSentence(count: number): string {
  if (count === 0) return ALERT_COUNT_NONE;
  if (count === 1) return 'An in-app alert was created for 1 caregiver.';
  return `In-app alerts were created for ${count} caregivers.`;
}

// --- capabilities (sections 64 and 106) -------------------------------------

export const CAPABILITIES_TITLE = 'What Nura can do';
export const CAPABILITIES_SUBTITLE =
  'This is the actual state of this build, not a list of features.';

// --- offline and degraded (sections 67 and 70) ------------------------------

export const OFFLINE_TITLE = 'No connection';
/**
 * Section 67: detect offline, say so prominently, and do not claim server
 * escalation occurred. The second sentence is what makes it useful rather
 * than only honest.
 */
export const OFFLINE_BODY =
  'Nura cannot reach the server right now, so it cannot record or send an emergency request. Call someone directly from your phone.';
export const DEGRADED_BODY =
  'Nura is having trouble reaching the server. Safety Monitoring may not work until the connection comes back.';

/** Section 68. Said next to a number, so nobody reads it as Nura calling. */
export const DIALER_TITLE = 'Call someone yourself';
export const DIALER_NOTE =
  'This opens your phone’s dialler. Nura does not place the call.';
export function dialerLabel(name: string): string {
  return `Call ${name}`;
}

export const CONTACTS_LINK = 'Emergency contacts';
export const CONTACTS_HINT = 'Who Nura would try to reach, and in what order.';

// --- caregiver alerts (sections 83, 84 and 97) ------------------------------

export const ALERTS_TITLE = 'Safety alerts';
export const ALERTS_EMPTY = 'No safety alerts.';
export const ALERTS_SUBTITLE =
  'Alerts Nura created for you. An alert is a record, not proof anybody was reached.';
export const ACKNOWLEDGE = 'I’m checking on them';
export const ACKNOWLEDGED = 'You said you were checking on them.';
export const ACKNOWLEDGE_NOTE =
  'This records that you are checking. It does not resolve the event.';

export function unreadAlertsSentence(count: number): string {
  if (count === 0) return 'No new safety alerts.';
  if (count === 1) return '1 new safety alert.';
  return `${count} new safety alerts.`;
}

// --- the Care tab card ------------------------------------------------------

export const CARE_CARD_TITLE = 'Safety';
export function careCardSentence(monitoringOn: boolean, contactCount: number): string {
  const monitoring = monitoringOn
    ? 'Safety Monitoring is on.'
    : 'Safety Monitoring is off.';
  if (contactCount === 0) return `${monitoring} No emergency contacts yet.`;
  if (contactCount === 1) return `${monitoring} 1 emergency contact.`;
  return `${monitoring} ${contactCount} emergency contacts.`;
}
