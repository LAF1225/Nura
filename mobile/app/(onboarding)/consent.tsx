/**
 * Privacy introduction and consent (PRD 1, sections 26 and 27).
 *
 * The two acknowledgements are separate controls on purpose -- PRD 1 forbids
 * merging them into one unclear checkbox. Neither is pre-ticked, and the
 * server independently refuses to complete onboarding without both, so this
 * screen is a real gate rather than a decorative one.
 *
 * Health-specific consent is not collected here. That belongs with the health
 * features themselves, in a later PRD.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { Linking, View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Checkbox,
  Screen,
  StepIndicator,
} from '../../src/components';
import { useUpdateOnboarding } from '../../src/hooks/useOnboarding';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

/**
 * Placeholder legal links, clearly marked as not production-ready
 * (PRD 1, section 26). Replace before any real release.
 */
const TERMS_URL = 'https://example.com/nura/terms-placeholder';
const PRIVACY_URL = 'https://example.com/nura/privacy-placeholder';

const PRIVACY_POINTS = [
  'Your information belongs to you.',
  'Nura uses your data to provide the features you choose.',
  'You control what caregivers can access.',
  'Health and personal information is not shared without your permission.',
  'You can review privacy settings from the app at any time.',
];

export default function ConsentScreen() {
  const router = useRouter();
  const updateOnboarding = useUpdateOnboarding();

  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [acknowledgedPrivacy, setAcknowledgedPrivacy] = useState(false);

  const bothGiven = acceptedTerms && acknowledgedPrivacy;
  const busy = updateOnboarding.isPending;

  async function submit() {
    if (!bothGiven || busy) return;
    try {
      await updateOnboarding.mutateAsync({
        acceptTerms: true,
        acknowledgePrivacy: true,
        status: 'consent_complete',
      });
      await updateOnboarding.mutateAsync({ status: 'ready_for_pairing' });
      router.push('/ready');
    } catch {
      // Shown from the mutation error state below.
    }
  }

  return (
    <Screen>
      <StepIndicator step={4} totalSteps={5} />

      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        Your privacy
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        A short summary before we finish setting up.
      </AppText>

      <Card style={{ gap: spacing.sm }}>
        {PRIVACY_POINTS.map((point) => (
          <AppText key={point} variant="body">
            {point}
          </AppText>
        ))}
      </Card>

      <Card style={{ marginTop: spacing.md, gap: spacing.xs }}>
        <AppText variant="bodyStrong" tone="warning">
          Placeholder documents
        </AppText>
        <AppText variant="caption" tone="secondary">
          The Terms and Privacy Policy linked below are placeholders for development and
          are not the real documents. They must be replaced before any public release.
        </AppText>
      </Card>

      <View style={{ marginTop: spacing.lg, gap: spacing.xs }}>
        <Checkbox
          label="I agree to the Terms of Service"
          checked={acceptedTerms}
          onChange={setAcceptedTerms}
        >
          <AppText variant="body">
            I agree to the{' '}
            <AppText
              variant="body"
              tone="accent"
              accessibilityRole="link"
              onPress={() => Linking.openURL(TERMS_URL)}
            >
              Terms of Service
            </AppText>
          </AppText>
        </Checkbox>

        <Checkbox
          label="I acknowledge the Privacy Policy"
          checked={acknowledgedPrivacy}
          onChange={setAcknowledgedPrivacy}
        >
          <AppText variant="body">
            I acknowledge the{' '}
            <AppText
              variant="body"
              tone="accent"
              accessibilityRole="link"
              onPress={() => Linking.openURL(PRIVACY_URL)}
            >
              Privacy Policy
            </AppText>
          </AppText>
        </Checkbox>
      </View>

      {updateOnboarding.isError ? (
        <Card style={{ marginTop: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(updateOnboarding.error)}
          </AppText>
        </Card>
      ) : null}

      <Button
        label={busy ? 'Saving…' : 'Agree and continue'}
        onPress={submit}
        disabled={!bothGiven || busy}
        accessibilityHint={
          bothGiven ? 'Completes setup' : 'Tick both acknowledgements above to continue'
        }
        style={{ marginTop: spacing.xl }}
      />
    </Screen>
  );
}
