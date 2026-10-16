/**
 * What Nura can and cannot reach (PRD 12, sections 25-29, 57 and 83).
 *
 * **Every sentence here is the server's.** The three external keys come back
 * with the PRD's own wording -- "Live weather is not configured in this
 * build." -- derived from whether a provider exists rather than written into a
 * screen. So this screen cannot say anything softer, and it cannot go stale if
 * a provider is ever wired up.
 *
 * It exists because somebody who has asked Nura about the weather deserves to
 * be able to find out why it could not answer, rather than concluding the
 * assistant is broken.
 */
import { View } from 'react-native';

import { AppText, AsyncState, Card, Screen } from '../../src/components';
import { ExternalCapabilityRow } from '../../src/features/productivity/components/DailyLifeRows';
import { EXTERNAL_NOTE } from '../../src/features/productivity/copy';
import { useExternalCapabilities } from '../../src/features/productivity/hooks';
import { spacing } from '../../src/theme/tokens';

export default function CapabilitiesScreen() {
  const capabilities = useExternalCapabilities();
  const data = capabilities.data;

  return (
    <Screen
      onRefresh={() => void capabilities.refetch()}
      refreshing={capabilities.isRefetching && !capabilities.isLoading}
    >
      <AsyncState
        status={capabilities.isError ? 'error' : data ? 'success' : 'loading'}
        error={capabilities.error}
        onRetry={() => void capabilities.refetch()}
      >
        {data ? (
          <View style={{ gap: spacing.lg }}>
            <Card accessible accessibilityLabel={EXTERNAL_NOTE}>
              <AppText variant="body" tone="secondary">
                {EXTERNAL_NOTE}
              </AppText>
            </Card>

            <Card>
              {data.capabilities.map((capability) => (
                <ExternalCapabilityRow key={capability.key} capability={capability} />
              ))}
            </Card>
          </View>
        ) : null}
      </AsyncState>
    </Screen>
  );
}
