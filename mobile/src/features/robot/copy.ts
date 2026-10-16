/**
 * Every robot sentence the app writes for itself, in one module (PRD 11, s75).
 *
 * **What is *not* here.** Anything describing what the robot can do, what it
 * was asked to show, or what became of it comes from the server: the
 * capability labels, the state labels, the history lines, the offline note and
 * the hardware note. One module writes the prose that could make a claim about
 * hardware, and it is `backend/app/services/robot/wording.py`.
 *
 * This file holds the words that are about the *app*: screen titles, section
 * headings, the explanations next to a setting, and the sentences that say
 * what a setting will do when there is hardware to do it with (section 49).
 *
 * **Four rules, each with a test in `tests/robotCopy.test.ts`.** Nothing here
 * claims the robot showed, spoke or played anything (section 20). Nothing here
 * says help is coming (section 8). Nothing here describes a detector (section
 * 9). And every sentence about a future capability says *when*, not *now*
 * (section 49) -- "when a speaker is available" rather than "reads aloud".
 */

export const ROBOT_TITLE = 'Nura Device';
export const ROBOT_SUBTITLE =
  'How Nura looks and behaves on its own screen, and what it can actually do.';

// --- status ------------------------------------------------------------------

export const STATUS_TITLE = 'Status';
export const NO_DEVICE_TITLE = 'No Nura connected yet';
export const NO_DEVICE_BODY =
  'Set up a Nura to choose how it looks and behaves. These settings wait here until you do.';
export const SET_UP_DEVICE = 'Set up Nura';
export const SETUP_INCOMPLETE =
  'Setup is not finished. Open Nura’s setup in the app to complete it.';

/** Section 4's modes, explained where the app has to name one. */
export const MODE_HINTS: Record<string, string> = {
  companion: 'Resting, with its face showing.',
  information: 'Showing a card rather than its face.',
  focus: 'Quiet. Information only when it matters.',
  sleep: 'Dimmed, and holding non-urgent things back.',
  privacy: 'Not showing anything about you.',
  safety: 'Asking whether you are okay.',
  emergency: 'Showing what Nura is doing about your safety request.',
  offline: 'Not reachable. Anything waiting stays on your phone.',
  setup: 'Waiting for setup to be finished.',
  error: 'Nura has something to report. Check its screen.',
};

// --- display -----------------------------------------------------------------

export const DISPLAY_TITLE = 'Display';
export const BRIGHTNESS_TITLE = 'Screen brightness';
export const BRIGHTNESS_HINT = 'How bright Nura’s screen is. Nura dims itself in Sleep.';
export const BRIGHTNESS_LABELS: Record<number, string> = {
  0: 'Off',
  25: 'Dimmest',
  50: 'Dim',
  75: 'Bright',
  100: 'Brightest',
};

export const REDUCED_MOTION_TITLE = 'Reduced motion';
export const REDUCED_MOTION_HINT = 'Still eyes, no bouncing, and no quick transitions.';
export const REDUCED_MOTION_FOLLOWING =
  'Following your accessibility setting. Choose On or Off to decide separately.';
export const REDUCED_MOTION_FOLLOW = 'Follow my accessibility setting';

export const FACE_ANIMATION_TITLE = 'Face animation';
export const FACE_ANIMATION_HINT =
  'A slow blink while Nura is resting. Nothing is ever said with movement alone.';

export const PRIVACY_PREVIEW_TITLE = 'Medication detail on Nura';
export const PRIVACY_PREVIEW_HINT =
  'Nura’s screen may be visible to other people in the room. This is what a reminder shows.';

export const SLEEP_SCREEN_TITLE = 'Sleep screen';
export const SLEEP_SCREEN_HINT = 'What Nura’s screen does while it is asleep.';

export const MESSAGE_DISPLAY_TITLE = 'Show family messages';
export const MESSAGE_DISPLAY_HINT =
  'A message from a family member appears on Nura’s screen with their name.';

// --- audio -------------------------------------------------------------------

export const AUDIO_TITLE = 'Audio';
export const VOLUME_TITLE = 'Volume';
export const VOLUME_HINT = 'How loud Nura is, when it can make a sound.';
export const VOLUME_LABELS: Record<number, string> = {
  0: 'Silent',
  25: 'Quietest',
  50: 'Quiet',
  75: 'Loud',
  100: 'Loudest',
};

/**
 * Sections 43 and 49, and the phrasing matters.
 *
 * Each of these says *when*, because none of them can happen yet: no robot has
 * ever reported a speaker. "Read reminders aloud" would describe something
 * this build does; "when Nura has a speaker" describes a preference being kept
 * for later, which is what is actually true.
 */
export const READ_MEDICATIONS_TITLE = 'Read reminders aloud';
export const READ_MEDICATIONS_HINT =
  'When Nura has a working speaker, say medication reminders out loud.';
export const READ_MESSAGES_TITLE = 'Read family messages aloud';
export const READ_MESSAGES_HINT =
  'When Nura has a working speaker, read messages out loud. Other people in the room would hear them.';
export const READ_ASSISTANT_TITLE = 'Read Nura’s replies aloud';
export const READ_ASSISTANT_HINT =
  'When Nura has a working speaker, say its replies out loud.';

// --- companion ---------------------------------------------------------------

export const COMPANION_TITLE = 'Companion';
export const COMPANION_HINT =
  'Nura rests with its face showing, and switches to plain information when something matters.';

// --- capabilities ------------------------------------------------------------

export const CAPABILITIES_TITLE = 'What this Nura can do';
export const CAPABILITIES_HINT =
  'Nura reports each part of itself separately. Nothing here is assumed.';
export const CAPABILITY_STALE =
  'Reported by an older version of Nura’s software. It has not been checked since.';
export const CAPABILITY_NEVER_REPORTED = 'Nura has not told us about this part.';

// --- history -----------------------------------------------------------------

export const HISTORY_TITLE = 'What Nura was asked to show';
export const HISTORY_HINT =
  'Nura has to confirm that it drew something before this says it was shown.';
export const HISTORY_EMPTY = 'Nothing has been sent to Nura’s screen yet.';
export const HISTORY_PRIVATE =
  'Reminders are listed as Nura received them, so a private reminder stays private here too.';

// --- preview -----------------------------------------------------------------

export const PREVIEW_TITLE = 'Preview Nura’s display';
export const PREVIEW_HINT =
  'A drawing of how each kind of card is laid out on Nura’s screen.';
export const PREVIEW_SAMPLES_TITLE = 'Card layouts';
export const PREVIEW_OPEN = 'Preview Nura’s display';

// --- actions -----------------------------------------------------------------

export const SAVING = 'Saving…';
export const SAVE_FAILED = 'That setting could not be saved. Try again.';
export const RETRY = 'Try again';
