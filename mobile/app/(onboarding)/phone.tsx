/**
 * Phone sign-in with a one-time code (PRD 1, section 11).
 *
 * Two stages on one screen: enter a number, then enter the code. A code is
 * only ever sent when someone taps the button -- nothing here triggers an SMS
 * automatically, which matters because sending costs money and providers rate
 * limit it. Resending is behind a visible cooldown.
 */
import { useRouter } from 'expo-router';
import { getLocales } from 'expo-localization';
import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  TextField,
} from '../../src/components';
import { COUNTRIES, countryForRegion } from '../../src/constants/countries';
import { AuthError } from '../../src/services/auth/authErrors';
import { AuthService } from '../../src/services/auth/authService';
import { useAppStore } from '../../src/store/appStore';
import { spacing } from '../../src/theme/tokens';
import { toE164, validateOtp, validatePhoneNumber } from '../../src/utils/validation';

/** Seconds before "Resend code" becomes available again. */
const RESEND_COOLDOWN_SECONDS = 60;

export default function PhoneAuthScreen() {
  const router = useRouter();
  const setAuthStatus = useAppStore((state) => state.setAuthStatus);

  const deviceRegion = useMemo(() => getLocales()[0]?.regionCode ?? null, []);
  const [country, setCountry] = useState(() => countryForRegion(deviceRegion));
  const [showCountryPicker, setShowCountryPicker] = useState(false);

  const [nationalNumber, setNationalNumber] = useState('');
  const [code, setCode] = useState('');
  const [stage, setStage] = useState<'number' | 'code'>('number');

  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  // The number the code was actually sent to, so editing the field afterwards
  // cannot verify against a different number than the one used.
  const sentTo = useRef<string | null>(null);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const phoneError = submitted
    ? validatePhoneNumber(country.dialling, nationalNumber)
    : null;
  const codeError = submitted && stage === 'code' ? validateOtp(code) : null;

  async function sendCode() {
    if (busy || cooldown > 0) return;
    setSubmitted(true);
    setError(null);
    setNotice(null);

    if (validatePhoneNumber(country.dialling, nationalNumber)) return;

    const e164 = toE164(country.dialling, nationalNumber);
    setBusy(true);
    try {
      await AuthService.sendPhoneOtp(e164);
      sentTo.current = e164;
      setStage('code');
      setSubmitted(false);
      setCooldown(RESEND_COOLDOWN_SECONDS);
      setNotice(`We sent a 6-digit code to ${e164}.`);
    } catch (caught) {
      const authError =
        caught instanceof AuthError ? caught : new AuthError('unknown', caught);
      setError(authError.message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (busy) return;
    setSubmitted(true);
    setError(null);

    if (validateOtp(code) || !sentTo.current) return;

    setBusy(true);
    setAuthStatus('authenticating');
    try {
      await AuthService.verifyPhoneOtp(sentTo.current, code.replace(/\D/g, ''));
      // Session established; routing happens centrally.
    } catch (caught) {
      const authError =
        caught instanceof AuthError ? caught : new AuthError('unknown', caught);
      setAuthStatus('unauthenticated');
      setError(authError.message);
      // An expired code is worth a fresh send rather than more guesses.
      if (authError.kind === 'expiredCode') {
        setCooldown(0);
      }
    } finally {
      setBusy(false);
    }
  }

  if (showCountryPicker) {
    return (
      <Screen>
        <AppText variant="title" style={{ marginBottom: spacing.md }}>
          Country or region
        </AppText>
        <ListGroup>
          {COUNTRIES.map((option) => (
            <ListRow
              key={option.code}
              label={option.name}
              value={`+${option.dialling}`}
              role="radio"
              selected={option.code === country.code}
              onPress={() => {
                setCountry(option);
                setShowCountryPicker(false);
              }}
            />
          ))}
        </ListGroup>
      </Screen>
    );
  }

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        {stage === 'number' ? 'What is your phone number?' : 'Enter your code'}
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        {stage === 'number'
          ? 'We will text you a 6-digit code to sign in.'
          : 'It can take a moment to arrive.'}
      </AppText>

      {error ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {error}
          </AppText>
        </Card>
      ) : null}

      {notice && stage === 'code' ? (
        <Card style={{ marginBottom: spacing.md }}>
          <AppText variant="body" accessibilityLiveRegion="polite">
            {notice}
          </AppText>
        </Card>
      ) : null}

      {stage === 'number' ? (
        <View style={{ gap: spacing.md }}>
          <ListGroup>
            <ListRow
              label="Country or region"
              value={`${country.name} +${country.dialling}`}
              showChevron
              onPress={() => setShowCountryPicker(true)}
              accessibilityHint="Choose your dialling code"
            />
          </ListGroup>

          <TextField
            label="Phone number"
            value={nationalNumber}
            onChangeText={setNationalNumber}
            error={phoneError}
            hint={`Your number will be used as +${country.dialling}…`}
            keyboardType="phone-pad"
            autoComplete="tel"
            textContentType="telephoneNumber"
            inputMode="tel"
          />

          <Button
            label={busy ? 'Sending code…' : 'Send code'}
            onPress={sendCode}
            disabled={busy}
            accessibilityHint="Sends a one-time code by text message"
          />
        </View>
      ) : (
        <View style={{ gap: spacing.md }}>
          <TextField
            label="6-digit code"
            value={code}
            onChangeText={setCode}
            error={codeError}
            keyboardType="number-pad"
            autoComplete="sms-otp"
            textContentType="oneTimeCode"
            inputMode="numeric"
            maxLength={6}
          />

          <Button
            label={busy ? 'Verifying…' : 'Verify and continue'}
            onPress={verify}
            disabled={busy}
          />

          <Button
            label={cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
            variant="ghost"
            onPress={sendCode}
            disabled={busy || cooldown > 0}
          />

          <Button
            label="Use a different number"
            variant="ghost"
            onPress={() => {
              setStage('number');
              setCode('');
              setSubmitted(false);
              setError(null);
            }}
            disabled={busy}
          />
        </View>
      )}

      <Button
        label="Use a different method"
        variant="ghost"
        onPress={() => router.back()}
        disabled={busy}
        style={{ marginTop: spacing.md }}
      />
    </Screen>
  );
}
