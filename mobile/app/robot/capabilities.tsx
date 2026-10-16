/**
 * What this Nura has told us it can do (PRD 11, sections 10, 12, 47, 91, 135).
 *
 * Twelve rows, always all twelve, because section 10 rules out a single
 * `robot_ready` boolean and the reason shows up here: "the screen works and
 * nobody has ever tested the speaker" is the honest answer, and one flag
 * cannot say it.
 *
 * The state a row shows is the state this build will *act on*, which is not
 * always what the robot said. A display proven by a firmware that is no longer
 * running reads as "Not tested yet" and says why (section 124). Nothing is
 * ever upgraded by inference.
 */
import { View } from 'react-native';

import { AppText, AsyncState, ListGroup, Screen } from '../../src/components';
import {
  CapabilityRow,
  RobotSectionHeading,
} from '../../src/features/robot/components/RobotCards';
import * as copy from '../../src/features/robot/copy';
import { useRobotCapabilities, useRobotDevice } from '../../src/features/robot/hooks';
import { spacing } from '../../src/theme/tokens';

export default function RobotCapabilitiesScreen() {
  const { deviceId } = useRobotDevice();
  const capabilities = useRobotCapabilities(deviceId);
  const data = capabilities.data;

  return (
    <Screen>
      <RobotSectionHeading
        title={copy.CAPABILITIES_TITLE}
        hint={copy.CAPABILITIES_HINT}
      />

      <AsyncState
        status={
          capabilities.isError ? 'error' : data === undefined ? 'loading' : 'success'
        }
        error={capabilities.error}
        loadingLabel="Reading what Nura can do"
        onRetry={() => void capabilities.refetch()}
      >
        {data === undefined ? null : (
          <View style={{ gap: spacing.md, marginTop: spacing.md }}>
            <ListGroup>
              {data.capabilities.map((capability) => (
                <CapabilityRow key={capability.key} capability={capability} />
              ))}
            </ListGroup>

            <AppText variant="caption" tone="secondary">
              {data.hardwareNote}
            </AppText>
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
