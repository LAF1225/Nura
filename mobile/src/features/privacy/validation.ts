/**
 * The rules the privacy screens enforce, as pure functions (PRD 13, ss21, 44).
 *
 * **Pure because they have to be testable.** PRD 12 found that under React 19
 * with React Native Testing Library 14, a component's own `useState` does not
 * flush from `fireEvent` -- so a rule implemented inside a form screen cannot
 * be driven by a test at all. The response then was to extract the daily-life
 * validation, and the same applies here with more at stake: the phrase check
 * is the thing standing between a mis-tap and an irreversible delete, so it is
 * the last rule in the app that should be untested.
 */

/**
 * Whether what somebody typed is the confirmation phrase.
 *
 * Compared **exactly**: no trimming, no case folding, no collapsing of
 * whitespace. Every one of those would make the check easier to pass by
 * accident, and the point of the phrase is to be hard to arrive at by
 * accident. The server compares it the same way and is the one that decides;
 * this is only what enables the button.
 *
 * An empty expected phrase never matches, so a response that somehow arrived
 * without one cannot unlock the delete.
 */
export function phraseMatches(typed: string, expected: string): boolean {
  if (expected.length === 0) return false;
  return typed === expected;
}

/**
 * Whether the delete button should be available.
 *
 * Both halves, named rather than inlined, so the reason a button is disabled
 * is readable: the phrase matches, and nothing is already in flight. A second
 * submission of an irreversible action is the one double-tap worth designing
 * against.
 */
export function canConfirmDeletion(options: {
  typed: string;
  expected: string;
  pending: boolean;
}): boolean {
  return !options.pending && phraseMatches(options.typed, options.expected);
}

/**
 * Whether an export can be requested.
 *
 * One at a time (PRD 13, section 53's repeat-export case). The server refuses
 * a second and names the one that exists; this stops the screen offering
 * something it knows will be refused.
 */
export function canCreateExport(options: {
  hasDownloadable: boolean;
  pending: boolean;
}): boolean {
  return !options.pending && !options.hasDownloadable;
}
