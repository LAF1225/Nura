/**
 * Signing out (PRD 1, sections 15 and 45; PRD 13, section 39).
 *
 * Clearing the provider session is not enough on its own: the cached account
 * and onboarding data, and the routing hint on disk, all have to go too.
 * Otherwise the next person to open the app would briefly see the previous
 * user's details, or be routed to their onboarding step.
 *
 * **PRD 13 found that only half of it went.** `queryClient.clear()` empties
 * the in-memory cache, and the Zustand setters below reset the account state --
 * but seventeen AsyncStorage keys and seven persisted stores stayed on disk, so
 * a second person signing in on the same phone inherited the previous one's
 * symptom draft, caregiver message drafts, assistant composer, Today cache and
 * every offline queue. `clearLocalData` is the inventory, and section 39 is the
 * requirement it satisfies.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

import { clearLocalData } from '../features/privacy/localData';
import { AuthService } from '../services/auth/authService';
import { useAppStore } from '../store/appStore';
import { createLogger } from '../utils/logger';

const log = createLogger('auth');

export function useSignOut() {
  const queryClient = useQueryClient();
  const [isPending, setIsPending] = useState(false);

  const signOut = useCallback(async () => {
    setIsPending(true);
    try {
      await AuthService.signOut();
    } catch (error) {
      // Even if the provider call fails -- offline, say -- local state must
      // still be cleared, or the app would look signed in when it is not.
      log.warn('sign-out request failed; clearing local state anyway', {
        message: String(error),
      });
    } finally {
      const store = useAppStore.getState();
      store.setSession(null);
      store.setAuthStatus('unauthenticated');
      store.setLastOnboardingStatus(null);
      store.setSuggestedName(null);
      queryClient.clear();
      // On disk as well as in memory (PRD 13, section 39). Awaited inside the
      // `finally` so the app is not navigated away from a signed-out state
      // while somebody's drafts are still being removed; `clearLocalData`
      // never throws, for the same reason this whole block is a `finally`.
      const removed = await clearLocalData();
      log.info('cleared local data on sign-out', { stores: removed });
      setIsPending(false);
    }
  }, [queryClient]);

  return { signOut, isPending };
}
