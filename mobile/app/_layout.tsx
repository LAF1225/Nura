/**
 * Root layout: the providers every screen depends on, in the order they depend
 * on each other.
 *
 *   SafeAreaProvider    -- inset measurements
 *   QueryClientProvider -- server state (PRD 0, section 14)
 *   ThemeProvider       -- Light / Dark / System (PRD 0, section 11)
 *
 * The splash screen is held until the persisted preferences have been read and
 * authentication has settled, so the app never paints the wrong theme or
 * flashes the welcome screen at someone who is already signed in.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { useAuthGate } from '../src/hooks/useAuthGate';
import { useAuthBootstrap } from '../src/services/auth/useAuthBootstrap';
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
  const authStatus = useAppStore((state) => state.authStatus);

  // Restores any stored session and keeps the API client supplied with a token.
  useAuthBootstrap();
  // Routes to welcome / the right onboarding step / the main app.
  useAuthGate();

  const ready = hasHydrated && authStatus !== 'unknown';

  useEffect(() => {
    if (ready) {
      void SplashScreen.hideAsync();
    }
  }, [ready]);

  if (!ready) {
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
        <Stack.Screen name="(onboarding)" options={{ headerShown: false }} />
        <Stack.Screen name="appearance" options={{ title: 'Appearance' }} />
        <Stack.Screen name="customize-today" options={{ title: '' }} />
        <Stack.Screen name="connect-device" options={{ title: '' }} />
        <Stack.Screen name="pairing" options={{ headerShown: false }} />
        <Stack.Screen name="devices/[id]" options={{ title: '' }} />
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
