/**
 * What this build can actually do (PRD 10, sections 64, 65, 66, 72 and 106).
 *
 * Section 64 gives the reason in one line: *this prevents misleading UI*. The
 * list is the server's answer, computed from the providers and the detector
 * registry it really has -- so a row says "Not set up in this build" because
 * nothing is wired up, not because somebody wrote that into a screen.
 *
 * It exists as its own screen because somebody deciding whether to rely on
 * this deserves one place that answers the question honestly, rather than
 * inferring it from which buttons happen to be missing (section 72).
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen } from '../../src/components';
import { CapabilityStatusRow } from '../../src/features/safety/components/SafetyCards';
import {
  CAPABILITIES_SUBTITLE,
  CAPABILITIES_TITLE,
} from '../../src/features/safety/copy';
import { useSafetyCapabilities } from '../../src/features/safety/hooks';
import { spacing } from '../../src/theme/tokens';

export default function SafetyCapabilitiesScreen() {
  const query = useSafetyCapabilities();
  const data = query.data ?? null;

  return (
    <Screen
      onRefresh={() => void query.refetch()}
      refreshing={query.isRefetching && !query.isLoading}
    >
      <View style={{ gap: spacing.md }}>
        <AppText variant="body" tone="secondary">
          {CAPABILITIES_SUBTITLE}
        </AppText>

        <AsyncState
          status={query.isError ? 'error' : data ? 'success' : 'loading'}
          error={query.error}
          loadingLabel={`Loading ${CAPABILITIES_TITLE.toLowerCase()}`}
          onRetry={() => void query.refetch()}
        >
          {data ? (
            <View style={{ gap: spacing.md }}>
              {data.warning ? (
                <Card accessible accessibilityRole="alert">
                  <AppText variant="body">{data.warning}</AppText>
                </Card>
              ) : null}
              <Card style={{ gap: spacing.sm }}>
                {data.capabilities.map((capability) => (
                  <CapabilityStatusRow key={capability.key} capability={capability} />
                ))}
              </Card>
            </View>
          ) : null}
        </AsyncState>
      </View>
    </Screen>
  );
}
