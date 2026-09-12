/**
 * Global app state (PRD 0, section 14).
 *
 * Zustand holds only app-wide preferences and session facts. Server data is
 * *not* kept here -- that is TanStack Query's job (see src/services/api).
 *
 * What persists to disk: the theme preference and the selected device, via
 * AsyncStorage. What deliberately does not: the auth session. Tokens belong in
 * secure storage (PRD 0, section 18), so `session` is in-memory only and is
 * repopulated on launch by the auth service.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { OnboardingStatus } from '../types/account';
import type { AuthSession, AuthStatus } from '../types/auth';
import type { ThemePreference } from '../theme/themes';

interface AppState {
  /** Appearance choice from More -> Appearance. Defaults to following the OS. */
  themePreference: ThemePreference;
  setThemePreference: (preference: ThemePreference) => void;

  /** Which paired Nura the app is currently showing. No pairing UI in PRD 0. */
  selectedDeviceId: string | null;
  setSelectedDeviceId: (deviceId: string | null) => void;

  /** Null whenever signed out. Populated only by a genuine provider session. */
  session: AuthSession | null;
  setSession: (session: AuthSession | null) => void;

  /** Where authentication currently stands (PRD 1, section 9). */
  authStatus: AuthStatus;
  setAuthStatus: (status: AuthStatus) => void;

  /**
   * Last onboarding status the backend reported, kept on disk so a relaunch
   * routes straight to the right step instead of waiting on the network, and
   * so a brief outage does not lose the user's place (PRD 1, section 38).
   * The server remains authoritative; this is only a routing hint.
   */
  lastOnboardingStatus: OnboardingStatus | null;
  setLastOnboardingStatus: (status: OnboardingStatus | null) => void;

  /**
   * A display name the provider offered during sign-in, used to prefill the
   * profile step. Apple shares a name only on the very first sign-in
   * (PRD 1, section 13), so it is captured then and held in memory until the
   * profile form reads it. Never persisted.
   */
  suggestedName: string | null;
  setSuggestedName: (name: string | null) => void;

  /**
   * False until persisted values have been read back from disk. The root
   * layout holds the splash screen until this flips, so the app never paints
   * the wrong theme for a frame and then snaps to the stored one.
   */
  hasHydrated: boolean;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      themePreference: 'system',
      setThemePreference: (preference) => set({ themePreference: preference }),

      selectedDeviceId: null,
      setSelectedDeviceId: (deviceId) => set({ selectedDeviceId: deviceId }),

      session: null,
      setSession: (session) => set({ session }),

      authStatus: 'unknown',
      setAuthStatus: (status) => set({ authStatus: status }),

      lastOnboardingStatus: null,
      setLastOnboardingStatus: (status) => set({ lastOnboardingStatus: status }),

      suggestedName: null,
      setSuggestedName: (name) => set({ suggestedName: name }),

      hasHydrated: false,
    }),
    {
      name: 'nura-app-state',
      storage: createJSONStorage(() => AsyncStorage),
      /** Only these keys reach disk. */
      partialize: (state) => ({
        themePreference: state.themePreference,
        selectedDeviceId: state.selectedDeviceId,
        lastOnboardingStatus: state.lastOnboardingStatus,
      }),
      onRehydrateStorage: () => () => {
        useAppStore.setState({ hasHydrated: true });
      },
    }
  )
);
