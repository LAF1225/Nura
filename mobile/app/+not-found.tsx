/**
 * Shown for any route that does not exist, so a bad link never dumps a raw
 * error in front of someone (PRD 0, section 20).
 */
import { useRouter } from 'expo-router';

import { AppText, Button, Card, Screen } from '../src/components';
import { spacing } from '../src/theme/tokens';

export default function NotFoundScreen() {
  const router = useRouter();

  return (
    <Screen>
      <Card style={{ gap: spacing.md }}>
        <AppText variant="heading">This screen does not exist</AppText>
        <AppText variant="body" tone="secondary">
          The link you followed may be out of date.
        </AppText>
        <Button label="Go to Today" onPress={() => router.replace('/')} />
      </Card>
    </Screen>
  );
}
