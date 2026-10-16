/**
 * The people this account supports, and switching between them.
 *
 * PRD 9, sections 16, 56, 57 and 58.
 *
 * The switcher. "My Nura" is always the first row, because an account that helps
 * somebody else is still allowed to be a person using Nura for themselves
 * (section 3).
 *
 * **Switching clears before it changes.** `useSwitchCareContext` removes the
 * previous person's cached queries and only then sets the new context, so the
 * next screen starts from a loading state rather than briefly showing one
 * person's medications under another's name (section 58).
 *
 * **A revoked relationship simply is not here.** The list comes from
 * `/caregiver/profiles`, which returns active relationships only, so somebody
 * whose access ended disappears on the next read (section 52).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Screen } from '../../src/components';
import {
  ProfileSwitcherRow,
  SupportedProfileCard,
} from '../../src/features/caregivers/components/CaregiverCards';
import {
  CAREGIVER_MODE,
  MY_NURA,
  SUPPORTED_EMPTY,
  SUPPORTED_TITLE,
} from '../../src/features/caregivers/copy';
import {
  useCareMode,
  useSupportedProfiles,
  useSwitchCareContext,
} from '../../src/features/caregivers/hooks';
import { SELF_CONTEXT } from '../../src/features/caregivers/modeStore';
import { spacing } from '../../src/theme/tokens';

export default function SupportedProfilesScreen() {
  const router = useRouter();
  const mode = useCareMode();
  const supported = useSupportedProfiles();
  const switchContext = useSwitchCareContext();
  const rows = supported.data ?? [];

  return (
    <Screen
      onRefresh={() => void supported.refetch()}
      refreshing={supported.isRefetching && !supported.isLoading}
    >
      <View style={{ gap: spacing.lg }}>
        <View style={{ gap: spacing.xxs }}>
          <AppText variant="bodyStrong" accessibilityRole="header">
            {CAREGIVER_MODE}
          </AppText>
          <ProfileSwitcherRow
            label={MY_NURA}
            description="Your own care"
            selected={!mode.isCaregiverMode}
            onPress={() => {
              switchContext(SELF_CONTEXT);
              router.replace('/(tabs)');
            }}
          />
        </View>

        <View style={{ gap: spacing.md }}>
          <AppText variant="bodyStrong" accessibilityRole="header">
            {SUPPORTED_TITLE}
          </AppText>

          <AsyncState
            status={supported.isError ? 'error' : 'success'}
            error={supported.error}
            isEmpty={rows.length === 0}
            emptyMessage={SUPPORTED_EMPTY}
            loadingLabel="Loading"
            onRetry={() => void supported.refetch()}
          >
            <View style={{ gap: spacing.md }}>
              {rows.map((profile) => (
                <SupportedProfileCard
                  key={profile.relationshipId}
                  profile={profile}
                  selected={
                    mode.isCaregiverMode &&
                    mode.relationship?.relationshipId === profile.relationshipId
                  }
                  onPress={() => {
                    switchContext({
                      kind: 'caregiver',
                      profileId: profile.profileId,
                      relationshipId: profile.relationshipId,
                    });
                    router.replace('/care-mode');
                  }}
                />
              ))}
            </View>
          </AsyncState>
        </View>
      </View>
    </Screen>
  );
}
