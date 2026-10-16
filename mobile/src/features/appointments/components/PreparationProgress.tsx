/**
 * Where somebody is in the preparation sequence (PRD 7, sections 13 and 62).
 *
 * PRD 7 section 13 lays the flow out as a sequence, and this is the sequence made
 * visible. Deliberately not a gate: every step is optional and any of them can be
 * revisited, so this shows position rather than permission.
 *
 * `StepIndicator` already exists from PRD 1's onboarding and does exactly this
 * job, accessibly -- a label a screen reader reads and a bar marked decorative so
 * progress is not announced twice. Reusing it keeps one implementation of
 * "step 3 of 4" in the app, and adds a line naming the step so the number means
 * something.
 */
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { StepIndicator } from '../../../components/StepIndicator';
import { spacing } from '../../../theme/tokens';

/** The steps, in PRD 7 section 13's own order. */
export const PREPARATION_STEPS = [
  { key: 'review', label: 'Review what you have recorded' },
  { key: 'questions', label: 'Add questions for the clinician' },
  { key: 'choose', label: 'Choose what to include' },
  { key: 'preview', label: 'Preview and export' },
] as const;

export type PreparationStepKey = (typeof PREPARATION_STEPS)[number]['key'];

interface PreparationProgressProps {
  current: PreparationStepKey;
}

export function PreparationProgress({ current }: PreparationProgressProps) {
  const index = PREPARATION_STEPS.findIndex((step) => step.key === current);
  const step = index < 0 ? 1 : index + 1;

  return (
    <View style={{ gap: spacing.xxs }}>
      <StepIndicator step={step} totalSteps={PREPARATION_STEPS.length} />
      <AppText variant="bodyStrong">
        {PREPARATION_STEPS[step - 1]?.label ?? PREPARATION_STEPS[0].label}
      </AppText>
    </View>
  );
}
