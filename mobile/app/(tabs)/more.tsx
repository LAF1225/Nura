/**
 * More (PRD 0, section 8).
 *
 * Account, privacy, device settings, notifications, data management and
 * support all belong here eventually. PRD 0 implements Appearance only, so
 * that is the single row -- no disabled placeholders for features that do not
 * exist yet.
 */
import { useRouter } from 'expo-router';

import { AppText, ListGroup, ListRow, Screen } from '../../src/components';
import { config } from '../../src/constants/config';
import { spacing } from '../../src/theme/tokens';

export default function MoreScreen() {
  const router = useRouter();

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        More
      </AppText>

      <ListGroup>
        <ListRow
          label="Appearance"
          description="Light, Dark or System"
          leadingIcon="color-palette-outline"
          showChevron
          onPress={() => router.push('/appearance')}
          accessibilityHint="Opens theme settings"
        />
      </ListGroup>

      <AppText
        variant="caption"
        tone="secondary"
        style={{ marginTop: spacing.lg, textAlign: 'center' }}
      >
        Nura {config.appVersion}
      </AppText>
    </Screen>
  );
}
