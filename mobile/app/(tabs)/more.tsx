/**
 * More (PRD 0 section 8; PRD 1 section 45).
 *
 * Account, privacy, device settings, notifications, data management and
 * support all belong here eventually. So far it holds Appearance and signing
 * out -- no disabled placeholders for features that do not exist yet.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, ListGroup, ListRow, Screen } from '../../src/components';
import { config } from '../../src/constants/config';
import { useAccount } from '../../src/hooks/useOnboarding';
import { useSignOut } from '../../src/hooks/useSignOut';
import { useAppStore } from '../../src/store/appStore';
import { spacing } from '../../src/theme/tokens';

export default function MoreScreen() {
  const router = useRouter();
  const { signOut, isPending } = useSignOut();
  const session = useAppStore((state) => state.session);
  const account = useAccount();

  // Prefer the name the user chose over the address they signed up with.
  const selfProfile = account.data?.profiles.find((profile) => profile.role === 'self');
  const identity = selfProfile?.preferredName ?? session?.email ?? session?.phone ?? null;

  return (
    <Screen>
      <AppText variant="title" style={{ marginBottom: spacing.md }}>
        More
      </AppText>

      <View style={{ gap: spacing.lg }}>
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

        {session ? (
          <ListGroup>
            <ListRow
              label={isPending ? 'Signing out…' : 'Sign out'}
              description={identity ?? undefined}
              leadingIcon="log-out-outline"
              onPress={isPending ? undefined : () => void signOut()}
              accessibilityHint="Signs you out of Nura on this device"
            />
          </ListGroup>
        ) : null}
      </View>

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
