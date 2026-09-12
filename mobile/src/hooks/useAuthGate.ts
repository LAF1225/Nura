/**
 * Decides which part of the app someone should be in (PRD 1, section 6).
 *
 *   no session                  -> the welcome/auth screens
 *   session, onboarding partway -> resume at the step they stopped on
 *   session, onboarding done    -> the main five-tab app
 *
 * A user who has already onboarded is never sent through it again
 * (PRD 1, section 6), and someone halfway through is never dropped at the
 * start.
 */
import { useRouter, useSegments } from 'expo-router';
import { useEffect } from 'react';

import { useAppStore } from '../store/appStore';
import { routeForStatus, useOnboarding } from './useOnboarding';

/**
 * Screens shown before a session exists. Reaching one of these while signed in
 * means the sign-in just succeeded, so the user should move on to their step.
 */
const PRE_AUTH_SCREENS = ['welcome', 'sign-in', 'email', 'phone'];

export function useAuthGate(): void {
  const router = useRouter();
  const segments = useSegments();

  const hasHydrated = useAppStore((state) => state.hasHydrated);
  const authStatus = useAppStore((state) => state.authStatus);
  const lastOnboardingStatus = useAppStore((state) => state.lastOnboardingStatus);

  const onboarding = useOnboarding();

  useEffect(() => {
    // Wait until stored state is loaded and auth has settled. `authenticating`
    // is a transient state during a sign-in attempt and must not cause a jump.
    if (!hasHydrated || authStatus === 'unknown' || authStatus === 'authenticating') {
      return;
    }

    const group = segments[0];
    const screen = segments[1];
    const inOnboarding = group === '(onboarding)';
    const onPreAuthScreen = inOnboarding && PRE_AUTH_SCREENS.includes(screen ?? '');

    if (authStatus !== 'authenticated') {
      if (!onPreAuthScreen) {
        router.replace('/welcome');
      }
      return;
    }

    // Signed in. Prefer the server's answer; fall back to the last one we saw
    // so a slow or unreachable backend does not strand the user on a spinner.
    const status = onboarding.data?.status ?? lastOnboardingStatus;
    if (!status) {
      return;
    }

    const nextRoute = routeForStatus(status);

    if (nextRoute) {
      // Only redirect when they are somewhere they should not be: outside
      // onboarding entirely, or still on a sign-in screen. Otherwise leave
      // them alone so they can move through the steps themselves and use the
      // back button (PRD 1, section 44).
      if (!inOnboarding || onPreAuthScreen) {
        router.replace(nextRoute);
      }
      return;
    }

    // Onboarding finished: the main app, not the onboarding stack.
    if (inOnboarding) {
      router.replace('/');
    }
  }, [
    hasHydrated,
    authStatus,
    onboarding.data?.status,
    lastOnboardingStatus,
    segments,
    router,
  ]);
}
