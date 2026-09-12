/**
 * Makes the active theme available to the tree (PRD 0, section 11).
 *
 * The active theme is derived from two inputs: the user's stored preference
 * and the device appearance. When the preference is `system`, React Native's
 * `useColorScheme()` drives it, so flipping the phone between Light and Dark
 * updates Nura immediately without any extra wiring.
 */
import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { useAppStore } from '../store/appStore';
import { getTheme, lightTheme, resolveThemeName, type Theme } from './themes';

const ThemeContext = createContext<Theme>(lightTheme);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const preference = useAppStore((state) => state.themePreference);
  const systemScheme = useColorScheme();

  const theme = useMemo(
    () => getTheme(resolveThemeName(preference, systemScheme)),
    [preference, systemScheme]
  );

  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

/** The theme that should render right now. */
export function useTheme(): Theme {
  return useContext(ThemeContext);
}
