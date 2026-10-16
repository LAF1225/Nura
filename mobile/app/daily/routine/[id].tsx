/**
 * One routine: its steps, its schedule, and today's run.
 *
 * PRD 12, sections 12, 13, 14 and 60's RoutineDetailScreen.
 *
 * **Today's run is the top of the screen**, because that is what somebody
 * opened this for -- and if the routine does not run today it says so rather
 * than showing an empty checklist.
 *
 * Pause keeps the routine and stops the runs (section 13). Archive keeps the
 * history, which is what somebody usually means by "stop this"; Delete is
 * separate and says what it removes.
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../../src/components';
import { RoutineStepRow } from '../../../src/features/productivity/components/DailyLifeRows';
import {
  COMPLETE_RUN,
  NO_RUN_TODAY,
  PAUSE,
  RESUME,
  SKIP,
} from '../../../src/features/productivity/copy';
import {
  useArchiveRoutine,
  useClearStep,
  useCompleteStep,
  useDeleteRoutine,
  useRoutine,
  useRunAction,
  useSetRoutinePaused,
} from '../../../src/features/productivity/hooks';
import { spacing } from '../../../src/theme/tokens';

export default function RoutineDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const routineId = typeof params.id === 'string' ? params.id : null;

  const routine = useRoutine(routineId);
  const complete = useCompleteStep();
  const clear = useClearStep();
  const runAct = useRunAction();
  const pause = useSetRoutinePaused();
  const archive = useArchiveRoutine();
  const remove = useDeleteRoutine();

  const data = routine.data;
  const run = data?.todayRun ?? null;
  const completionFor = (stepId: string) =>
    run?.completions.find((row) => row.stepId === stepId) ?? null;

  return (
    <Screen
      onRefresh={() => void routine.refetch()}
      refreshing={routine.isRefetching && !routine.isLoading}
    >
      <AsyncState
        status={routine.isError ? 'error' : data ? 'success' : 'loading'}
        error={routine.error}
        onRetry={() => void routine.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.xxs }}>
              <AppText variant="title">{data.title}</AppText>
              <AppText variant="body" tone="secondary">
                {data.scheduleLabel}
              </AppText>
              {data.description ? (
                <AppText variant="body" tone="secondary">
                  {data.description}
                </AppText>
              ) : null}
              <AppText variant="caption" tone="secondary">
                {data.statusLabel}
                {data.source !== 'user' ? ` · ${data.sourceLabel}` : ''}
              </AppText>
            </Card>

            {run === null ? (
              <Card>
                <AppText variant="body" tone="secondary">
                  {NO_RUN_TODAY}
                </AppText>
              </Card>
            ) : (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading">Today</AppText>
                <AppText variant="body" tone="secondary">
                  {run.progressLabel}
                </AppText>

                {data.steps.map((step) => {
                  const completion = completionFor(step.id);
                  return (
                    <RoutineStepRow
                      key={step.id}
                      step={step}
                      completion={completion}
                      onToggle={() => {
                        if (completion !== null) {
                          clear.mutate({ runId: run.id, stepId: step.id });
                          return;
                        }
                        complete.mutate({ runId: run.id, stepId: step.id });
                      }}
                      onSkip={
                        step.optional
                          ? () =>
                              complete.mutate({
                                runId: run.id,
                                stepId: step.id,
                                state: 'skipped',
                              })
                          : undefined
                      }
                    />
                  );
                })}

                <View style={{ gap: spacing.sm }}>
                  <Button
                    label={COMPLETE_RUN}
                    onPress={() => runAct.mutate({ runId: run.id, action: 'complete' })}
                    accessibilityHint="Marks today's routine done"
                  />
                  <Button
                    label={SKIP}
                    variant="secondary"
                    onPress={() => runAct.mutate({ runId: run.id, action: 'skip' })}
                    accessibilityHint="Records that today's routine is not happening"
                  />
                </View>
              </Card>
            )}

            <Card style={{ gap: spacing.sm }}>
              <AppText variant="heading">Steps</AppText>
              {data.steps.map((step, index) => (
                <AppText key={step.id} variant="body" tone="secondary">
                  {index + 1}. {step.title}
                  {step.optional ? ' (optional)' : ''}
                </AppText>
              ))}
              <Button
                label="Edit routine"
                variant="secondary"
                onPress={() =>
                  router.push({
                    pathname: '/daily/routine-form',
                    params: { id: data.id },
                  })
                }
                accessibilityHint="Opens this routine for editing"
              />
            </Card>

            <View style={{ gap: spacing.sm }}>
              <Button
                label={data.status === 'paused' ? RESUME : PAUSE}
                variant="secondary"
                onPress={() =>
                  pause.mutate({
                    routineId: data.id,
                    paused: data.status !== 'paused',
                  })
                }
                accessibilityHint="Stops or restarts this routine"
              />
              <Button
                label="Archive"
                variant="ghost"
                onPress={() =>
                  archive.mutate(data.id, { onSuccess: () => router.back() })
                }
                accessibilityHint="Stops this routine and keeps its history"
              />
              <Button
                label="Delete"
                variant="ghost"
                onPress={() => remove.mutate(data.id, { onSuccess: () => router.back() })}
                accessibilityHint="Removes this routine and everything it recorded"
              />
            </View>
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
