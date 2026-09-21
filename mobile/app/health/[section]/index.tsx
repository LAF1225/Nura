/**
 * One section of the health record (PRD 4, sections 20, 29, 37 and 46).
 *
 * Six sections, one screen: the route parameter picks a section spec, and the
 * spec supplies the wording, the row titles and the summary line. Writing this
 * six times would mean six chances for the delete confirmation or an empty
 * state to drift.
 *
 * Deleting always asks first, and says what will be removed (section 46).
 */
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { useLayoutEffect } from 'react';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  SkeletonCard,
} from '../../../src/components';
import { OfflineBanner } from '../../../src/components/today';
import { useHealthRecords } from '../../../src/features/health/hooks';
import { isRecordSection, SECTIONS } from '../../../src/features/health/sections';
import type { HealthRecord } from '../../../src/features/health/types';
import { useIsOffline } from '../../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

function recordTitle(record: HealthRecord, field: string): string {
  const value = record[field];
  return typeof value === 'string' && value.length > 0 ? value : 'Untitled';
}

export default function HealthSectionScreen() {
  const { section } = useLocalSearchParams<{ section: string }>();
  const router = useRouter();
  const navigation = useNavigation();
  const isOffline = useIsOffline();

  const spec = isRecordSection(section) ? SECTIONS[section] : null;

  useLayoutEffect(() => {
    navigation.setOptions({ title: spec?.title ?? 'Health' });
  }, [navigation, spec]);

  // The hook runs unconditionally, so an unknown section still calls it --
  // with a stand-in spec whose results are then never rendered.
  const records = useHealthRecords(spec ?? SECTIONS.conditions);

  if (spec === null) {
    return (
      <Screen>
        <Card>
          <AppText variant="body" tone="secondary">
            That part of your health profile isn’t available in this version of Nura.
          </AppText>
        </Card>
      </Screen>
    );
  }

  const items = records.data ?? [];

  return (
    <Screen
      onRefresh={() => void records.refetch()}
      refreshing={records.isRefetching && !records.isLoading}
    >
      <AppText variant="body" tone="secondary" style={{ marginBottom: spacing.lg }}>
        {spec.description}
      </AppText>

      {isOffline ? <OfflineBanner /> : null}

      {records.isLoading ? (
        <Card>
          <SkeletonCard lines={3} label={`Loading ${spec.title.toLowerCase()}`} />
        </Card>
      ) : records.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(records.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => records.refetch()}
          />
        </Card>
      ) : (
        <View style={{ gap: spacing.lg }}>
          {items.length === 0 ? (
            <Card>
              <AppText variant="body" tone="secondary">
                {spec.emptyMessage}
              </AppText>
            </Card>
          ) : (
            <ListGroup>
              {items.map((record) => (
                <ListRow
                  key={record.id}
                  label={recordTitle(record, spec.titleField)}
                  description={spec.subtitle(record) ?? undefined}
                  showChevron
                  onPress={() =>
                    router.push({
                      pathname: '/health/[section]/[id]',
                      params: { section: spec.key, id: record.id },
                    })
                  }
                  accessibilityHint="Opens this record to edit it"
                />
              ))}
            </ListGroup>
          )}

          <Button
            label={`Add ${articleFor(spec.singular)}`}
            onPress={() =>
              router.push({
                pathname: '/health/[section]/[id]',
                params: { section: spec.key, id: 'new' },
              })
            }
          />

          {items.length > 0 ? (
            <AppText variant="caption" tone="secondary">
              Tap a {spec.singular} to change or remove it.
            </AppText>
          ) : null}
        </View>
      )}
    </Screen>
  );
}

/** "a condition" / "an allergy". */
function articleFor(singular: string): string {
  return /^[aeiou]/.test(singular) ? `an ${singular}` : `a ${singular}`;
}
