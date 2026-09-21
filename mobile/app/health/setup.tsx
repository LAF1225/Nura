/**
 * Gradual health setup (PRD 4, sections 4, 17, 18 and 19).
 *
 * Not a wizard. It is a list of the seven sections with a way into each, and
 * the one the user is on highlighted -- so "add now" and "skip for now" are
 * the same gesture as "go somewhere else", and stopping half way is not a
 * state anyone has to escape from.
 *
 * Where someone got to is stored on the server, so it survives a reinstall,
 * and the app can say "continue" rather than starting again (section 18).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  SkeletonCard,
} from '../../src/components';
import { Completeness } from '../../src/features/health/components/Completeness';
import { useHealthSummary, useUpdateHealthSetup } from '../../src/features/health/hooks';
import { bloodTypeLabel, isRecordSection } from '../../src/features/health/sections';
import type { HealthSection } from '../../src/features/health/types';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function HealthSetupScreen() {
  const router = useRouter();
  const summary = useHealthSummary();
  const setup = useUpdateHealthSetup();

  const data = summary.data;

  const open = (section: HealthSection) => {
    // Remember where they went, so Health can offer to continue here.
    setup.mutate({ step: section, status: 'in_progress' });
    if (isRecordSection(section)) {
      router.push({ pathname: '/health/[section]', params: { section } });
    } else {
      router.push('/health/blood-type');
    }
  };

  return (
    <Screen>
      <AppText variant="title" accessibilityRole="header">
        Your health profile
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.xs }}>
        Add what you can, in any order. You can stop at any point and pick it up later —
        nothing here is required.
      </AppText>

      <View style={{ height: spacing.lg }} />

      {summary.isLoading ? (
        <Card>
          <SkeletonCard lines={4} label="Loading your health profile" />
        </Card>
      ) : summary.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="body" tone="secondary">
            {apiErrorMessage(summary.error)}
          </AppText>
          <Button
            label="Try again"
            variant="secondary"
            onPress={() => summary.refetch()}
          />
        </Card>
      ) : data ? (
        <View style={{ gap: spacing.lg }}>
          <Card style={{ gap: spacing.sm }}>
            <AppText variant="bodyStrong">{data.percent}% filled in</AppText>
            <Completeness
              percent={data.percent}
              completedSections={data.completedSections}
              totalSections={data.totalSections}
            />
          </Card>

          <ListGroup>
            {data.sections.map((section) => (
              <ListRow
                key={section.key}
                label={section.title}
                description={
                  data.step === section.key && data.status !== 'complete'
                    ? 'Where you left off'
                    : undefined
                }
                value={
                  section.key === 'blood_type'
                    ? (bloodTypeLabel(data.bloodType) ?? 'Add')
                    : section.count > 0
                      ? String(section.count)
                      : 'Add'
                }
                showChevron
                onPress={() => open(section.key)}
                accessibilityHint={`Opens ${section.title.toLowerCase()}`}
              />
            ))}
          </ListGroup>

          {/* "Finish later" is just leaving, so the only action here is the
              one that says you are done for good (PRD 4, section 4). */}
          <View style={{ gap: spacing.sm }}>
            {data.status === 'complete' ? (
              <AppText variant="body" tone="secondary">
                You’ve marked your health profile as complete. You can still add to it
                whenever you like.
              </AppText>
            ) : (
              <Button
                label="I’m done for now"
                variant="secondary"
                onPress={() => {
                  setup.mutate({ status: 'complete', step: null });
                  router.back();
                }}
                accessibilityHint="Marks your health profile as complete. You can still change it later."
              />
            )}
            <Button label="Finish later" variant="ghost" onPress={() => router.back()} />
          </View>

          {setup.isError ? (
            <AppText variant="caption" tone="secondary">
              {apiErrorMessage(setup.error)}
            </AppText>
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
