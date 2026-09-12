/**
 * Email sign-up and sign-in (PRD 1, section 10).
 *
 * One screen with two modes rather than two near-identical screens. Validation
 * runs on submit and then live, so nobody is told they are wrong before they
 * have finished typing.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, Screen, TextField } from '../../src/components';
import { AuthError } from '../../src/services/auth/authErrors';
import { AuthService } from '../../src/services/auth/authService';
import { useAppStore } from '../../src/store/appStore';
import { spacing } from '../../src/theme/tokens';
import {
  MIN_PASSWORD_LENGTH,
  validateEmail,
  validatePassword,
  validatePasswordConfirmation,
} from '../../src/utils/validation';

type Mode = 'signIn' | 'signUp';

export default function EmailAuthScreen() {
  const router = useRouter();
  const setAuthStatus = useAppStore((state) => state.setAuthStatus);

  const [mode, setMode] = useState<Mode>('signUp');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');

  // Validation messages only appear after a submit attempt.
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const emailError = submitted ? validateEmail(email) : null;
  const passwordError = submitted ? validatePassword(password) : null;
  const confirmationError =
    submitted && mode === 'signUp'
      ? validatePasswordConfirmation(password, confirmation)
      : null;

  function switchMode(next: Mode) {
    setMode(next);
    setSubmitted(false);
    setFormError(null);
    setNotice(null);
  }

  async function submit() {
    // Guard against a second tap while a request is in flight
    // (PRD 1, section 39).
    if (busy) return;
    setSubmitted(true);
    setFormError(null);
    setNotice(null);

    const problems = [
      validateEmail(email),
      validatePassword(password),
      mode === 'signUp' ? validatePasswordConfirmation(password, confirmation) : null,
    ].filter(Boolean);
    if (problems.length > 0) {
      return;
    }

    setBusy(true);
    setAuthStatus('authenticating');
    try {
      if (mode === 'signUp') {
        const session = await AuthService.signUpWithEmail(email, password);
        if (!session) {
          // The project requires email confirmation. The account exists but is
          // not usable yet, so say exactly that rather than implying success.
          setAuthStatus('unauthenticated');
          setNotice(
            'Check your inbox to confirm your email address, then come back and sign in.'
          );
          setMode('signIn');
          return;
        }
      } else {
        await AuthService.signInWithEmail(email, password);
      }
      // A real session now exists; routing happens centrally.
    } catch (caught) {
      const error =
        caught instanceof AuthError ? caught : new AuthError('unknown', caught);
      setAuthStatus('unauthenticated');
      setFormError(error.message);
      if (error.kind === 'emailAlreadyRegistered') {
        setMode('signIn');
      }
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (busy) return;
    const problem = validateEmail(email);
    if (problem) {
      setSubmitted(true);
      return;
    }
    setBusy(true);
    setFormError(null);
    try {
      await AuthService.sendPasswordReset(email);
      // Worded so it does not reveal whether the address is registered.
      setNotice('If that address has an account, a reset link is on its way.');
    } catch (caught) {
      const error =
        caught instanceof AuthError ? caught : new AuthError('unknown', caught);
      setFormError(error.message);
    } finally {
      setBusy(false);
    }
  }

  const busyLabel = mode === 'signUp' ? 'Creating your account…' : 'Signing in…';
  const actionLabel = mode === 'signUp' ? 'Create account' : 'Sign in';

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.lg }}>
        {mode === 'signUp' ? 'Create your account' : 'Sign in'}
      </AppText>

      {formError ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {formError}
          </AppText>
        </Card>
      ) : null}

      {notice ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="body" accessibilityLiveRegion="polite">
            {notice}
          </AppText>
        </Card>
      ) : null}

      <View style={{ gap: spacing.md }}>
        <TextField
          label="Email"
          value={email}
          onChangeText={setEmail}
          error={emailError}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          textContentType="emailAddress"
          inputMode="email"
        />

        <TextField
          label="Password"
          value={password}
          onChangeText={setPassword}
          error={passwordError}
          hint={
            mode === 'signUp' ? `At least ${MIN_PASSWORD_LENGTH} characters.` : undefined
          }
          secureTextEntry
          autoCapitalize="none"
          autoComplete={mode === 'signUp' ? 'new-password' : 'current-password'}
          textContentType={mode === 'signUp' ? 'newPassword' : 'password'}
        />

        {mode === 'signUp' ? (
          <TextField
            label="Confirm password"
            value={confirmation}
            onChangeText={setConfirmation}
            error={confirmationError}
            secureTextEntry
            autoCapitalize="none"
            autoComplete="new-password"
            textContentType="newPassword"
          />
        ) : null}

        <Button
          label={busy ? busyLabel : actionLabel}
          onPress={submit}
          disabled={busy}
          accessibilityHint={
            mode === 'signUp'
              ? 'Creates your Nura account'
              : 'Signs you in to your Nura account'
          }
        />

        {mode === 'signIn' ? (
          <Button
            label="Forgot your password?"
            variant="ghost"
            onPress={resetPassword}
            disabled={busy}
          />
        ) : null}

        <Button
          label={
            mode === 'signUp' ? 'I already have an account' : 'Create an account instead'
          }
          variant="ghost"
          onPress={() => switchMode(mode === 'signUp' ? 'signIn' : 'signUp')}
          disabled={busy}
        />

        <Button
          label="Use a different method"
          variant="ghost"
          onPress={() => router.back()}
          disabled={busy}
        />
      </View>
    </Screen>
  );
}
