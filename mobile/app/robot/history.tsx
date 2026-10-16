/**
 * What Nura was asked to show, and what became of it (PRD 11, section 96).
 *
 * The distinction this screen exists to keep is section 14's: *sent to Nura*
 * and *shown* are different rows. A card the backend handed over and that the
 * robot never acknowledged reads as "sent to Nura", not as shown -- and
 * because no physical robot has ever acknowledged anything, nothing in this
 * list has ever read as shown outside a test.
 *
 * The summary under each line is the payload the robot was *sent*, already
 * reduced to the privacy level in force when it was built (section 22). So a
 * private medication reminder reads as "Reminder due" here too: there is no
 * path by which this screen can show more than the robot received.
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen } from '../../src/components';
import {
  PresentationRow,
  RobotSectionHeading,
} from '../../src/features/robot/components/RobotCards';
import * as copy from '../../src/features/robot/copy';
import { usePresentationHistory, useRobotDevice } from '../../src/features/robot/hooks';
import { spacing } from '../../src/theme/tokens';

export default function RobotHistoryScreen() {
  const { deviceId } = useRobotDevice();
  const history = usePresentationHistory(deviceId);
  const rows = history.data;

  return (
    <Screen>
      <RobotSectionHeading title={copy.HISTORY_TITLE} hint={copy.HISTORY_HINT} />

      <AsyncState
        status={history.isError ? 'error' : rows === undefined ? 'loading' : 'success'}
        error={history.error}
        loadingLabel="Reading Nura’s history"
        onRetry={() => void history.refetch()}
      >
        {rows === undefined ? null : rows.length === 0 ? (
          <Card style={{ marginTop: spacing.md }}>
            <AppText variant="body" tone="secondary">
              {copy.HISTORY_EMPTY}
            </AppText>
          </Card>
        ) : (
          <View style={{ gap: spacing.sm, marginTop: spacing.md }}>
            {rows.map((presentation) => (
              <PresentationRow key={presentation.id} presentation={presentation} />
            ))}
            <AppText variant="caption" tone="secondary">
              {copy.HISTORY_PRIVATE}
            </AppText>
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
