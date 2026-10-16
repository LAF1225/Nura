/**
 * Safety history (PRD 10, section 49).
 *
 * Newest first, each row saying what was observed and how it ended. The
 * labels are the server's, so "Possible fall" cannot become "Fall" on the way
 * to a screen (sections 16 and 52).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Screen } from '../../src/components';
import { SafetyEventRow } from '../../src/features/safety/components/SafetyCards';
import { HISTORY_EMPTY, HISTORY_TITLE } from '../../src/features/safety/copy';
import { useSafetyEvents } from '../../src/features/safety/hooks';
import { spacing } from '../../src/theme/tokens';

export default function SafetyHistoryScreen() {
  const router = useRouter();
  const events = useSafetyEvents();
  const rows = events.data ?? [];

  return (
    <Screen
      onRefresh={() => void events.refetch()}
      refreshing={events.isRefetching && !events.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {HISTORY_TITLE}
        </AppText>
        <AsyncState
          status={events.isError ? 'error' : events.data ? 'success' : 'loading'}
          error={events.error}
          isEmpty={rows.length === 0}
          emptyMessage={HISTORY_EMPTY}
          loadingLabel="Loading safety history"
          onRetry={() => void events.refetch()}
        >
          <View style={{ gap: spacing.xs }}>
            {rows.map((event) => (
              <SafetyEventRow
                key={event.id}
                event={event}
                onPress={() => router.push(`/safety/${event.id}`)}
              />
            ))}
          </View>
        </AsyncState>
      </View>
    </Screen>
  );
}
