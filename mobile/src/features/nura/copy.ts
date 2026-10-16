/**
 * Every sentence the Nura screens can say (PRD 8, sections 2, 16 and 73).
 *
 * In one file for the same reason PRD 7 put report prose in one file: a test
 * reads all of it and fails on a diagnosis, a likelihood, a cause, a treatment
 * suggestion or a promise of help Nura cannot give. That check is only
 * exhaustive if there is nowhere else for a sentence to live, so screens
 * import from here rather than writing their own.
 *
 * What is deliberately *not* here: anything the model says. That is generated
 * text, bounded by the guardrails in `services/assistant/policy.py`, and no
 * amount of app-side copy changes what it can be. These are the sentences
 * Nura says as a *product* -- labels, empty states, what happened when
 * something failed.
 *
 * The tone rules are section 2's: warm, mature, useful. Not a mascot, not
 * cheerful about health, and never reassuring about a symptom.
 */

// --- the Nura tab -----------------------------------------------------------

export const NURA_INTRO =
  'A calm companion for everyday health. Ask about what you have recorded, or ' +
  'about anything else on your mind.';

export const START_CONVERSATION = 'Start a conversation';
export const NEW_CONVERSATION = 'New conversation';
export const CONTINUE_CONVERSATION = 'Continue';
export const RECENT_HEADING = 'Recent';
export const SEE_ALL_CONVERSATIONS = 'All conversations';

export const SETTINGS_HEADING = 'How Nura works with you';
export const PERSONALITY_LINK = 'Personality';
export const VOICE_LINK = 'Voice and language';
export const MEMORY_LINK = 'What Nura remembers';
export const PROACTIVITY_LINK = 'When Nura speaks first';
export const INSTRUCTIONS_LINK = 'Custom instructions';

/**
 * Shown when the server has no model provider configured (section 55).
 * Says what is true -- this is a deployment that has not been set up -- rather
 * than implying the phone or the connection is at fault.
 */
export const ASSISTANT_UNAVAILABLE =
  'Nura’s assistant is not set up on this server yet. Everything else in ' +
  'the app works as usual.';

// --- the conversation -------------------------------------------------------

export const COMPOSER_PLACEHOLDER = 'Type a message';
export const COMPOSER_LABEL = 'Message to Nura';
export const SEND = 'Send';
export const SENDING = 'Nura is thinking';
export const RETRY = 'Try again';
export const CONVERSATION_EMPTY = 'What would you like help with?';

/** Shown above a thread that was archived, so nobody types into a shelf. */
export const ARCHIVED_NOTICE = 'This conversation is archived.';

export const RENAME_CONVERSATION = 'Rename';
export const ARCHIVE_CONVERSATION = 'Archive';
export const UNARCHIVE_CONVERSATION = 'Restore';
export const DELETE_CONVERSATION = 'Delete conversation';

/**
 * The delete confirmation. Says exactly what goes and what stays, because
 * section 61 is a promise the user should be able to see kept.
 */
export const DELETE_CONVERSATION_HINT =
  'Deletes this conversation only. Your medications, symptoms, appointments, ' +
  'health record and saved memories are not affected.';

// --- offline ----------------------------------------------------------------

/**
 * Section 56: a clear offline banner, and no fake assistant reply. The draft
 * claim is true -- `composerStore` persists it (section 57).
 */
export const OFFLINE_NOTICE =
  'You are offline, so Nura cannot reply right now. Your message is saved on ' +
  'this phone and your conversations are still here to read.';

export const DRAFT_SAVED = 'Saved on this phone';

/** Shown under a reply that hit the output ceiling (PRD 8, section 77). */
export const TRUNCATED_NOTE = 'That reply was cut short. Ask again for the rest.';

/** The everything-else failure, for a save that did not go through. */
export const SAVE_FAILED = 'That could not be saved. Try again.';

// --- failures ---------------------------------------------------------------

/**
 * The fallback when the server sends a failure code the app has not seen.
 * Every known code arrives with its own sentence from the backend, which is
 * where section 55's fixed set lives.
 */
export const GENERIC_FAILURE = 'Nura can’t respond right now. Please try again.';

// --- serious and privacy modes ---------------------------------------------

/** Section 37's banner. States what changed and why, in one line. */
export const SERIOUS_BANNER =
  'Nura is keeping this brief and direct because of what you asked about.';

/** Section 68: Privacy Mode is clearly indicated. */
export const PRIVACY_BANNER =
  'Privacy mode is on. Nura will not suggest new memories or bring up your ' +
  'records unless you ask.';

export const PRIVACY_MODE_LABEL = 'Privacy mode';

// --- write confirmation -----------------------------------------------------

export const CONFIRM = 'Confirm';
export const CANCEL = 'Cancel';
export const ACTION_CONFIRMED = 'Done.';
export const ACTION_CANCELLED = 'Nothing was changed.';

// --- the symptom hand-off ---------------------------------------------------

/**
 * Section 18: route into the PRD 6 workflow rather than discussing a symptom
 * loosely. The wording offers to *record* it and promises nothing else.
 */
export const LOG_SYMPTOM_PROMPT =
  'Would you like to record that as a symptom, so it is saved properly?';
export const LOG_SYMPTOM = 'Record a symptom';
export const JUST_ASKING = 'No, just asking';

// --- memory -----------------------------------------------------------------

export const MEMORY_HEADING = 'What Nura remembers';
export const MEMORY_INTRO =
  'Nura keeps a short list of how you like to be spoken to. Your health ' +
  'records are kept separately and are not part of this list.';
export const MEMORY_EMPTY = 'Nura is not remembering anything yet.';
export const ADD_MEMORY = 'Add something to remember';
export const MEMORY_LABEL = 'What should Nura remember?';
export const MEMORY_PLACEHOLDER = 'For example: call me Baba';
export const EDIT_MEMORY = 'Edit';
export const REMOVE_MEMORY = 'Remove';
export const MEMORY_ACTIVE = 'In use';

/** Section 47's promise, said on the button that keeps it. */
export const REMOVE_MEMORY_HINT = 'Forgets this one thing. Nothing else is affected.';
export const MEMORY_PAUSED = 'Paused';

/** Section 94's exact shape: a question, Remember, Not now. */
export const MEMORY_SUGGESTION_TITLE = 'Would you like Nura to remember this?';
export const REMEMBER_THIS = 'Remember';
export const NOT_NOW = 'Not now';

export const MEMORY_FULL =
  'Nura is already remembering as much as it can. Remove something first.';

/** Section 26, when a stored instruction tries to move the boundary. */
export const UNSAFE_INSTRUCTION =
  'Nura can’t follow that. It can’t be asked to diagnose, to leave out ' +
  'safety information, to reveal how it is set up, or to reach anyone ' +
  'else’s information.';

// --- personality ------------------------------------------------------------

export const PERSONALITY_HEADING = 'Personality';
export const PERSONALITY_INTRO =
  'These change how Nura sounds. They do not change what Nura will and will ' +
  'not say about your health.';

export const PRESET_HEADING = 'Start from';
export const PRESET_ADJUSTED = 'Adjusted';

export const PRESET_LABELS: Record<string, string> = {
  gentle: 'Gentle',
  friendly: 'Friendly',
  focused: 'Focused',
  professional: 'Professional',
};

export const PRESET_DESCRIPTIONS: Record<string, string> = {
  gentle: 'Warm and unhurried, with no jokes and light reminders.',
  friendly: 'Warm and chatty, with a little humour.',
  focused: 'Brief and plain, and direct about what is outstanding.',
  professional: 'Even in tone, brief, and direct about what is outstanding.',
};

export const TRAIT_LABELS: Record<string, string> = {
  warmth: 'Warmth',
  humour: 'Humour',
  talkativeness: 'Talkativeness',
  proactivity: 'Speaking first',
  reminderFirmness: 'Reminder firmness',
};

export const LEVEL_LABELS: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  off: 'Off',
};

/** Section 24, said to the user rather than only enforced behind the screen. */
export const PERSONALITY_SAFETY_NOTE =
  'Whatever you choose here, Nura stays serious about anything to do with ' +
  'your safety or your medication.';

// --- voice and language -----------------------------------------------------

export const VOICE_HEADING = 'Voice and language';

/**
 * Section 27: settings are stored now and used when there is something to
 * speak with. Saying so is better than a control that appears to do nothing.
 */
export const VOICE_NOT_YET =
  'Nura has no voice yet. These are saved for when speaking arrives.';

export const VOICE_LABEL = 'Voice';
export const SPEED_LABEL = 'Speaking speed';
export const VERBOSITY_LABEL = 'Reply length';
export const LANGUAGE_LABEL = 'Language';

export const VOICE_LABELS: Record<string, string> = {
  calm: 'Calm',
  clear: 'Clear',
  warm: 'Warm',
  bright: 'Bright',
};

export const SPEED_LABELS: Record<string, string> = {
  slow: 'Slow',
  normal: 'Normal',
  fast: 'Fast',
};

export const VERBOSITY_LABELS: Record<string, string> = {
  concise: 'Concise',
  balanced: 'Balanced',
  detailed: 'Detailed',
};

/** Section 31: state that only English is implemented, do not fake the rest. */
export const LANGUAGE_NOTE =
  'Nura speaks English at the moment. More languages are coming.';

export const VERBOSITY_NOTE =
  'Shorter replies never leave out something you need for your safety.';

// --- proactivity ------------------------------------------------------------

export const PROACTIVITY_HEADING = 'When Nura speaks first';
export const PROACTIVITY_INTRO =
  'Nura can mention things you have already recorded — an appointment ' +
  'tomorrow, a check-in you have not done, a medication running low. It never ' +
  'raises a health concern on its own.';

export const PROACTIVITY_LABELS: Record<string, string> = {
  off: 'Never',
  low: 'Rarely',
  medium: 'Sometimes',
  high: 'Often',
};

export const DISMISS_PROMPT = 'Not now';
export const PROMPTS_EMPTY = 'Nothing to mention right now.';

// --- modes ------------------------------------------------------------------

export const MODE_HEADING = 'Mode';
export const MODE_LABELS: Record<string, string> = {
  normal: 'Normal',
  focus: 'Focus',
  sleep: 'Sleep',
  privacy: 'Privacy',
};

export const MODE_DESCRIPTIONS: Record<string, string> = {
  normal: 'Nura behaves as you have set it up.',
  focus: 'Shorter replies, and nothing raised that you did not ask about.',
  sleep: 'Quiet replies, and no nudges. Your reminders are unaffected.',
  privacy:
    'No new memories suggested, nothing about your records volunteered, and ' +
    'nothing raised first.',
};

/** Section 67, said plainly so nobody expects mode to silence a reminder. */
export const MODE_REMINDERS_NOTE =
  'Your medication and appointment reminders follow their own settings and ' +
  'are not changed by this.';

// --- custom instructions ----------------------------------------------------

export const INSTRUCTIONS_HEADING = 'Custom instructions';
export const INSTRUCTIONS_INTRO = 'Tell Nura how you prefer it to talk with you.';
export const INSTRUCTIONS_LABEL = 'Custom instructions';
export const INSTRUCTIONS_PLACEHOLDER = 'Keep morning conversations short.';

export const INSTRUCTION_EXAMPLES = [
  'Keep morning conversations short.',
  'Explain medical words simply.',
  'Don’t use overly cheerful language when I’m unwell.',
];

/** Section 25's boundary, said to the user before they hit it. */
export const INSTRUCTIONS_LIMIT_NOTE =
  'Nura follows these where it can. They cannot change what it will say about ' +
  'your health, or reach anyone else’s information.';

export const SAVE = 'Save';
export const SAVED = 'Saved';

// --- history ----------------------------------------------------------------

export const HISTORY_HEADING = 'Conversations';
export const HISTORY_EMPTY = 'You have not talked with Nura yet.';
export const SHOW_ARCHIVED = 'Show archived';
export const HIDE_ARCHIVED = 'Hide archived';
export const ARCHIVED_LABEL = 'Archived';
