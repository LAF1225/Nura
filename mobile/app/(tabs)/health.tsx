/**
 * Health -- the overview of the health record (PRD 4, sections 5, 6 and 19).
 *
 * Summary-oriented on purpose. This screen says what is in the profile and
 * gives a way into each part; it never lists conditions or medications
 * itself. That keeps the most-opened health screen calm, and keeps sensitive
 * detail one deliberate tap away (PRD 4, sections 5 and 33).
 *
 * A partly-filled profile is a normal state, not a warning (section 19), and
 * none of this needs a robot (section 38).
 */
import { useRouter } from 'expo-router';
import { Fragment } from 'react';
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
import { OfflineBanner } from '../../src/components/today';
import { Completeness } from '../../src/features/health/components/Completeness';
import { useHealthSummary } from '../../src/features/health/hooks';
import { bloodTypeLabel, isRecordSection } from '../../src/features/health/sections';
import type { HealthSectionSummary } from '../../src/features/health/types';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { useToday } from '../../src/hooks/useToday';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';
import { timeAgo } from '../../src/utils/time';

/**
 * "2 active" / "None active" -- the symptom row's value (PRD 6, section 48).
 *
 * Symptoms are listed here because PRD 6 section 6 puts them in Health, and they
 * are deliberately *not* one of the completeness sections: having none logged is a
 * good state, and a percentage that rose because somebody felt unwell would be
 * grotesque. They are also never added to the condition counts -- a symptom is
 * what somebody is experiencing and a condition is what they have been told they
 * have (PRD 6, section 6).
 */
function symptomValue(activeSymptoms: number): string {
  if (activeSymptoms === 0) return 'None active';
  return activeSymptoms === 1 ? '1 active' : `${activeSymptoms} active`;
}

function symptomDescription(updatesThisWeek: number): string | undefined {
  if (updatesThisWeek === 0) return undefined;
  return updatesThisWeek === 1
    ? '1 updated this week'
    : `${updatesThisWeek} updated this week`;
}

/** "3 added" / "Not added yet" / "O positive" -- never a record's contents. */
function sectionValue(section: HealthSectionSummary, bloodType: string | null): string {
  if (section.key === 'blood_type') {
    return bloodTypeLabel(bloodType) ?? 'Not added yet';
  }
  if (section.count === 0) return 'Not added yet';
  return section.count === 1 ? '1 added' : `${section.count} added`;
}

function sectionDescription(section: HealthSectionSummary): string | undefined {
  if (section.key === 'blood_type' || section.updatedAt === null) return undefined;
  return `Updated ${timeAgo(section.updatedAt)}`;
}

export default function HealthScreen() {
  const router = useRouter();
  const summary = useHealthSummary();
  const today = useToday();
  const isOffline = useIsOffline();
  // PRD 3 section 34 put the weekly check-in count here, and it stays: it is
  // the one health-adjacent thing that exists outside the medical record.
  const checkIns = today.data?.dailyCheckIn.recentCompletedCount ?? 0;

  const data = summary.data;
  const started = data !== undefined && data.status !== 'not_started';

  return (
    <Screen
      onRefresh={() => void summary.refetch()}
      refreshing={summary.isRefetching && !summary.isLoading}
    >
      <AppText variant="title" accessibilityRole="header">
        Health
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.xxs }}>
        Everything here is what you have told Nura. Add as much or as little as you like.
      </AppText>

      <View style={{ height: spacing.lg }} />

      {isOffline ? <OfflineBanner /> : null}

      {summary.isLoading ? (
        <Card>
          <SkeletonCard lines={4} label="Loading your health profile" />
        </Card>
      ) : summary.isError ? (
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura can’t load your health profile</AppText>
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
            {started ? (
              <>
                <AppText variant="heading">
                  {data.status === 'complete'
                    ? 'Your health profile'
                    : 'Your profile is partly complete'}
                </AppText>
                <Completeness
                  percent={data.percent}
                  completedSections={data.completedSections}
                  totalSections={data.totalSections}
                />
                <Button
                  label={data.status === 'complete' ? 'Review setup' : 'Continue setup'}
                  onPress={() => router.push('/health/setup')}
                />
              </>
            ) : (
              <>
                <AppText variant="heading">Set up your health profile</AppText>
                <AppText variant="body" tone="secondary">
                  You can add your medical information now or complete it gradually. Nura
                  will use only the information you choose to provide.
                </AppText>
                <Button
                  label="Start health setup"
                  onPress={() => router.push('/health/setup')}
                />
              </>
            )}
          </Card>

          <View style={{ gap: spacing.xs }}>
            <AppText variant="bodyStrong">What Nura knows</AppText>
            <ListGroup>
              {data.sections.map((section) => (
                <Fragment key={section.key}>
                  <ListRow
                    label={section.title}
                    description={sectionDescription(section)}
                    value={sectionValue(section, data.bloodType)}
                    showChevron
                    onPress={() =>
                      isRecordSection(section.key)
                        ? router.push({
                            pathname: '/health/[section]',
                            params: { section: section.key },
                          })
                        : router.push('/health/blood-type')
                    }
                    accessibilityHint={`Opens ${section.title.toLowerCase()}`}
                  />

                  {/* Symptoms sit between allergies and doctors, which is where
                      PRD 6 section 6 puts them -- and they are their own row
                      rather than one of the record sections above. */}
                  {section.key === 'allergies' ? (
                    <ListRow
                      label="Symptoms"
                      description={symptomDescription(data.symptomUpdatesThisWeek)}
                      value={symptomValue(data.activeSymptoms)}
                      showChevron
                      onPress={() => router.push('/symptoms')}
                      accessibilityHint="Opens what you are experiencing, and its history"
                    />
                  ) : null}
                </Fragment>
              ))}
            </ListGroup>
          </View>

          {data.activeConditions > 0 || data.activeMedications > 0 ? (
            <Card style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">Right now</AppText>
              <AppText variant="body" tone="secondary">
                {data.activeConditions === 1
                  ? '1 ongoing condition'
                  : `${data.activeConditions} ongoing conditions`}
                {' · '}
                {data.activeMedications === 1
                  ? '1 medication you are taking'
                  : `${data.activeMedications} medications you are taking`}
              </AppText>
            </Card>
          ) : null}

          {/* PRD 4, section 55: Nura stores what people tell it, and says so
              rather than implying any of it has been checked. */}
          <AppText variant="caption" tone="secondary">
            Nura stores what you enter. Nothing here has been checked by a clinician.
          </AppText>
        </View>
      ) : null}

      <View style={{ height: spacing.lg }} />

      {checkIns > 0 ? (
        <Card style={{ gap: spacing.xxs, marginBottom: spacing.md }}>
          <AppText variant="bodyStrong">This week</AppText>
          <AppText variant="body" tone="secondary">
            {checkIns === 1 ? '1 check-in completed' : `${checkIns} check-ins completed`}
          </AppText>
        </Card>
      ) : null}

      <Card style={{ gap: spacing.xs }}>
        <AppText variant="body" tone="secondary">
          Your health timeline, conditions over time, measurements and reports will live
          here as Nura grows.
        </AppText>
      </Card>
    </Screen>
  );
}
