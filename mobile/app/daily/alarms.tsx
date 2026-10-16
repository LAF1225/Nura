/**
 * The alarm list (PRD 12, sections 10, 11, 54 and 60's AlarmsScreen).
 *
 * **The limitation sentence is at the top, not in the small print.** Section
 * 11 asks for honest labelling and section 71 for the gap to be stated; the
 * text comes from the server with every list, so this screen cannot soften it
 * and a future change cannot drop it by editing a string here. **No alarm has
 * ever fired on a physical phone.**
 *
 * The switch on each row is the whole interaction people want -- an alarm is a
 * thing you turn off at the weekend -- so it is one tap, and editing is behind
 * the row.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, AsyncState, Button, Card, Screen } from '../../src/components';
import {
  AlarmLimitationNote,
  AlarmRow,
} from '../../src/features/productivity/components/DailyLifeRows';
import { ADD_ALARM, NO_ALARMS } from '../../src/features/productivity/copy';
import {
  useAlarms,
  useDailyLifeNotifications,
  useUpdateAlarm,
} from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

export default function AlarmsScreen() {
  const router = useRouter();
  const alarms = useAlarms();
  const update = useUpdateAlarm();

  // Section 34: the phone's pending alarm notifications are rebuilt from what
  // the server says, every time this screen is shown.
  useDailyLifeNotifications(undefined, alarms.data?.alarms);

  const data = alarms.data;

  return (
    <Screen
      onRefresh={() => void alarms.refetch()}
      refreshing={alarms.isRefetching && !alarms.isLoading}
    >
      <AsyncState
        status={alarms.isError ? 'error' : data ? 'success' : 'loading'}
        error={alarms.error}
        onRetry={() => void alarms.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <AlarmLimitationNote limitation={data.limitation} />

            {data.alarms.length === 0 ? (
              <Card>
                <AppText variant="body" tone="secondary">
                  {NO_ALARMS}
                </AppText>
              </Card>
            ) : (
              <Card style={{ gap: spacing.md }}>
                {data.alarms.map((alarm) => (
                  <AlarmRow
                    key={alarm.id}
                    alarm={alarm}
                    onToggle={(enabled) =>
                      update.mutate({ alarmId: alarm.id, input: { enabled } })
                    }
                    onOpen={() =>
                      router.push({
                        pathname: '/daily/alarm-form',
                        params: { id: alarm.id },
                      })
                    }
                  />
                ))}
              </Card>
            )}

            <Button
              label={ADD_ALARM}
              onPress={() => router.push('/daily/alarm-form')}
              accessibilityHint="Opens the new alarm form"
            />
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
