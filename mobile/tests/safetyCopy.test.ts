/**
 * The safety copy audit (PRD 10, sections 38, 42, 52, 72 and 120).
 *
 * Section 120 asks for all safety wording in one reviewable module, and this
 * is what that buys: three rules checked against *every* string the app can
 * produce, rather than against the ones somebody remembered to look at.
 *
 * The rules are the PRD's own, and each quotes the thing it forbids.
 *
 * - Section 52: no definitive label. "seizure detected", "fall confirmed",
 *   "vomiting detected", "unconscious".
 * - Sections 38 and 42: no claim anybody was reached. "Caregiver notified",
 *   "Ayesha has been contacted".
 * - Section 72: no guarantee of emergency response.
 *
 * The backend has the same audit over its own wording module
 * (`tests/test_safety.py::TestNeutralWording`), because the sentences that
 * describe what happened are written there -- this covers the ones the app
 * writes for itself.
 */
import * as copy from '../src/features/safety/copy';

function sentences(): string[] {
  const out: string[] = [];
  for (const value of Object.values(copy)) {
    if (typeof value === 'string') out.push(value);
    else if (typeof value === 'function') {
      // The functions that build a sentence, driven at their edges.
      if (value === copy.countdownSentence) {
        out.push(
          copy.countdownSentence(0),
          copy.countdownSentence(1),
          copy.countdownSentence(45)
        );
      } else if (value === copy.alertCountSentence) {
        out.push(
          copy.alertCountSentence(0),
          copy.alertCountSentence(1),
          copy.alertCountSentence(3)
        );
      } else if (value === copy.unreadAlertsSentence) {
        out.push(
          copy.unreadAlertsSentence(0),
          copy.unreadAlertsSentence(1),
          copy.unreadAlertsSentence(4)
        );
      } else if (value === copy.careCardSentence) {
        out.push(
          copy.careCardSentence(false, 0),
          copy.careCardSentence(true, 1),
          copy.careCardSentence(true, 3)
        );
      } else if (value === copy.timeoutLabel) {
        out.push(copy.timeoutLabel(45));
      } else if (value === copy.dialerLabel) {
        out.push(copy.dialerLabel('Ayesha'));
      }
    } else if (value !== null && typeof value === 'object') {
      for (const entry of Object.values(value)) {
        if (typeof entry === 'string') out.push(entry);
      }
    }
  }
  return out;
}

const ALL = sentences();

it('has something to audit', () => {
  // A guard on the guard: if the module were refactored into a shape this
  // collector missed, every assertion below would pass vacuously.
  expect(ALL.length).toBeGreaterThan(40);
});

it.each([
  [/seizure detected/i, 'section 52'],
  [/fall confirmed/i, 'section 52'],
  [/vomiting detected/i, 'section 52'],
  [/\bunconscious\b/i, 'section 52'],
  [/lost consciousness/i, 'section 52'],
  [/\bdiagnos/i, 'section 52'],
  [/caregiver notified/i, 'section 38'],
  [/has been contacted/i, 'section 42'],
  [/have been notified/i, 'section 42'],
  [/help is on the way/i, 'section 72'],
  [/\bguarantee/i, 'section 72'],
  [/emergency services have been/i, 'section 72'],
])('never says %s (%s)', (pattern) => {
  expect(ALL.filter((sentence) => pattern.test(sentence))).toEqual([]);
});

it('says what pressing SOS will and will not do (sections 13 and 42)', () => {
  expect(copy.SOS_CONFIRM_BODY).toMatch(/record an emergency request/i);
  expect(copy.SOS_CONFIRM_BODY).toMatch(/cannot call or text anyone/i);
});

it('says monitoring is the user’s choice (section 4)', () => {
  expect(copy.MONITORING_OFF_HINT).toMatch(/only checks on you while this is on/i);
  expect(copy.MONITORING_OFF_HINT).toMatch(/You choose how long/i);
});

it('states the second prompt’s timing rather than implying it (section 8)', () => {
  expect(copy.SECOND_PROMPT_HINT).toMatch(/20 seconds/);
});

it('says Nura does not work out a bedtime (section 6)', () => {
  expect(copy.BEDTIME_HINT).toMatch(/does not work your bedtime out/i);
});

it('says cancelling does not recall what already went (section 45)', () => {
  expect(copy.CANCEL_BODY).toMatch(/has not been sent yet/i);
  expect(copy.CANCEL_BODY).toMatch(/already exist stay/i);
});

it('says the dialler is the phone’s, not Nura’s (section 68)', () => {
  expect(copy.DIALER_NOTE).toMatch(/Nura does not place the call/i);
});

it('says offline means nothing can be recorded, and what to do (section 67)', () => {
  expect(copy.OFFLINE_BODY).toMatch(/cannot reach the server/i);
  expect(copy.OFFLINE_BODY).toMatch(/Call someone directly/i);
});

it('says an acknowledgement is not a resolution (section 125)', () => {
  expect(copy.ACKNOWLEDGE_NOTE).toMatch(/does not resolve the event/i);
});

it('says a false-alarm label trains nothing (section 48)', () => {
  expect(copy.FALSE_ALARM_NOTE).toMatch(/Nothing is trained on it/i);
});

it('offers both false-alarm answers, so silence is not a claim (section 48)', () => {
  expect(copy.FALSE_ALARM_YES).toBe('Yes');
  expect(copy.FALSE_ALARM_NO).toMatch(/not sure/i);
});

it('counts down in words (section 118)', () => {
  expect(copy.countdownSentence(45)).toMatch(/45 seconds left/);
  expect(copy.countdownSentence(1)).toMatch(/1 second left/);
  // And says what happens next rather than only that time ran out.
  expect(copy.countdownSentence(0)).toMatch(/starting escalation/i);
});

it('offers exactly section 5’s durations and section 7’s timeouts', () => {
  expect(copy.DURATION_ORDER).toEqual([
    '30_minutes',
    '1_hour',
    'until_bedtime',
    'until_turned_off',
  ]);
  expect(copy.TIMEOUT_OPTIONS).toEqual([15, 30, 45, 60, 90]);
  expect(copy.DEFAULT_TIMEOUT).toBe(45);
});
