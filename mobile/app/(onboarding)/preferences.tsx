/**
 * Comfort and accessibility preferences (PRD 1, sections 22-25).
 *
 * Nobody is asked to disclose or label a disability. These are plainly worded
 * comfort settings, all optional and all off by default.
 *
 * The notifications explainer from PRD 1 section 24 lives here as a short card
 * rather than as its own step, which keeps the flow to five steps
 * (PRD 1, section 29). It only explains -- no OS permission is requested,
 * because permissions are asked for when the feature is first used
 * (PRD 1, section 25).
 *
 * Appearance is deliberately not repeated here. PRD 1 section 23 allows
 * leaving it under More -> Appearance rather than lengthening onboarding.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  StepIndicator,
  ToggleRow,
} from '../../src/components';
import { useUpdateOnboarding, useUpdateSettings } from '../../src/hooks/useOnboarding';
import { apiErrorMessage } from '../../src/services/api';
import { useTheme } from '../../src/theme';
import { radius, spacing } from '../../src/theme/tokens';

interface PreferenceState {
  largerText: boolean;
  highContrast: boolean;
  reduceMotion: boolean;
  voiceFirstPreference: boolean;
  simplifiedInterface: boolean;
}

export default function PreferencesScreen() {
  const router = useRouter();
  const theme = useTheme();
  const updateSettings = useUpdateSettings();
  const updateOnboarding = useUpdateOnboarding();

  const [preferences, setPreferences] = useState<PreferenceState>({
    largerText: false,
    highContrast: false,
    reduceMotion: false,
    voiceFirstPreference: false,
    simplifiedInterface: false,
  });

  const busy = updateSettings.isPending || updateOnboarding.isPending;
  const failure = updateSettings.error ?? updateOnboarding.error;

  function set<K extends keyof PreferenceState>(key: K, value: boolean) {
    setPreferences((current) => ({ ...current, [key]: value }));
  }

  async function submit() {
    if (busy) return;
    try {
      await updateSettings.mutateAsync(preferences);
      await updateOnboarding.mutateAsync({ status: 'preferences_complete' });
      router.push('/consent');
    } catch {
      // Shown from the mutation error state below.
    }
  }

  return (
    <Screen>
      <StepIndicator step={3} totalSteps={5} />

      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        Make Nura comfortable to use
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        All optional, and you can change any of these later.
      </AppText>

      <View
        style={{
          backgroundColor: theme.colors.surface,
          borderRadius: radius.lg,
          borderWidth: 1,
          borderColor: theme.colors.border,
          overflow: 'hidden',
        }}
      >
        <ToggleRow
          label="Larger text"
          description="Increase text size throughout the app."
          value={preferences.largerText}
          onChange={(value) => set('largerText', value)}
        />
        <ToggleRow
          label="Higher contrast"
          description="Stronger contrast between text and backgrounds."
          value={preferences.highContrast}
          onChange={(value) => set('highContrast', value)}
        />
        <ToggleRow
          label="Reduce motion"
          description="Keep animations to a minimum."
          value={preferences.reduceMotion}
          onChange={(value) => set('reduceMotion', value)}
        />
        <ToggleRow
          label="Prefer voice"
          description="Lead with voice interaction where it is available."
          value={preferences.voiceFirstPreference}
          onChange={(value) => set('voiceFirstPreference', value)}
        />
        <ToggleRow
          label="Simplified interface"
          description="Fewer options on screen at once."
          value={preferences.simplifiedInterface}
          onChange={(value) => set('simplifiedInterface', value)}
        />
      </View>

      <AppText variant="caption" tone="secondary" style={{ marginTop: spacing.sm }}>
        Light and Dark appearance is under More, then Appearance.
      </AppText>

      {/* Notifications explainer -- nothing is requested yet. */}
      <Card style={{ marginTop: spacing.lg, gap: spacing.xs }}>
        <AppText variant="bodyStrong">Staying up to date</AppText>
        <AppText variant="body" tone="secondary">
          Nura can later remind you about medications, appointments, routines and
          important care events. We will ask for permission when you set the first one up,
          not before.
        </AppText>
      </Card>

      {failure ? (
        <Card style={{ marginTop: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(failure)}
          </AppText>
        </Card>
      ) : null}

      <Button
        label={busy ? 'Saving your preferences…' : 'Continue'}
        onPress={submit}
        disabled={busy}
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
