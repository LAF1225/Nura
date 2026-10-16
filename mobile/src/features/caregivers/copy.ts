/**
 * Every sentence the caregiver and family screens say.
 *
 * PRD 9, sections 15, 18, 25, 34-38, 47, 52, 71, 86, 88 and 94.
 *
 * One file, for the reason PRD 7 found and PRD 8 kept: when all the prose is in
 * one place the test that checks none of it diagnoses anything, promises a
 * notification nothing sends, or implies a capability Nura does not have is
 * exhaustive rather than a spot check.
 *
 * Three rules every string here follows.
 *
 * **Nothing promises delivery.** Section 37 allows "sent" and "read" and no
 * stronger claim, and there is no push notification for a family message yet.
 * So nothing here says "delivered", "received" or "notified".
 *
 * **Nothing implies monitoring.** Section 2 rules out a surveillance
 * experience, section 36 says check-ins must not be compulsory, and section 49
 * says the user is not told every time a caregiver looks at something. No string
 * here reports that somebody viewed anything, and no check-in is phrased as a
 * request that expects an answer.
 *
 * **A permission label says what would actually be visible.** Section 15
 * forbids vague wording such as "access health information". The labels
 * themselves come from the server, so they cannot drift between the invitation
 * screen and the permission screen; what is here is the surrounding
 * explanation.
 */
import type { CheckInCode, PermissionKey, RelationshipStatus } from './types';

// --- the caregiver list ------------------------------------------------------

export const CAREGIVERS_TITLE = 'Caregivers';
export const CAREGIVERS_INTRO =
  'The people who help look after you, and exactly what each of them can see.';
export const CAREGIVERS_EMPTY =
  'Nobody is helping with your care in Nura yet. You can invite someone, and choose what they see.';
export const CAREGIVERS_EMPTY_HINT =
  'You can change what they see, or remove them, at any time.';

export const STATUS_LABELS: Record<RelationshipStatus, string> = {
  pending: 'Invitation sent',
  active: 'Active',
  declined: 'Declined',
  revoked: 'Removed',
  expired: 'Invitation expired',
};

export function grantedSentence(count: number, total: number): string {
  if (count === 0) return `Can see nothing yet, of ${total} areas`;
  return `Can see ${count} of ${total} areas`;
}

// --- inviting ----------------------------------------------------------------

export const INVITE_TITLE = 'Invite someone';
export const INVITE_INTRO =
  'Choose what they will be able to see. You can change it later, or remove them.';
export const INVITE_NAME_LABEL = 'Their name';
export const INVITE_NAME_HINT = 'What you would like to call them in your list';
export const INVITE_CONTACT_LABEL = 'Email or phone (optional)';
export const INVITE_CONTACT_HINT = 'Just a note for you. Nura does not contact them.';
export const INVITE_ROLE_LABEL = 'How are they related to you?';
export const INVITE_ROLE_HINT =
  'A label for your list. It does not change what they can see.';
export const INVITE_PERMISSIONS_LABEL = 'What they can see';
export const INVITE_SEND = 'Create invitation';
export const INVITE_FAILED = 'That invitation could not be created. Please try again.';

/**
 * The one sentence that has to be said plainly (section 12).
 *
 * Nura has no mail sender and no SMS gateway, so sharing the link is the primary
 * user's job. Saying so is better than a Send button that quietly does nothing.
 */
export const INVITE_DELIVERY =
  'Nura cannot send this for you. Share the link below however you normally talk to them.';
export const INVITE_LINK_TITLE = 'Their invitation link';
export const INVITE_LINK_ONCE =
  'This is shown once. If you lose it, remove the invitation and create another.';
export const INVITE_LINK_PRIVATE =
  'Anyone who has this link can accept it, so send it directly to them.';

export function inviteExpirySentence(label: string): string {
  return `It stops working on ${label}.`;
}

// --- accepting ---------------------------------------------------------------

export const ACCEPT_TITLE = 'Help with someone’s care';
export const ACCEPT_WILL_ACCESS = 'You will be able to see';
export const ACCEPT_WILL_NOT_ACCESS = 'You will not be able to see';
export const ACCEPT_BUTTON = 'Accept';
export const DECLINE_BUTTON = 'Decline';
export const ACCEPT_NO_PROFILE_NEEDED =
  'You do not need to set up Nura for yourself to help with theirs.';
export const ACCEPT_FAILED = 'That invitation could not be accepted.';
export const INVITATION_NOT_FOUND =
  'This invitation has expired, has already been used, or is not valid.';

export function acceptIntro(profileName: string, invitedName: string): string {
  return `${invitedName}, you have been asked to help with ${profileName}’s care.`;
}

// --- permissions -------------------------------------------------------------

export const PERMISSIONS_TITLE = 'What they can see';
export const PERMISSIONS_INTRO =
  'Each area is separate. Turning one on does not turn on any of the others.';
export const PERMISSIONS_SAVED = 'Saved';
export const PERMISSIONS_SAVE = 'Save';
export const PERMISSIONS_FAILED = 'That change could not be saved. Please try again.';

/**
 * Said against the two categories that are granted but do nothing.
 *
 * Section 94 is explicit that the `safety_alerts` key may exist before its event
 * source does and that no alert should be fabricated. The same honesty applies
 * to routines, which no PRD has defined. Granting either is stored faithfully
 * and unlocks nothing, and this says so rather than showing an empty section
 * that reads as "nothing recorded".
 */
/**
 * Categories that can be granted and unlock nothing, with the honest reason.
 *
 * **Empty since PRD 12**, and the history is the point. `safety_alerts` left
 * this list in PRD 10, which built the event source PRD 9 section 94 said not
 * to fabricate. `routines` left it in PRD 12, which built routines, runs and
 * steps -- so the sentence saying Nura keeps none would now be the untrue one.
 *
 * The map stays, and the screen still renders whatever is in it. The next
 * permission that is reserved before its data exists goes here, and nothing
 * else has to change.
 */
export const PERMISSION_NOT_YET: Partial<Record<PermissionKey, string>> = {};

export const ROLE_NOTE = 'Changing this label does not change what they can see.';

// --- removing ----------------------------------------------------------------

export const REMOVE_TITLE = 'Remove this person';
export const REMOVE_BODY =
  'They will not be able to see anything of yours from the moment you remove them. Messages you have already exchanged stay in Nura.';
export const REMOVE_BUTTON = 'Remove';
export const KEEP_BUTTON = 'Keep them';

/**
 * The confirm step names the person.
 *
 * Section 77 asks for approval dialogs that clearly state what will change, and
 * two presses of a button reading just "Remove" state nothing -- the first press
 * would look like nothing happened.
 */
export function confirmRemoveLabel(name: string): string {
  return `Yes, remove ${name}`;
}
export const REMOVE_FAILED = 'They could not be removed. Please try again.';
export const WITHDRAW_INVITATION_BODY = 'The link you sent them will stop working.';

// --- Caregiver Mode ----------------------------------------------------------

export const MODE_SWITCH_LABEL = 'Switch';
export const MY_NURA = 'My Nura';
export const CAREGIVER_MODE = 'Caregiver Mode';
export const SUPPORTED_TITLE = 'People you support';
export const SUPPORTED_EMPTY =
  'You are not helping with anyone’s care in Nura. When someone invites you, they will appear here.';

export function supportingSentence(name: string): string {
  return `You are looking at ${name}’s care.`;
}

/**
 * What a caregiver is told about their own waiting suggestions (section 88).
 *
 * Phrased so it cannot be read as "it will happen": the decision is the primary
 * user's, and section 21 is explicit that nothing is applied by a caregiver
 * account.
 */
export function caregiverPendingSentence(count: number): string {
  return count === 1
    ? 'You have 1 suggestion waiting for a decision.'
    : `You have ${count} suggestions waiting for a decision.`;
}

export const CAREGIVER_PENDING_NOTE = 'They decide whether to apply them.';

export const NO_REMINDERS_SET = 'No reminders set up';
export const REMINDERS_PAUSED = 'Reminders paused';
export const NO_UPCOMING_APPOINTMENTS = 'No upcoming appointments.';
export const NO_SEVERITY_RECORDED = 'No severity recorded';

export function severitySentence(severity: number): string {
  return `Last recorded as ${severity} out of 10`;
}

/** Counts, in the order the screen reads them. Never a verdict on them. */
export function adherenceCounts(taken: number, skipped: number, missed: number): string {
  return `${taken} taken, ${skipped} skipped, ${missed} not recorded`;
}

/** Counts only, never a name (section 67). */
export function healthCountsSentence(
  conditions: number,
  medications: number,
  symptoms: number
): string {
  return `${conditions} conditions, ${medications} medications, ${symptoms} symptoms recorded`;
}

export function reportVersionLabel(version: number): string {
  return `Version ${version}`;
}

export const CARE_NOTIFICATIONS_NOT_DELIVERED =
  'Nura does not send these to your phone yet. Your choices are kept for when it can.';

export const SELF_MODE_PROMPT =
  'You are looking at your own Nura. Choose someone to support.';

export function sharedAreasSentence(count: number): string {
  if (count === 0) return 'Nothing shared with you yet';
  return count === 1 ? '1 area shared with you' : `${count} areas shared with you`;
}

export function contactCountSentence(count: number): string {
  if (count === 0) return 'No emergency contacts yet.';
  return count === 1 ? '1 emergency contact' : `${count} emergency contacts`;
}

export const CAREGIVER_HOME_NOTHING_GRANTED =
  'Nothing has been shared with you yet. They can choose what you see.';

/**
 * Said when a category is granted and there is genuinely nothing in it.
 *
 * Distinct from a category that was not granted, which is not shown at all --
 * section 18 says the absence of a permission must not leak, so the screen never
 * names an area the caregiver cannot see.
 */
export const NOTHING_RECORDED = 'Nothing recorded.';

export const ADHERENCE_NOTE = 'Counts only. Nura does not draw conclusions from them.';
export const NO_DOSES_DUE = 'No doses were due in this period.';

// --- suggestions -------------------------------------------------------------

export const SUGGESTIONS_TITLE = 'Care requests';
export const SUGGESTIONS_INTRO =
  'Changes someone has suggested. Nothing happens until you approve it.';
export const SUGGESTIONS_EMPTY = 'No care requests are waiting.';
export const SUGGESTION_CURRENT = 'Now';
export const SUGGESTION_PROPOSED = 'Suggested';
export const APPROVE_BUTTON = 'Approve';
export const DECLINE_SUGGESTION_BUTTON = 'Decline';
export const APPROVE_FAILED = 'That change could not be applied. Please try again.';
export const DECLINE_FAILED = 'That could not be saved. Please try again.';
export const SUGGESTION_TARGET_MISSING =
  'The thing this would change is no longer there, so it cannot be applied.';
export const DECLINE_NOTE_LABEL = 'Add a note for yourself (optional)';
export const DECLINE_NOTE_HINT = 'Only you can see this.';

export const SUGGESTION_STATUS_LABELS: Record<string, string> = {
  pending: 'Waiting for a decision',
  approved: 'Approved',
  declined: 'Declined',
  cancelled: 'Withdrawn',
  expired: 'Expired',
};

export function suggestedBy(name: string): string {
  return `${name} suggested a change`;
}

export const PROPOSE_TITLE = 'Suggest a change';
export const PROPOSE_INTRO =
  'They will be asked to approve it. Nothing changes until they do.';
export const PROPOSE_SEND = 'Send suggestion';
export const PROPOSE_FAILED = 'That suggestion could not be sent. Please try again.';
export const PROPOSE_SENT = 'Sent. They will see it in Nura.';
export const PROPOSE_CANCEL = 'Withdraw';
export const PROPOSE_NO_SCHEDULE =
  'There are no reminders set up for this, so there is nothing to change.';

// --- family messaging --------------------------------------------------------

export const MESSAGES_TITLE = 'Messages';
export const MESSAGES_INTRO = 'Keeping in touch with the people who help you.';
export const MESSAGES_EMPTY = 'No messages yet.';
export const THREAD_EMPTY = 'Say hello.';
export const MESSAGE_PLACEHOLDER = 'Write a message';
export const MESSAGE_SEND = 'Send';
export const MESSAGE_SENDING = 'Sending…';
export const MESSAGE_FAILED = 'That message was not sent. Tap to try again.';
export const MESSAGE_READ = 'Read';
export const MESSAGE_SENT = 'Sent';
export const CHECK_IN_TITLE = 'Quick check-in';

/**
 * The draft banner (sections 71 and 72).
 *
 * Says what is true: the text is kept on this phone, and it has not been sent.
 * Not "it will send when you are back online" -- there is no send queue, and a
 * message that went out an hour later without the sender knowing is worse than
 * one they resend themselves.
 */
export const DRAFT_KEPT = 'Saved on this phone. It has not been sent yet.';
export const OFFLINE_NOTE =
  'You are offline. What you type is kept here until you send it.';

export const CHECK_IN_LABELS: Record<CheckInCode, string> = {
  im_okay: 'I’m okay',
  not_great: 'Not feeling great',
  please_call_me: 'Can you call me?',
  need_help: 'I need help with something',
  how_are_you: 'How are you doing?',
  thinking_of_you: 'Thinking of you',
};

/** Said beside the check-in buttons, so nobody reads one as an alarm. */
export const CHECK_IN_NOTE =
  'These are messages, not alerts. Nura does not call anyone for you.';

export function unreadSentence(count: number): string {
  if (count === 0) return 'Nothing new';
  return count === 1 ? '1 new message' : `${count} new messages`;
}

// --- calling -----------------------------------------------------------------

/**
 * What the app says instead of showing a call screen (section 38).
 *
 * Section 38 forbids simulating a successful call. No provider is configured in
 * any deployment, so there is no Call control to press -- and if the server is
 * reached anyway it answers plainly rather than ringing.
 */
export const CALLING_UNAVAILABLE =
  'Calling through Nura is not available yet. Use your phone to call them.';

// --- emergency contacts ------------------------------------------------------

export const CONTACTS_TITLE = 'Emergency contacts';
export const CONTACTS_INTRO =
  'Who you would want contacted first, in the order you would want them tried.';

/**
 * The sentence that keeps this screen honest (PRD 9 section 47; PRD 10
 * sections 30, 39 and 74).
 *
 * PRD 9 managed the chain and never walked it. PRD 10 walks it -- and what
 * walking it does today is record an in-app alert for a caregiver and write
 * down that calling and texting are not set up. So the sentence changed from
 * "Nura does not contact anyone" to the narrower true thing, because the first
 * one is now wrong in a way that undersells it and the obvious replacement
 * ("Nura will call these people") would be wrong in the dangerous direction.
 */
export const CONTACTS_NOT_YET =
  'Nura uses this order if you ask for help. It cannot call or text anyone in this build — it records what it tried and shows you.';
export const CONTACTS_EMPTY = 'No emergency contacts yet.';
export const CONTACT_NAME_LABEL = 'Name';
export const CONTACT_PHONE_LABEL = 'Phone (optional)';
export const CONTACT_RELATIONSHIP_LABEL = 'How are they related? (optional)';
export const CONTACT_RELATIONSHIP_HINT = 'For example, spouse, son, neighbour';
export const CONTACT_ACTIVE_LABEL = 'Include in the list';
export const CONTACT_SAVE = 'Save contact';
export const CONTACT_SAVED = 'Saved';
export const CONTACT_FAILED = 'That contact could not be saved. Please try again.';
export const CONTACT_DELETE = 'Remove contact';
export const MOVE_UP = 'Move up';
export const MOVE_DOWN = 'Move down';
export const CONTACT_INACTIVE = 'Not included';

export function priorityLabel(priority: number): string {
  return `Number ${priority} in the list`;
}

// --- notifications -----------------------------------------------------------

export const CARE_NOTIFICATIONS_TITLE = 'Care notifications';
export const CARE_NOTIFICATIONS_INTRO =
  'What Nura tells you about. Requests to approve always appear in the app, whichever of these are off.';

export const CARE_NOTIFICATION_LABELS: Record<string, string> = {
  caregiver_messages: 'Messages from the people who help you',
  suggestion_requests: 'Changes someone has suggested',
  appointment_suggestions: 'Appointments someone has suggested',
  routine_suggestions: 'Routines someone has suggested',
};

export const CAREGIVER_NOTIFICATION_LABELS: Record<string, string> = {
  messages: 'Messages',
  appointment_updates: 'Appointment changes',
  suggestion_outcomes: 'Whether your suggestions were approved',
  safety_alerts: 'Safety alerts',
};

/**
 * Said against the safety-alert notification toggle.
 *
 * PRD 9 said "Nura does not watch for emergencies yet, so nothing will be
 * sent", which was true then. PRD 10 built the thing that sends them, so the
 * sentence changed -- and what it changed to is the narrower true statement:
 * an alert will exist in the app, and no push, text or call will happen,
 * because no provider exists to make one (PRD 10, sections 38 and 93).
 */
export const SAFETY_ALERTS_NOTE =
  'You will get an alert in the app. Nura cannot send a push notification, a text or a call in this build.';

// --- the Care screen ---------------------------------------------------------

export const CARE_SECTION_TITLE = 'Caregivers and family';

export function careSummarySentence(
  caregivers: number,
  pendingInvitations: number
): string {
  if (caregivers === 0 && pendingInvitations === 0) {
    return 'Nobody is helping with your care yet.';
  }
  const parts: string[] = [];
  parts.push(caregivers === 1 ? '1 caregiver' : `${caregivers} caregivers`);
  if (pendingInvitations > 0) {
    parts.push(
      pendingInvitations === 1
        ? '1 invitation waiting'
        : `${pendingInvitations} invitations waiting`
    );
  }
  return `${parts.join(', ')}.`;
}

export function pendingRequestsSentence(count: number): string {
  if (count === 0) return '';
  return count === 1
    ? '1 care request is waiting for you.'
    : `${count} care requests are waiting for you.`;
}

// --- shared failures ---------------------------------------------------------

export const LOAD_FAILED = 'That could not be loaded. Pull down to try again.';
export const OFFLINE_READ_ONLY =
  'You are offline, so this may not be up to date. Changes are not saved until you are back online.';
