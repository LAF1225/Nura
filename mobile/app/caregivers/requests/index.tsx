/**
 * Care requests waiting for the primary user (PRD 9, sections 86, 87 and 88).
 *
 * Nothing here applies anything. The list is a way in to Review, and the only
 * thing that changes a record is Approve on the next screen -- which is the same
 * boundary PRD 8 drew around the assistant's one write, for the same reason.
 *
 * Answered requests stay in the list below the waiting ones. A caregiver who
 * suggested something should be able to see it was declined (section 88), and the
 * primary user should be able to see what they agreed to last week.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Screen } from '../../../src/components';
import { SuggestionCard } from '../../../src/features/caregivers/components/CaregiverCards';
import {
  SUGGESTIONS_EMPTY,
  SUGGESTIONS_INTRO,
} from '../../../src/features/caregivers/copy';
import { useSuggestions } from '../../../src/features/caregivers/hooks';
import { spacing } from '../../../src/theme/tokens';

export default function CareRequestsScreen() {
  const router = useRouter();
  const suggestions = useSuggestions();
  const rows = suggestions.data?.suggestions ?? [];
  const waiting = rows.filter((row) => row.status === 'pending');
  const answered = rows.filter((row) => row.status !== 'pending');

  return (
    <Screen
      onRefresh={() => void suggestions.refetch()}
      refreshing={suggestions.isRefetching && !suggestions.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {SUGGESTIONS_INTRO}
        </AppText>

        <AsyncState
          status={suggestions.isError ? 'error' : 'success'}
          error={suggestions.error}
          isEmpty={rows.length === 0}
          emptyMessage={SUGGESTIONS_EMPTY}
          loadingLabel="Loading care requests"
          onRetry={() => void suggestions.refetch()}
        >
          <View style={{ gap: spacing.md }}>
            {waiting.map((suggestion) => (
              <SuggestionCard
                key={suggestion.id}
                suggestion={suggestion}
                onPress={() => router.push(`/caregivers/requests/${suggestion.id}`)}
              />
            ))}

            {answered.length > 0 ? (
              <AppText variant="bodyStrong" accessibilityRole="header">
                Already answered
              </AppText>
            ) : null}
            {answered.map((suggestion) => (
              <SuggestionCard key={suggestion.id} suggestion={suggestion} />
            ))}
          </View>
        </AsyncState>
      </View>
    </Screen>
  );
}
