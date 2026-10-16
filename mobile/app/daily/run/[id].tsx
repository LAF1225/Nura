/**
 * One routine run, step by step (PRD 12, sections 14, 39, 60's RoutineRunScreen).
 *
 * What Today's routine row opens: the checklist for right now, with nothing
 * else on the screen. The detail screen can also tick steps, and this exists
 * because somebody arriving from Today wants the steps and not the routine's
 * settings.
 *
 * **A tick works offline.** `useCompleteStep` queues the completion with a
 * client id if the request cannot go, and `(run, step)` is unique on the
 * server -- so a retry cannot invent progress (section 39).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../../src/components';
import { RoutineStepRow } from '../../../src/features/productivity/components/DailyLifeRows';
import { COMPLETE_RUN, SKIP } from '../../../src/features/productivity/copy';
import {
  useClearStep,
  useCompleteStep,
  useRoutine,
  useRun,
  useRunAction,
} from '../../../src/features/productivity/hooks';
import { spacing } from '../../../src/theme/tokens';

export default function RoutineRunScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string }>();
  const runId = typeof params.id === 'string' ? params.id : null;

  const run = useRun(runId);
  const routine = useRoutine(run.data?.routineId ?? null);
  const complete = useCompleteStep();
  const clear = useClearStep();
  const runAct = useRunAction();

  const data = run.data;
  const steps = routine.data?.steps ?? [];
  const completionFor = (stepId: string) =>
    data?.completions.find((row) => row.stepId === stepId) ?? null;

  return (
    <Screen
      onRefresh={() => void run.refetch()}
      refreshing={run.isRefetching && !run.isLoading}
    >
      <AsyncState
        status={run.isError ? 'error' : data ? 'success' : 'loading'}
        error={run.error}
        onRetry={() => void run.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <Card style={{ gap: spacing.xxs }}>
              <AppText variant="title">{data.routineTitle}</AppText>
              <AppText variant="body" tone="secondary">
                {data.progressLabel}
              </AppText>
              <AppText variant="caption" tone="secondary">
                {data.statusLabel}
              </AppText>
            </Card>

            <Card style={{ gap: spacing.sm }}>
              {steps.map((step) => {
                const completion = completionFor(step.id);
                return (
                  <RoutineStepRow
                    key={step.id}
                    step={step}
                    completion={completion}
                    onToggle={() => {
                      if (completion !== null) {
                        clear.mutate({ runId: data.id, stepId: step.id });
                        return;
                      }
                      complete.mutate({ runId: data.id, stepId: step.id });
                    }}
                    onSkip={
                      step.optional
                        ? () =>
                            complete.mutate({
                              runId: data.id,
                              stepId: step.id,
                              state: 'skipped',
                            })
                        : undefined
                    }
                  />
                );
              })}
            </Card>

            <View style={{ gap: spacing.sm }}>
              <Button
                label={COMPLETE_RUN}
                onPress={() => runAct.mutate({ runId: data.id, action: 'complete' })}
                accessibilityHint="Marks today's routine done"
              />
              <Button
                label={SKIP}
                variant="secondary"
                onPress={() => runAct.mutate({ runId: data.id, action: 'skip' })}
                accessibilityHint="Records that today's routine is not happening"
              />
              <Button
                label="Open the routine"
                variant="ghost"
                onPress={() =>
                  router.push({
                    pathname: '/daily/routine/[id]',
                    params: { id: data.routineId },
                  })
                }
                accessibilityHint="Opens this routine's settings"
              />
            </View>
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
