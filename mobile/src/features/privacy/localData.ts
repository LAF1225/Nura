/**
 * Everything Nura keeps on this phone, and how to remove it (PRD 13, s39).
 *
 * **Signing out cleared the query cache and nothing else.** PRD 13 section 39
 * asks for local sensitive caches to be cleared on sign-out, and before this
 * module they were not: seventeen AsyncStorage keys and seven persisted stores
 * survived a sign-out, so the next person to sign in on the same phone
 * inherited the previous one's symptom draft, appointment form, caregiver
 * message drafts, assistant composer, Today cache and every offline queue.
 *
 * Three decisions shape the list.
 *
 * **It is a list, not a prefix wipe.** `AsyncStorage.clear()` would be shorter
 * and would also remove things that are not user data -- Expo's own keys, and
 * anything a library stores under its own name. Removing another library's
 * state on sign-out is the kind of fix that works until it breaks something
 * unrelated.
 *
 * **Every key says what it holds and whether it is personal.** The distinction
 * decides what goes on sign-out versus what goes when a *profile* is deleted,
 * and it is the reason `clearOnSignOut` and `clearForProfileDeletion` are
 * different functions rather than one with a flag.
 *
 * **A drift test reads the source.** `localData.test.ts` greps every
 * `'nura.…'` literal and every persisted store name out of `src/` and fails if
 * one is not listed here. A hand-maintained inventory that nothing checks is
 * the bug PRD 13 found in `PROFILE_SCOPED_KEY_PREFIXES`; this one is checked.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

/** What one stored thing is, so the lists below are decisions rather than strings. */
export interface LocalStore {
  /** The AsyncStorage key, or the persisted store's `name`. */
  key: string;
  /** What is in it. */
  holds: string;
  /**
   * Whether it contains anything about the person. `false` is for device
   * preferences and mirrors of operating-system state, which a second person
   * signing in on the same phone may reasonably keep.
   */
  personal: boolean;
}

/** Offline queues: actions a person took that have not reached the server. */
export const PENDING_QUEUES: readonly LocalStore[] = [
  {
    key: 'nura.checkin.pending',
    holds: 'A daily check-in answered with no signal.',
    personal: true,
  },
  {
    key: 'nura.medications.pendingActions',
    holds: 'Doses recorded as taken, snoozed or skipped while offline.',
    personal: true,
  },
  {
    key: 'nura.symptoms.pendingEntries',
    holds: 'Symptom entries, and photos waiting to upload.',
    personal: true,
  },
  {
    key: 'nura.appointments.pending',
    holds: 'Appointments written down offline.',
    personal: true,
  },
  {
    key: 'nura.appointments.pendingQuestions',
    holds: 'Questions for a doctor, written offline.',
    personal: true,
  },
  {
    key: 'nura.productivity.pendingTasks',
    holds: 'Tasks created offline.',
    personal: true,
  },
  {
    key: 'nura.productivity.pendingTaskActions',
    holds: 'Tasks completed, reopened, archived or cancelled offline.',
    personal: true,
  },
  {
    key: 'nura.productivity.pendingReminders',
    holds: 'Reminders created offline.',
    personal: true,
  },
  {
    key: 'nura.productivity.pendingSteps',
    holds: 'Routine steps ticked offline.',
    personal: true,
  },
];

/** Cached server responses, kept so a screen is not empty without a signal. */
export const CACHES: readonly LocalStore[] = [
  {
    key: 'nura.today.lastSummary',
    holds: "The last Today response, including the day's medications.",
    personal: true,
  },
];

/**
 * Mirrors of what was handed to the operating system's scheduler.
 *
 * Not personal in themselves -- they hold notification ids and times -- but
 * they are cleared anyway, because a mirror of the previous person's reminders
 * would make the app cancel notifications it no longer understands.
 */
export const NOTIFICATION_MIRRORS: readonly LocalStore[] = [
  {
    key: 'nura.medications.notifications',
    holds: 'Scheduled medication reminder ids.',
    personal: false,
  },
  {
    key: 'nura.appointments.notifications',
    holds: 'Scheduled appointment reminder ids.',
    personal: false,
  },
  {
    key: 'nura.productivity.reminderNotifications',
    holds: 'Scheduled general reminder ids.',
    personal: false,
  },
  {
    key: 'nura.productivity.alarmNotifications',
    holds: 'Scheduled alarm ids.',
    personal: false,
  },
];

/** Half-finished input, kept so closing the app does not lose it. */
export const DRAFTS: readonly LocalStore[] = [
  {
    key: 'nura.health.draft',
    holds: 'A part-filled health record form.',
    personal: true,
  },
  {
    key: 'nura-symptom-draft',
    holds: 'A symptom being described, including the guided conversation.',
    personal: true,
  },
  {
    key: 'nura-appointment-form',
    holds: 'A part-filled appointment.',
    personal: true,
  },
  {
    key: 'nura-report-selection',
    holds: 'Which symptoms and sections a doctor report would include.',
    personal: true,
  },
  {
    key: 'nura-assistant-composer',
    holds: 'An unsent message to Nura.',
    personal: true,
  },
  {
    key: 'nura-family-drafts',
    holds: 'Unsent messages to a caregiver.',
    personal: true,
  },
  {
    key: 'nura-care-suggestion-drafts',
    holds: 'A change a caregiver was part way through proposing.',
    personal: true,
  },
];

/** Which person is on screen, and the account's own routing state. */
export const CONTEXT: readonly LocalStore[] = [
  {
    key: 'nura-care-mode',
    holds: 'Whose Nura is on screen: your own, or somebody you support.',
    personal: true,
  },
  {
    key: 'nura-app-state',
    holds: 'Theme, the last onboarding step, and the name offered during setup.',
    personal: true,
  },
];

/** Everything, in one list. */
export const ALL_LOCAL_STORES: readonly LocalStore[] = [
  ...PENDING_QUEUES,
  ...CACHES,
  ...NOTIFICATION_MIRRORS,
  ...DRAFTS,
  ...CONTEXT,
];

/**
 * Keys that are deliberately *not* cleared, with why.
 *
 * The drift test requires every stored key in the source to be in one list or
 * the other, so leaving something behind is a decision somebody wrote down.
 */
export const KEPT_ON_SIGN_OUT: Readonly<Record<string, string>> = {
  'nura.auth.accessToken':
    'Cleared by the auth service itself, through secure storage rather than ' +
    'AsyncStorage. Listing it here would mean removing it twice.',
  'nura.auth.refreshToken':
    'Cleared by the auth service through secure storage, for the same reason ' +
    'as the access token above.',
};

/**
 * Removes every local store on sign-out.
 *
 * Deliberately tolerant: a key that is already absent, or a storage layer that
 * throws, must not stop the rest being removed. Sign-out has to finish even
 * when something goes wrong, because the alternative is an app that looks
 * signed in when it is not -- which is the reason `useSignOut` already clears
 * its state inside a `finally`.
 */
export async function clearLocalData(): Promise<number> {
  const keys = ALL_LOCAL_STORES.map((store) => store.key);
  try {
    await AsyncStorage.multiRemove(keys);
    return keys.length;
  } catch {
    // Fall back to one at a time, so one bad key does not keep the rest.
    let removed = 0;
    for (const key of keys) {
      try {
        await AsyncStorage.removeItem(key);
        removed += 1;
      } catch {
        // Nothing useful to do, and nothing worth logging: the key name is
        // all this could say, and the caller is already on its way out.
      }
    }
    return removed;
  }
}

/** The personal subset, for a message that says what will go. */
export function personalStoreCount(): number {
  return ALL_LOCAL_STORES.filter((store) => store.personal).length;
}
