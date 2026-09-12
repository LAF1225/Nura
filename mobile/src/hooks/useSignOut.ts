/**
 * Signing out (PRD 1, sections 15 and 45).
 *
 * Clearing the provider session is not enough on its own: the cached account
 * and onboarding data, and the routing hint on disk, all have to go too.
 * Otherwise the next person to open the app would briefly see the previous
 * user's details, or be routed to their onboarding step.
 */
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useState } from 'react';

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
      setIsPending(false);
    }
  }, [queryClient]);

  return { signOut, isPending };
}
