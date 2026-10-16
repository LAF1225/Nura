/**
 * Which person the app is currently about (PRD 9, sections 16, 57 and 58).
 *
 * An account may be using Nura for itself, supporting one or more other people,
 * or both. This store holds which of those contexts is on screen -- and nothing
 * else, because that is the only thing the client is allowed to decide. What the
 * context *grants* comes from the server on every request (section 62).
 *
 * **The stored value is a choice, not a credential.** It is a profile id the
 * account has already been shown in `/caregiver/profiles`. Setting it grants
 * nothing: every request still resolves the relationship server-side, and a
 * context whose relationship was revoked a moment ago fails the same way it
 * would if the id had been typed in by hand (section 52).
 *
 * **Switching clears the previous person's data, rather than refetching over
 * it.** Section 58 says not to briefly display the prior profile's data, and
 * `invalidate` would do exactly that: the old rows stay in the cache, rendered,
 * until the new ones arrive. `clearProfileScopedQueries` *removes* them, so the
 * next screen starts from a loading state. That is the whole reason this module
 * knows about the query client at all.
 *
 * **It is persisted.** Somebody who switched to their mother should come back to
 * their mother. On the way back in, `useCareMode` checks the stored id against
 * the profiles the server currently lists and falls back to `self` if it is not
 * there -- so a revoked relationship cannot leave the app pointed at somebody it
 * can no longer read.
 */
import type { QueryClient } from '@tanstack/react-query';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

/** Whose Nura is on screen. */
export type CareContext =
  { kind: 'self' } | { kind: 'caregiver'; profileId: string; relationshipId: string };

export const SELF_CONTEXT: CareContext = { kind: 'self' };

interface ModeState {
  context: CareContext;
  /** False until the persisted choice has been read back from disk. */
  hydrated: boolean;

  setContext: (context: CareContext) => void;
  /** Back to the account's own Nura. */
  reset: () => void;
}

export const useCareModeStore = create<ModeState>()(
  persist(
    (set) => ({
      context: SELF_CONTEXT,
      hydrated: false,

      setContext: (context) => set({ context }),
      reset: () => set({ context: SELF_CONTEXT }),
    }),
    {
      name: 'nura-care-mode',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({ context: state.context }),
      onRehydrateStorage: () => () => {
        useCareModeStore.setState({ hydrated: true });
      },
    }
  )
);

/**
 * The query key prefixes that are about one particular person.
 *
 * Everything here is removed on a context switch. Deliberately a list rather
 * than a wildcard: `removeQueries()` with no filter would also drop the account
 * itself and the supported-profile list, which are what the switcher is built
 * from -- so switching would blank the screen that did the switching.
 *
 * **PRD 13 found this list badly out of date, and the gap was not where it
 * looked.** The obvious half was PRD 10's and PRD 12's keys, added after this
 * list was last touched. The rest was worse: keys from PRD 3, PRD 5, PRD 6 and
 * PRD 7 had never been here either, and `health-summary`/`health-records` were
 * here but matched nothing -- the real keys are `['health', 'summary', …]`, and
 * a prefix is compared element by element. So switching from one supported
 * person to another left the previous person's health record, dose history,
 * adherence figures, symptom entries, appointment questions, doctor reports,
 * check-in, safety status, tasks and routines rendered from cache. That is
 * precisely what PRD 13 section 40 exists to prevent.
 *
 * Twenty-six keys were added or corrected. None of them was found by reading
 * the list: `cacheIsolation.test.ts` reads every `queryKey` literal out of the
 * feature modules and fails if one is neither here nor in the documented
 * account-scoped list below, and it asserts the reverse too -- a key here that
 * nothing declares is the mistake that made `health-summary` useless. A
 * hand-maintained list that nothing checks is a list that is already wrong.
 */
export const PROFILE_SCOPED_KEY_PREFIXES: readonly string[] = [
  // PRD 3 to PRD 9.
  'caregiver-home',
  'caregivers',
  'care-summary',
  'caregiver-suggestions',
  'family-threads',
  'family-thread',
  'emergency-contacts',
  'today',
  // `['health', 'summary', profileId]` and `['health', 'records', ...]`, so the
  // prefix is `health`. It read `health-summary` and `health-records` until
  // PRD 13, which matched nothing: a prefix is compared element by element, so
  // the whole health record stayed in the cache across a profile switch. The
  // orphan check in `cacheIsolation.test.ts` is what found it, and is why that
  // test asserts in both directions rather than only that the list is covered.
  'health',
  'medication-schedules',
  'medication-doses',
  'medication-supply',
  'symptom-episodes',
  'symptom-summary',
  'appointments',
  'appointment',
  'appointment-summary',
  'assistant-home',
  'assistant-conversations',
  'assistant-conversation',
  'assistant-preferences',
  'assistant-memories',
  // PRD 10. A safety event names a time, a place in somebody's day and who was
  // contacted; of everything on this list it is the least acceptable to show
  // against the wrong name.
  'safety-status',
  'safety-capabilities',
  'safety-events',
  'safety-event',
  'safety-alerts',
  // PRD 12.
  'tasks',
  'reminders',
  'reminder-occurrences',
  'alarms',
  'routines',
  'routine',
  'routine-runs',
  'routine-run',
  'daily-life',
  'external-capabilities',
  'care-routines',
  // PRD 13. The privacy hub reads caregivers, memory counts and the export
  // state, all per profile.
  'privacy-summary',
  'privacy-exports',
  'privacy-deletion-inventory',
  // --- found by the drift test, not by reading the list -------------------
  // PRD 3.
  'daily-checkin',
  'dashboard-preferences',
  // PRD 5. An adherence figure and a dose history are as personal as the
  // schedule they come from.
  'medication-adherence',
  'medication-history',
  // PRD 6.
  'symptom-episode',
  'symptom-entries',
  'symptom-photo-source',
  // PRD 7. A doctor report is the single most sensitive thing Nura generates.
  'appointment-questions',
  'appointment-preparation',
  'appointment-report',
  'appointment-reports',
];

/**
 * Keys that are *not* about one profile, with why.
 *
 * The drift test reads every `queryKey` literal in the feature modules and
 * requires each one to be in this list or the one above. That is what makes
 * the decision explicit: a key added by a later PRD fails the test until
 * somebody has said which it is.
 *
 * PRD 11's four robot keys are scoped by **device id**, not profile. A device
 * is claimed by an account, no caregiver route reaches one, and the Nura Device
 * screen is the account holder's own -- so switching which person is on screen
 * does not change which robot is theirs. Signing out clears them along with
 * everything else, because `queryClient.clear()` takes the whole cache.
 */
export const ACCOUNT_SCOPED_KEY_PREFIXES: Readonly<Record<string, string>> = {
  account: 'The signed-in account itself. The profile switcher is built from it.',
  onboarding: 'Account-level progress through setup, not about one person.',
  'supported-profiles':
    'The list of people this account supports. Removing it would blank the ' +
    'screen that does the switching.',
  'caregiver-permission-catalogue':
    "The server's own descriptions of the permission categories. The same " +
    'for every account, and nothing in it is about anybody.',
  'caregiver-invitation':
    'An invitation looked up by its token, before any relationship exists. ' +
    'It belongs to the accepting account, which has no profile yet.',
  devices:
    'Robots this account claimed. A device is claimed by an account, so ' +
    'switching which person is on screen does not change which robot is ' +
    'theirs.',
  'robot-status':
    'PRD 11: keyed by device id rather than profile id, for the reason above. ' +
    'Signing out clears it along with the whole cache.',
  'robot-capabilities': 'PRD 11: keyed by device id. See robot-status.',
  'robot-preferences': 'PRD 11: keyed by device id. See robot-status.',
  'robot-history': 'PRD 11: keyed by device id. See robot-status.',
  productivity:
    'Device-local pending actions, read from this phone-s own storage rather ' +
    'than from the server. Cleared on sign-out by clearLocalData instead.',
  notifications:
    "The operating system's notification permission for this install. A " +
    'property of the phone, not of the person using it.',
  system:
    'Whether the backend is reachable and its minimum app version. Neither ' +
    'depends on who is signed in.',
};

/**
 * Drops everything cached about whoever was on screen before.
 *
 * `removeQueries`, not `invalidateQueries`: section 58 forbids briefly showing
 * the previous profile's data, and an invalidated query keeps serving its old
 * value while it refetches. Removing means the next render is a loading state,
 * which is the honest thing for a screen that does not yet know anything about
 * this person.
 */
export function clearProfileScopedQueries(client: QueryClient): void {
  for (const prefix of PROFILE_SCOPED_KEY_PREFIXES) {
    client.removeQueries({ queryKey: [prefix] });
  }
}
