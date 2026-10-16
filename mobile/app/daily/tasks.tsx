/**
 * The task list (PRD 12, sections 5, 6 and 60's TasksScreen).
 *
 * Three decisions worth reading.
 *
 * **Done is one tap on the row, and Undo is the same tap again.** Section 6
 * asks for Complete, Undo, Archive and Delete; the first two are the ones
 * people do constantly, so they are the tick box, and the other two are behind
 * the task itself where a mistake costs nothing.
 *
 * **A queued action shows immediately.** `useTasks` overlays whatever is in
 * the offline queue, so a Done pressed with no signal stays done on the screen
 * and says "Saved on this phone" rather than reverting on the next refresh
 * (section 37).
 *
 * **Completed tasks are a separate list, not a struck-through pile.** The open
 * list is what somebody opened this for.
 */
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import { TaskRow } from '../../src/features/productivity/components/DailyLifeRows';
import { ADD_TASK, NO_TASKS, NO_TASKS_HINT } from '../../src/features/productivity/copy';
import {
  useSyncPendingDailyLife,
  useTaskAction,
  useTasks,
} from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

type Scope = 'open' | 'completed' | 'archived';

const SCOPE_LABELS: Record<Scope, string> = {
  open: 'To do',
  completed: 'Done',
  archived: 'Archived',
};

export default function TasksScreen() {
  const router = useRouter();
  const [scope, setScope] = useState<Scope>('open');
  const tasks = useTasks(scope);
  const action = useTaskAction();
  useSyncPendingDailyLife();

  const data = tasks.data;
  const rows = data?.tasks ?? [];

  return (
    <Screen
      onRefresh={() => void tasks.refetch()}
      refreshing={tasks.isRefetching && !tasks.isLoading}
    >
      <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
        {(Object.keys(SCOPE_LABELS) as Scope[]).map((key) => (
          <Button
            key={key}
            label={SCOPE_LABELS[key]}
            variant={scope === key ? 'primary' : 'ghost'}
            onPress={() => setScope(key)}
            accessibilityHint={`Shows ${SCOPE_LABELS[key].toLowerCase()} tasks`}
          />
        ))}
      </View>

      <View style={{ height: spacing.md }} />

      <AsyncState
        status={tasks.isError ? 'error' : data ? 'success' : 'loading'}
        error={tasks.error}
        onRetry={() => void tasks.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.md }}>
            {rows.length === 0 ? (
              <Card style={{ gap: spacing.xxs }}>
                <AppText variant="body" tone="secondary">
                  {NO_TASKS}
                </AppText>
                {scope === 'open' ? (
                  <AppText variant="caption" tone="secondary">
                    {NO_TASKS_HINT}
                  </AppText>
                ) : null}
              </Card>
            ) : (
              <Card>
                {rows.map((task) => (
                  <TaskRow
                    key={task.id}
                    task={task}
                    onToggle={() =>
                      action.mutate({
                        taskId: task.id,
                        action: task.status === 'completed' ? 'reopen' : 'complete',
                      })
                    }
                    onOpen={() =>
                      router.push({
                        pathname: '/daily/task-form',
                        params: { id: task.id },
                      })
                    }
                  />
                ))}
              </Card>
            )}

            <Button
              label={ADD_TASK}
              onPress={() => router.push('/daily/task-form')}
              accessibilityHint="Opens the new task form"
            />
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
