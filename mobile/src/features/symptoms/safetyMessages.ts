/**
 * Every sentence Nura may say back about a symptom (PRD 6, sections 42-46, 77).
 *
 * Its own file, with no logic in it, because PRD 6 section 45 asks for exactly
 * that: reviewed safety wording kept apart from symptom code, so somebody
 * clinical or legal can read and change all of it without touching a screen.
 *
 * Three rules hold over everything in here.
 *
 * **Nothing names a condition, a cause or a likelihood.** No "this sounds
 * like", no "probably", no "caused by". A test asserts it
 * (PRD 6, section 81).
 *
 * **Nothing tells anyone what to do about their medication**, and nothing
 * claims urgency Nura has not been told about (sections 43 and 82).
 *
 * **The server's wording wins.** When a response carries
 * `safety.notice`, that is what is shown -- these constants mirror the reviewed
 * text in `backend/app/services/symptoms/safety.py` so an *offline* save can
 * still say the right thing. If the two ever diverge, the backend is correct.
 */

/**
 * Shown when the user has recorded a symptom as worsening.
 *
 * Mirrors `WORSENING_NOTICE` on the backend. States what was recorded and
 * leaves the decision with the person (PRD 6, sections 42 and 77).
 */
export const WORSENING_NOTICE =
  'You have recorded this as worsening. If it keeps getting worse, becomes ' +
  'severe, or is affecting what you can normally do, consider contacting a ' +
  'healthcare professional.';

/**
 * How Nura checks a concerning statement it is not sure about
 * (PRD 6, section 46). Asked before anything follows from it, and a "no"
 * records the phrase as denied rather than leaving it as a maybe.
 */
export function confirmationPrompt(term: string): string {
  return `Just to confirm: are you saying you have ${term} right now?`;
}

/** What Nura says whenever a photo is attached (PRD 6, section 32). */
export const PHOTO_NOTICE =
  'Nura stores your photos for your own records. It does not look at them.';

/**
 * The one line on the symptom screens that comes close to advice, and it points
 * at a person rather than giving any (PRD 6, sections 3 and 81).
 */
export const NOT_ADVICE =
  'Nura records what you describe so you can share it. It does not work out ' +
  'what is causing it.';

/** Shown above the guided conversation, so nobody expects a diagnosis. */
export const GUIDED_INTRO =
  'A few short questions, in your own words. You can skip anything, and you ' +
  'will see everything before it is saved.';

/** Shown when a symptom has been tracked for a while, from the server. */
export const PERSISTENT_NOTICE =
  'You have been recording this for a while. It may be worth mentioning at ' +
  'your next appointment.';
