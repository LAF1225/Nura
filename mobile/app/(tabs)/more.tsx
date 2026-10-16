/**
 * More (PRD 0 section 8; PRD 1 section 45).
 *
 * Account, device settings, notifications and support all belong here
 * eventually. So far it holds Tasks & routines (PRD 12, section 19),
 * Customize Today, Appearance, Nura Device (PRD 11, section 46), Privacy &
 * Security (PRD 13, section 4) and signing out -- no disabled placeholders for
 * features that do not exist yet.
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
            label="Tasks & routines"
            description="Your list, reminders, alarms and routines"
            leadingIcon="checkmark-done-outline"
            showChevron
            onPress={() => router.push('/daily')}
            accessibilityHint="Opens tasks, reminders, alarms and routines"
          />
          <ListRow
            label="Customize Today"
            description="Choose which cards appear"
            leadingIcon="options-outline"
            showChevron
            onPress={() => router.push('/customize-today')}
            accessibilityHint="Opens Today screen settings"
          />
          <ListRow
            label="Appearance"
            description="Light, Dark or System"
            leadingIcon="color-palette-outline"
            showChevron
            onPress={() => router.push('/appearance')}
            accessibilityHint="Opens theme settings"
          />
          <ListRow
            label="Nura Device"
            description="How Nura looks and behaves"
            leadingIcon="hardware-chip-outline"
            showChevron
            onPress={() => router.push('/robot')}
            accessibilityHint="Opens settings for Nura's own screen and sounds"
          />
          <ListRow
            label="Privacy & Security"
            description="What Nura stores, who can see it, and your data"
            leadingIcon="lock-closed-outline"
            showChevron
            onPress={() => router.push('/privacy')}
            accessibilityHint="Opens privacy settings, data export and deletion"
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
