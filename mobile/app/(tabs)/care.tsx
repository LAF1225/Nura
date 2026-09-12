/**
 * Care -- placeholder for PRD 0 (section 8).
 *
 * Future purpose: medication schedules, appointments, caregivers, routines,
 * family communication and safety monitoring.
 */
import { AppText, Card, Screen } from '../../src/components';
import { spacing } from '../../src/theme/tokens';

export default function CareScreen() {
  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        Care
      </AppText>
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          Schedules, appointments, routines and the people who help care for you will live
          here.
        </AppText>
        <AppText variant="caption" tone="secondary">
          No reminders or caregivers are set up yet.
        </AppText>
      </Card>
    </Screen>
  );
}
