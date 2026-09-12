/**
 * Health -- placeholder for PRD 0 (section 8).
 *
 * Future purpose: timeline, conditions, symptoms, medications, medical
 * history, measurements and reports. Nothing is tracked or stored yet, and the
 * copy says so plainly rather than implying features that do not exist.
 */
import { AppText, Card, Screen } from '../../src/components';
import { spacing } from '../../src/theme/tokens';

export default function HealthScreen() {
  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        Health
      </AppText>
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="body" tone="secondary">
          Your health timeline, conditions, measurements and reports will live here.
        </AppText>
        <AppText variant="caption" tone="secondary">
          Nothing is being recorded yet.
        </AppText>
      </Card>
    </Screen>
  );
}
