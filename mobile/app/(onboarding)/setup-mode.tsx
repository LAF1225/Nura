/**
 * Who Nura is being set up for (PRD 1, sections 16 and 17).
 *
 * Wording matters here: no "patient" or "caregiver" at this point. The user is
 * only telling us whether they will be the person using Nura, and formal roles
 * and permissions come much later.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  Screen,
  SelectableCard,
  StepIndicator,
} from '../../src/components';
import { useUpdateOnboarding } from '../../src/hooks/useOnboarding';
import { useSignOut } from '../../src/hooks/useSignOut';
import { apiErrorMessage } from '../../src/services/api';
import type { SetupMode } from '../../src/types/account';
import { spacing } from '../../src/theme/tokens';

export default function SetupModeScreen() {
  const router = useRouter();
  const [choice, setChoice] = useState<SetupMode | null>(null);
  const updateOnboarding = useUpdateOnboarding();
  const { signOut, isPending: signingOut } = useSignOut();

  async function submit() {
    if (!choice || updateOnboarding.isPending) return;
    try {
      await updateOnboarding.mutateAsync({
        setupMode: choice,
        status: 'setup_mode_selected',
      });
      router.push('/profile');
    } catch {
      // Surfaced below from the mutation's error state.
    }
  }

  return (
    <Screen>
      <StepIndicator step={1} totalSteps={5} />

      <AppText variant="title" style={{ marginBottom: spacing.xs }}>
        Who are you setting up Nura for?
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.xl }}>
        You can change this later.
      </AppText>

      <View
        // Groups the two cards as one radio set for screen readers.
        accessibilityRole="radiogroup"
        style={{ gap: spacing.md }}
      >
        <SelectableCard
          title="For myself"
          description="I will be the primary person using Nura."
          icon="person-outline"
          selected={choice === 'self'}
          onPress={() => setChoice('self')}
        />
        <SelectableCard
          title="For someone else"
          description="I am helping a family member or another person set up Nura."
          icon="people-outline"
          selected={choice === 'assisted'}
          onPress={() => setChoice('assisted')}
        />
      </View>

      {updateOnboarding.isError ? (
        <Card style={{ marginTop: spacing.md }}>
          <AppText variant="body" tone="danger" accessibilityLiveRegion="polite">
            {apiErrorMessage(updateOnboarding.error)}
          </AppText>
        </Card>
      ) : null}

      <Button
        label={updateOnboarding.isPending ? 'Saving…' : 'Continue'}
        onPress={submit}
        disabled={!choice || updateOnboarding.isPending}
        style={{ marginTop: spacing.xl }}
      />

      {/* Quietly available in case someone signed in with the wrong account
          (PRD 1, section 45). */}
      <Button
        label={signingOut ? 'Signing out…' : 'Sign in with a different account'}
        variant="ghost"
        onPress={() => void signOut()}
        disabled={signingOut}
        style={{ marginTop: spacing.sm }}
      />
    </Screen>
  );
}
