/**
 * Server state for the account and onboarding progress (PRD 1, sections 30-31).
 *
 * TanStack Query owns fetching and caching. The last known onboarding status
 * is also mirrored into the persisted store, so a relaunch can route straight
 * to the right step instead of showing a spinner while the network answers --
 * and so a brief backend outage does not lose a user's place
 * (PRD 1, section 38).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  createProfile,
  fetchAccount,
  fetchOnboarding,
  updateOnboarding,
  updateProfile,
  updateSettings,
  type OnboardingPatch,
  type ProfilePayload,
  type SettingsPatch,
} from '../services/api/account';
import { useAppStore } from '../store/appStore';
import type { Account, OnboardingProgress, OnboardingStatus } from '../types/account';

export const accountQueryKey = ['account', 'me'] as const;
export const onboardingQueryKey = ['account', 'onboarding'] as const;

/**
 * The onboarding steps a user can be resumed to. A literal union rather than
 * `string`, so expo-router's typed routes still catch a bad path here.
 */
export type OnboardingRoute =
  '/setup-mode' | '/profile' | '/preferences' | '/consent' | '/ready';

/**
 * Where a user with this status should resume (PRD 1, section 30).
 * `null` means onboarding is done and the main app should be shown.
 */
export function routeForStatus(status: OnboardingStatus): OnboardingRoute | null {
  switch (status) {
    case 'not_started':
    case 'authenticated':
      return '/setup-mode';
    case 'setup_mode_selected':
      return '/profile';
    case 'basic_profile_complete':
      return '/preferences';
    case 'preferences_complete':
      return '/consent';
    case 'consent_complete':
      return '/ready';
    case 'ready_for_pairing':
    case 'onboarding_complete':
      return null;
  }
}

export function useAccount() {
  const authStatus = useAppStore((state) => state.authStatus);
  return useQuery<Account>({
    queryKey: accountQueryKey,
    queryFn: ({ signal }) => fetchAccount(signal),
    // These endpoints require a bearer token; asking while signed out would
    // only produce 401s.
    enabled: authStatus === 'authenticated',
    retry: 1,
  });
}

export function useOnboarding() {
  const rememberStatus = useAppStore((state) => state.setLastOnboardingStatus);
  const authStatus = useAppStore((state) => state.authStatus);

  return useQuery<OnboardingProgress>({
    queryKey: onboardingQueryKey,
    enabled: authStatus === 'authenticated',
    queryFn: async ({ signal }) => {
      const progress = await fetchOnboarding(signal);
      // Mirror it so the next launch can route immediately.
      rememberStatus(progress.status);
      return progress;
    },
    retry: 1,
  });
}

/** Invalidates both account and onboarding after any change. */
function useRefreshOnboarding() {
  const queryClient = useQueryClient();
  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: accountQueryKey }),
      queryClient.invalidateQueries({ queryKey: onboardingQueryKey }),
    ]);
  };
}

export function useUpdateOnboarding() {
  const refresh = useRefreshOnboarding();
  const rememberStatus = useAppStore((state) => state.setLastOnboardingStatus);

  return useMutation({
    mutationFn: (patch: OnboardingPatch) => updateOnboarding(patch),
    onSuccess: async (progress) => {
      rememberStatus(progress.status);
      await refresh();
    },
  });
}

export function useUpdateSettings() {
  const refresh = useRefreshOnboarding();
  return useMutation({
    mutationFn: (patch: SettingsPatch) => updateSettings(patch),
    onSuccess: refresh,
  });
}

export function useCreateProfile() {
  const refresh = useRefreshOnboarding();
  return useMutation({
    mutationFn: (payload: ProfilePayload) => createProfile(payload),
    onSuccess: refresh,
  });
}

export function useUpdateProfile() {
  const refresh = useRefreshOnboarding();
  return useMutation({
    mutationFn: ({ id, ...payload }: ProfilePayload & { id: string }) =>
      updateProfile(id, payload),
    onSuccess: refresh,
  });
}
