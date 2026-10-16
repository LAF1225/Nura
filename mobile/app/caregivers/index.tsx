/**
 * The caregiver list the primary user controls (PRD 9, sections 11, 53, 55, 83).
 *
 * Several caregivers, each with their own permissions, and an invitation that
 * has not been answered shown alongside them -- because to the person reading
 * this, "I asked Ayesha and she hasn't said yes yet" is part of the same list.
 *
 * What this screen never shows: anything about what a caregiver has *looked at*.
 * Section 49 says not to notify the user every time a caregiver views a permitted
 * category and section 50 not to build a feed of reads, so there is nothing here
 * that could become one.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import { CaregiverCard } from '../../src/features/caregivers/components/CaregiverCards';
import {
  CAREGIVERS_EMPTY,
  CAREGIVERS_EMPTY_HINT,
  CAREGIVERS_INTRO,
  pendingRequestsSentence,
} from '../../src/features/caregivers/copy';
import { PERMISSION_KEYS } from '../../src/features/caregivers/api';
import { useCaregivers, useCareSummary } from '../../src/features/caregivers/hooks';
import { spacing } from '../../src/theme/tokens';

export default function CaregiversScreen() {
  const router = useRouter();
  const caregivers = useCaregivers();
  const summary = useCareSummary();

  const rows = caregivers.data?.caregivers ?? [];
  const pending = summary.data?.pendingSuggestionCount ?? 0;

  return (
    <Screen
      onRefresh={() => {
        void caregivers.refetch();
        void summary.refetch();
      }}
      refreshing={caregivers.isRefetching && !caregivers.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {CAREGIVERS_INTRO}
        </AppText>

        {pending > 0 ? (
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="bodyStrong">{pendingRequestsSentence(pending)}</AppText>
            <Button
              label="Review"
              onPress={() => router.push('/caregivers/requests')}
              accessibilityHint="Opens the changes someone has suggested"
            />
          </Card>
        ) : null}

        <AsyncState
          status={caregivers.isError ? 'error' : 'success'}
          error={caregivers.error}
          isEmpty={rows.length === 0}
          emptyMessage={CAREGIVERS_EMPTY}
          loadingLabel="Loading caregivers"
          onRetry={() => void caregivers.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            {rows.map((caregiver) => (
              <CaregiverCard
                key={caregiver.id}
                caregiver={caregiver}
                total={PERMISSION_KEYS.length}
                onPress={() => router.push(`/caregivers/${caregiver.id}`)}
              />
            ))}
          </View>
        </AsyncState>

        <View style={{ gap: spacing.xs }}>
          <Button
            label="Invite someone"
            onPress={() => router.push('/caregivers/invite')}
            accessibilityHint="Opens the invitation form"
          />
          <Button
            label="Care notifications"
            variant="secondary"
            onPress={() => router.push('/caregivers/notifications')}
            accessibilityHint="Chooses what Nura tells you about"
          />
          {rows.length === 0 ? (
            <AppText variant="caption" tone="secondary">
              {CAREGIVERS_EMPTY_HINT}
            </AppText>
          ) : null}
        </View>
      </View>
    </Screen>
  );
}
