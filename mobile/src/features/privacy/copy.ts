/**
 * The words the privacy screens use that are *not* the server's (PRD 13).
 *
 * The division matters and is the same one PRD 10, 11 and 12 use. Anything
 * that makes a claim about what Nura can reach, what it stores or what it
 * cannot do comes from the server, because a truthfulness claim with two
 * sources eventually has two meanings -- so there is no privacy-mode sentence
 * here, no capability sentence, no deletion warning and no export note. What
 * is here is navigation: row titles, button labels, and the headings a screen
 * needs to lay the server's answers out.
 *
 * A test asserts the division: every string in this file is checked against
 * the same patterns PRD 10's and PRD 12's copy tests use, and separately
 * against the rule that nothing here promises a capability.
 */

export const HUB_TITLE = 'Privacy & Security';
export const HUB_INTRO = 'What Nura stores, who can see it, and what you can take away.';

/** Section 4's rows, in order, as navigation rather than as claims. */
export const ROW_PRIVACY_MODE = 'Privacy Mode';
export const ROW_CAMERA_MIC = 'Camera & microphone';
export const ROW_MEMORY = 'What Nura remembers';
export const ROW_CONVERSATIONS = 'Conversation history';
export const ROW_CAREGIVERS = 'Caregiver access';
export const ROW_SAFETY = 'Safety Monitoring';
export const ROW_ROBOT = 'Nura Device privacy';
export const ROW_EXPORT = 'Export your data';
export const ROW_DELETE = 'Delete your data';
export const ROW_SECURITY = 'Security status';

export const SECTION_WHAT_NURA_STORES = 'What Nura stores';
export const SECTION_WHO_CAN_SEE = 'Who can see it';
export const SECTION_WHAT_NURA_CAN_REACH = 'What Nura can reach';
export const SECTION_YOUR_DATA = 'Your data';
export const SECTION_SECURITY = 'How this is protected';

/** Counts, as a person reads them. */
export function memorySummary(active: number, total: number): string {
  if (total === 0) return 'Nothing remembered yet';
  if (active === total) return `${total} ${total === 1 ? 'item' : 'items'}`;
  return `${active} of ${total} in use`;
}

export function conversationSummary(count: number): string {
  if (count === 0) return 'No conversations yet';
  return `${count} ${count === 1 ? 'conversation' : 'conversations'}`;
}

export function caregiverSummary(count: number): string {
  if (count === 0) return 'Nobody else has access';
  return `${count} ${count === 1 ? 'person' : 'people'}`;
}

/** Whether a robot is linked at all, which is not the same as "off". */
export const NO_ROBOT_LINKED = 'No Nura Device is linked to this profile.';

// --- export ------------------------------------------------------------------

export const EXPORT_TITLE = 'Export your data';
export const EXPORT_BUTTON = 'Create an export';
export const EXPORT_BUSY = 'Preparing your export…';
export const EXPORT_DOWNLOAD = 'Download';
export const EXPORT_DELETE = 'Delete this export';
export const EXPORT_NONE = 'You have not exported anything yet.';
export const EXPORT_WHAT_IS_INCLUDED = 'What is included';
export const EXPORT_ONE_AT_A_TIME =
  'You can keep one export at a time. Delete this one to make another.';

export function exportSize(bytes: number | null): string | null {
  if (bytes === null) return null;
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function exportFiles(count: number): string {
  return `${count} ${count === 1 ? 'file' : 'files'}`;
}

// --- deletion ----------------------------------------------------------------

export const DELETE_TITLE = 'Delete your data';
export const DELETE_START = 'Continue';
export const DELETE_CONFIRM = 'Delete everything';
export const DELETE_CANCEL = 'Keep my data';
export const DELETE_PHRASE_LABEL = 'Confirmation phrase';
export const DELETE_PHRASE_MISMATCH = 'That does not match. Type it exactly as shown.';
export const DELETE_BUSY = 'Deleting…';
export const DELETE_DONE_TITLE = 'Your data has been deleted';

export function deletionCounts(rows: number, files: number): string {
  const parts = [`${rows} ${rows === 1 ? 'record' : 'records'}`];
  if (files > 0) {
    parts.push(`${files} ${files === 1 ? 'file' : 'files'}`);
  }
  return parts.join(' and ');
}

export function deletionResultSummary(
  rows: number,
  files: number,
  caregivers: number
): string {
  const parts = [`${rows} ${rows === 1 ? 'record' : 'records'} removed`];
  if (files > 0) parts.push(`${files} ${files === 1 ? 'file' : 'files'} removed`);
  if (caregivers > 0) {
    parts.push(
      `${caregivers} ${caregivers === 1 ? 'person' : 'people'} no longer has access`
    );
  }
  return `${parts.join('. ')}.`;
}

/** What is left, said plainly, so nobody wonders whether they still have an account. */
export function remainingSummary(otherProfiles: number): string {
  if (otherProfiles === 0) {
    return 'You are still signed in. There is nothing else on this account.';
  }
  return `You are still signed in. ${otherProfiles} other ${
    otherProfiles === 1 ? 'profile' : 'profiles'
  } on this account ${otherProfiles === 1 ? 'is' : 'are'} untouched.`;
}
