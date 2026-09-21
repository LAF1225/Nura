/**
 * The optional Health profile card on Today (PRD 4, section 47).
 *
 * Off by default, and enabled from More → Customize Today. It shows a
 * percentage and a way in, and **never a condition, medication or allergy
 * name** -- Today is the screen most likely to be glanced at by someone else
 * in the room (PRD 4, sections 33 and 47).
 */
import { useRouter } from 'expo-router';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { SkeletonCard } from '../../../components/Skeleton';
import { spacing } from '../../../theme/tokens';
import { useHealthSummary } from '../hooks';
import { Completeness } from './Completeness';

export function HealthProfileCard() {
  const router = useRouter();
  const summary = useHealthSummary();

  if (summary.isLoading) {
    return (
      <Card>
        <SkeletonCard lines={2} label="Loading your health profile" />
      </Card>
    );
  }

  // An error here is not worth a red box on Today: the Health tab will say so
  // properly. The card simply stands down.
  if (!summary.data) return null;

  const { percent, completedSections, totalSections, status } = summary.data;
  const notStarted = status === 'not_started';

  return (
    <Card style={{ gap: spacing.sm }}>
      <AppText variant="heading">Health profile</AppText>

      {notStarted ? (
        <AppText variant="body" tone="secondary">
          Add your conditions, medications and allergies whenever you like. You can do a
          little at a time.
        </AppText>
      ) : (
        <>
          <AppText variant="body" tone="secondary">
            {percent}% filled in
          </AppText>
          <Completeness
            percent={percent}
            completedSections={completedSections}
            totalSections={totalSections}
          />
        </>
      )}

      <Button
        label={notStarted ? 'Start health setup' : 'Continue setup'}
        variant="secondary"
        onPress={() => router.push('/health/setup')}
        accessibilityHint="Opens your health profile"
      />
    </Card>
  );
}
