/**
 * The rules the privacy screens enforce (PRD 13, sections 21, 44 and 53).
 *
 * Pure functions, tested directly, for the reason PRD 12 found the hard way:
 * under React 19 with React Native Testing Library 14 a component's own
 * `useState` does not flush from `fireEvent`, so a rule implemented inside a
 * form screen cannot be driven by a test at all.
 *
 * Here that limitation is a gift rather than a nuisance. The phrase check is
 * what stands between a mis-tap and an irreversible delete, and testing it as
 * a function lets the test say what actually matters -- that the comparison is
 * exact -- instead of that one keystroke produced one state.
 */
import {
  canConfirmDeletion,
  canCreateExport,
  phraseMatches,
} from '../src/features/privacy/validation';

const PHRASE = 'DELETE MY NURA DATA';

describe('the confirmation phrase', () => {
  it('matches when typed exactly', () => {
    expect(phraseMatches(PHRASE, PHRASE)).toBe(true);
  });

  it('does not match a different case', () => {
    // Case folding would make the phrase easier to arrive at by accident,
    // which is the one thing it exists to prevent. The server compares it the
    // same way.
    expect(phraseMatches('delete my nura data', PHRASE)).toBe(false);
    expect(phraseMatches('Delete My Nura Data', PHRASE)).toBe(false);
  });

  it('does not match with surrounding whitespace', () => {
    // No trimming. A phrase pasted with a trailing space is a phrase somebody
    // pasted rather than typed.
    expect(phraseMatches(` ${PHRASE}`, PHRASE)).toBe(false);
    expect(phraseMatches(`${PHRASE} `, PHRASE)).toBe(false);
    expect(phraseMatches(`${PHRASE}\n`, PHRASE)).toBe(false);
  });

  it('does not match a partial phrase', () => {
    expect(phraseMatches('DELETE', PHRASE)).toBe(false);
    expect(phraseMatches('DELETE MY NURA', PHRASE)).toBe(false);
    expect(phraseMatches('DELETE MY NURA DATA NOW', PHRASE)).toBe(false);
  });

  it('does not match an empty input', () => {
    expect(phraseMatches('', PHRASE)).toBe(false);
  });

  it('never matches when there is no expected phrase', () => {
    // A response that somehow arrived without one must not unlock the delete.
    expect(phraseMatches('', '')).toBe(false);
    expect(phraseMatches('anything', '')).toBe(false);
  });
});

describe('whether the delete button is available', () => {
  it('needs the phrase to match', () => {
    expect(canConfirmDeletion({ typed: PHRASE, expected: PHRASE, pending: false })).toBe(
      true
    );
    expect(
      canConfirmDeletion({ typed: 'DELETE', expected: PHRASE, pending: false })
    ).toBe(false);
  });

  it('is unavailable while a request is in flight', () => {
    // A second submission of an irreversible action is the one double-tap
    // worth designing against.
    expect(canConfirmDeletion({ typed: PHRASE, expected: PHRASE, pending: true })).toBe(
      false
    );
  });
});

describe('whether an export can be requested', () => {
  it('is available when nothing is waiting', () => {
    expect(canCreateExport({ hasDownloadable: false, pending: false })).toBe(true);
  });

  it('is unavailable while one is already downloadable', () => {
    // Section 53's repeat-export case. Replacing a waiting archive would be
    // worse than refusing: somebody may be part way through downloading it.
    expect(canCreateExport({ hasDownloadable: true, pending: false })).toBe(false);
  });

  it('is unavailable while one is being built', () => {
    expect(canCreateExport({ hasDownloadable: false, pending: true })).toBe(false);
  });
});
