/**
 * Health -- still deliberately minimal (PRD 3, section 34).
 *
 * The timeline, conditions, measurements and reports arrive in PRD 4 and
 * later. All this shows now is the one health-adjacent thing that genuinely
 * exists: how many days this week have a check-in. A count, not a trend --
 * charts and correlations are ruled out until there is clinical care behind
 * them (PRD 3, section 12).
 */
import { AppText, Card, Screen } from '../../src/components';
import { useToday } from '../../src/hooks/useToday';
import { spacing } from '../../src/theme/tokens';

export default function HealthScreen() {
  const today = useToday();
  const checkIn = today.data?.dailyCheckIn;

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        Health
      </AppText>

      {checkIn && checkIn.recentCompletedCount > 0 ? (
        <Card style={{ gap: spacing.xxs, marginBottom: spacing.md }}>
          <AppText variant="bodyStrong">This week</AppText>
          <AppText variant="body" tone="secondary">
            {checkIn.recentCompletedCount === 1
              ? '1 check-in completed'
              : `${checkIn.recentCompletedCount} check-ins completed`}
          </AppText>
        </Card>
      ) : null}

      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          Your health timeline, conditions, measurements and reports will live here.
        </AppText>
        <AppText variant="caption" tone="secondary">
          Nothing beyond your daily check-ins is being recorded yet.
        </AppText>
      </Card>
    </Screen>
  );
}
