/**
 * Choosing how to sign in (PRD 1, sections 8, 9 and 52).
 *
 * Order follows the PRD: Apple and Google first where available, then phone
 * and email as fallbacks. A provider that is not configured is shown as
 * unavailable with the reason -- it is never offered as a button that
 * pretends to work.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Platform, View } from 'react-native';

import { AppText, Button, Card, Screen } from '../../src/components';
import { AuthService } from '../../src/services/auth/authService';
import { AuthError } from '../../src/services/auth/authErrors';
import { useAppStore } from '../../src/store/appStore';
import { useTheme } from '../../src/theme';
import { spacing } from '../../src/theme/tokens';

function Divider({ label }: { label: string }) {
  const theme = useTheme();
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}
    >
      <View style={{ flex: 1, height: 1, backgroundColor: theme.colors.border }} />
      <AppText variant="caption" tone="secondary">
        {label}
      </AppText>
      <View style={{ flex: 1, height: 1, backgroundColor: theme.colors.border }} />
    </View>
  );
}

export default function SignInScreen() {
  const router = useRouter();
  const setSuggestedName = useAppStore((state) => state.setSuggestedName);
  const setAuthStatus = useAppStore((state) => state.setAuthStatus);

  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const configured = AuthService.isConfigured();
  const providers = AuthService.availableProviders();

  /** Shared handler for the two OAuth buttons. */
  async function runOAuth(provider: 'apple' | 'google') {
    // Guards against a double tap firing two provider sheets.
    if (busyProvider) return;

    setBusyProvider(provider);
    setError(null);
    setAuthStatus('authenticating');
    try {
      const result =
        provider === 'apple'
          ? await AuthService.signInWithApple()
          : await AuthService.signInWithGoogle();

      // Apple shares a name only on first sign-in; keep it for the profile step.
      if (result.suggestedName) {
        setSuggestedName(result.suggestedName);
      }
      // Routing is handled centrally once the session lands.
    } catch (caught) {
      const authError =
        caught instanceof AuthError ? caught : new AuthError('unknown', caught);
      setAuthStatus('unauthenticated');
      // Backing out of the sheet is normal, not something to shout about.
      setError(authError.kind === 'cancelled' ? null : authError.message);
    } finally {
      setBusyProvider(null);
    }
  }

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        Sign in to Nura
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.xl }}>
        Use whichever option suits you. You can add another way to sign in later.
      </AppText>

      {!configured ? (
        <Card style={{ gap: spacing.sm, marginBottom: spacing.lg }}>
          <AppText variant="bodyStrong" tone="warning">
            Sign-in is not configured in this build
          </AppText>
          <AppText variant="caption" tone="secondary">
            Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY to mobile/.env,
            then restart the app. Setup steps are in the README.
          </AppText>
        </Card>
      ) : null}

      {error ? (
        <Card style={{ marginBottom: spacing.lg }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {error}
          </AppText>
        </Card>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        {/* Apple first on iOS, as the platform expects. */}
        {Platform.OS === 'ios' ? (
          <Button
            label={busyProvider === 'apple' ? 'Signing in…' : 'Continue with Apple'}
            onPress={() => runOAuth('apple')}
            disabled={!providers.includes('apple') || busyProvider !== null}
            accessibilityHint="Signs in using your Apple ID"
          />
        ) : null}

        <Button
          label={busyProvider === 'google' ? 'Signing in…' : 'Continue with Google'}
          variant={Platform.OS === 'ios' ? 'secondary' : 'primary'}
          onPress={() => runOAuth('google')}
          disabled={!providers.includes('google') || busyProvider !== null}
          accessibilityHint="Signs in using your Google account"
        />

        {configured && !providers.includes('google') ? (
          <AppText variant="caption" tone="secondary">
            Google sign-in needs EXPO_PUBLIC_GOOGLE_CLIENT_ID to be set.
          </AppText>
        ) : null}

        <View style={{ marginVertical: spacing.sm }}>
          <Divider label="or" />
        </View>

        <Button
          label="Continue with phone"
          variant="secondary"
          onPress={() => router.push('/phone')}
          disabled={!providers.includes('phone') || busyProvider !== null}
          accessibilityHint="Sign in with a code sent by text message"
        />
        <Button
          label="Continue with email"
          variant="secondary"
          onPress={() => router.push('/email')}
          disabled={!providers.includes('email') || busyProvider !== null}
          accessibilityHint="Sign in or create an account with an email address"
        />
      </View>
    </Screen>
  );
}
