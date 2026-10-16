/**
 * The routine list (PRD 12, sections 12, 13, 20 and 60's RoutinesScreen).
 *
 * Also what the Care tab's Routines card opens, which is why it is a list of
 * cards rather than rows: a routine's useful state is how today's run is
 * going, and that does not fit on a row.
 *
 * **Nothing here prescribes a routine.** Sections 15 and 24: a person creates
 * one they or their clinician decided on, and a routine that arrived through a
 * caregiver suggestion they approved says so on its card.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import { RoutineCard } from '../../src/features/productivity/components/DailyLifeRows';
import {
  ADD_ROUTINE,
  NO_ROUTINES,
  NO_ROUTINES_HINT,
} from '../../src/features/productivity/copy';
import {
  useRoutines,
  useSyncPendingDailyLife,
} from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

export default function RoutinesScreen() {
  const router = useRouter();
  const routines = useRoutines();
  useSyncPendingDailyLife();

  const data = routines.data;

  return (
    <Screen
      onRefresh={() => void routines.refetch()}
      refreshing={routines.isRefetching && !routines.isLoading}
    >
      <AsyncState
        status={routines.isError ? 'error' : data ? 'success' : 'loading'}
        error={routines.error}
        onRetry={() => void routines.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            {data.routines.length === 0 ? (
              <Card style={{ gap: spacing.xxs }}>
                <AppText variant="body" tone="secondary">
                  {NO_ROUTINES}
                </AppText>
                <AppText variant="caption" tone="secondary">
                  {NO_ROUTINES_HINT}
                </AppText>
              </Card>
            ) : (
              data.routines.map((routine) => (
                <RoutineCard
                  key={routine.id}
                  routine={routine}
                  onOpen={() =>
                    router.push({
                      pathname: '/daily/routine/[id]',
                      params: { id: routine.id },
                    })
                  }
                />
              ))
            )}

            <Button
              label={ADD_ROUTINE}
              onPress={() => router.push('/daily/routine-form')}
              accessibilityHint="Opens the new routine form"
            />
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
