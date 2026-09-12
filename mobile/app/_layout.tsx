/**
 * Root layout: the providers every screen depends on, in the order they depend
 * on each other.
 *
 *   SafeAreaProvider   -- inset measurements
 *   QueryClientProvider -- server state (PRD 0, section 14)
 *   ThemeProvider      -- Light / Dark / System (PRD 0, section 11)
 *
 * The splash screen is held until the persisted theme preference has been read
 * back from disk, so the app never paints the wrong theme and then snaps to the
 * stored one.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useAppStore } from '../src/store/appStore';
import { ThemeProvider, useTheme } from '../src/theme';

// Keep the native splash up until we are ready to render (see AppShell below).
void SplashScreen.preventAutoHideAsync();

/**
 * One client for the app's lifetime. Defaults are conservative: a single
 * retry, and no refetch on window focus since this is a mobile app.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppShell() {
  const theme = useTheme();
  const hasHydrated = useAppStore((state) => state.hasHydrated);

  useEffect(() => {
    if (hasHydrated) {
      void SplashScreen.hideAsync();
    }
  }, [hasHydrated]);

  if (!hasHydrated) {
    // Native splash is still covering the screen at this point.
    return null;
  }

  return (
    <>
      <StatusBar style={theme.isDark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          // Avoids a flash of the wrong colour during screen transitions.
          contentStyle: { backgroundColor: theme.colors.background },
          headerStyle: { backgroundColor: theme.colors.background },
          headerTintColor: theme.colors.textPrimary,
          headerTitleStyle: { color: theme.colors.textPrimary },
          headerShadowVisible: false,
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="appearance" options={{ title: 'Appearance' }} />
      </Stack>
    </>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <AppShell />
        </ThemeProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
