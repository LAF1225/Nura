/**
 * The caregiver's home (PRD 9, sections 17, 18, 19, 28, 29, 38, 60 and 67).
 *
 * Only the permitted categories appear, and that is enforced by what arrives
 * rather than by what this screen decides: the backend omits a section the
 * caregiver was not granted, so a missing key here means "not granted" and an
 * empty list means "granted, nothing recorded". Section 18 says those must not be
 * confusable, so the screen draws no heading at all for the first.
 *
 * Three things it deliberately does not do.
 *
 * **It does not interpret anything.** The adherence block shows counts with a
 * sentence saying they are counts. Nothing on this screen concludes that somebody
 * is doing badly, and nothing is coloured as a warning.
 *
 * **It does not offer a Call control** while `callingAvailable` is false, which is
 * every deployment today. Section 38 forbids simulating a successful call, and a
 * button whose only outcome is an error message is a worse version of saying so.
 *
 * **It does not write.** Every action leads either to a message or to a
 * suggestion the primary user approves (sections 21 and 64).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  StatusChip,
} from '../../src/components';
import {
  adherenceCounts,
  ADHERENCE_NOTE,
  CAREGIVER_PENDING_NOTE,
  caregiverPendingSentence,
  healthCountsSentence,
  NO_REMINDERS_SET,
  NO_SEVERITY_RECORDED,
  NO_UPCOMING_APPOINTMENTS,
  REMINDERS_PAUSED,
  reportVersionLabel,
  SELF_MODE_PROMPT,
  severitySentence,
  CAREGIVER_HOME_NOTHING_GRANTED,
  NO_DOSES_DUE,
  NOTHING_RECORDED,
  PERMISSION_NOT_YET,
  supportingSentence,
  unreadSentence,
} from '../../src/features/caregivers/copy';
import { useCaregiverHome, useCareMode } from '../../src/features/caregivers/hooks';
import { CAREGIVER_ROUTINES_ONLY } from '../../src/features/productivity/copy';
import { ALERTS_TITLE, unreadAlertsSentence } from '../../src/features/safety/copy';
import { dormantPermissions } from '../../src/features/caregivers/permissions';
import { spacing } from '../../src/theme/tokens';

export default function CaregiverModeHomeScreen() {
  const router = useRouter();
  const mode = useCareMode();
  const home = useCaregiverHome();
  const data = home.data;

  if (!mode.isCaregiverMode) {
    return (
      <Screen>
        <View style={{ gap: spacing.md }}>
          <AppText variant="body">{SELF_MODE_PROMPT}</AppText>
          <Button
            label="People you support"
            onPress={() => router.push('/care-mode/profiles')}
          />
        </View>
      </Screen>
    );
  }

  return (
    <Screen
      onRefresh={() => void home.refetch()}
      refreshing={home.isRefetching && !home.isLoading}
    >
      <AsyncState
        status={home.isError ? 'error' : 'success'}
        error={home.error}
        isEmpty={false}
        loadingLabel="Loading"
        onRetry={() => void home.refetch()}
      >
        {data === undefined ? null : (
          <View style={{ gap: spacing.lg }}>
            <View style={{ gap: spacing.xxs }}>
              <AppText variant="title" accessibilityRole="header">
                {data.profileName}
              </AppText>
              <AppText variant="body" tone="secondary">
                {supportingSentence(data.profileName)}
              </AppText>
              <AppText variant="caption" tone="secondary">
                {data.roleLabel}
              </AppText>
            </View>

            <Button
              label="Switch person"
              variant="secondary"
              onPress={() => router.push('/care-mode/profiles')}
              accessibilityHint="Opens the people you support"
            />

            {data.granted.length === 0 ? (
              <Card>
                <AppText variant="body">{CAREGIVER_HOME_NOTHING_GRANTED}</AppText>
              </Card>
            ) : null}

            {data.pendingSuggestions > 0 ? (
              <Card style={{ gap: spacing.xxs }}>
                <AppText variant="bodyStrong">
                  {caregiverPendingSentence(data.pendingSuggestions)}
                </AppText>
                <AppText variant="caption" tone="secondary">
                  {CAREGIVER_PENDING_NOTE}
                </AppText>
              </Card>
            ) : null}

            {/* Medications (section 19). No skip reasons -- there is no field. */}
            {data.medications !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Medication reminders
                </AppText>
                {data.medications.length === 0 ? (
                  <AppText variant="body" tone="secondary">
                    {NOTHING_RECORDED}
                  </AppText>
                ) : (
                  data.medications.map((medication) => (
                    <View key={medication.medicationId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">
                        {medication.dose
                          ? `${medication.name} ${medication.dose}`
                          : medication.name}
                      </AppText>
                      <AppText variant="body" tone="secondary">
                        {medication.remindersPaused
                          ? REMINDERS_PAUSED
                          : (medication.scheduleLabel ?? NO_REMINDERS_SET)}
                      </AppText>
                      {medication.supplyLow ? (
                        <StatusChip label="Running low" tone="warning" />
                      ) : null}
                      {medication.scheduleId !== null ? (
                        <Button
                          label="Suggest a change"
                          variant="secondary"
                          onPress={() =>
                            router.push({
                              pathname: '/care-mode/suggest',
                              params: {
                                scheduleId: medication.scheduleId ?? '',
                                name: medication.name,
                                current: medication.scheduleLabel ?? '',
                              },
                            })
                          }
                          accessibilityHint={`Suggests a change to ${medication.name}'s reminders`}
                        />
                      ) : null}
                    </View>
                  ))
                )}

                {data.adherence !== null ? (
                  <View style={{ gap: spacing.xxs }}>
                    <AppText variant="bodyStrong">Last 7 days</AppText>
                    {data.adherence.percent === null ? (
                      <AppText variant="body" tone="secondary">
                        {NO_DOSES_DUE}
                      </AppText>
                    ) : (
                      <AppText variant="body" tone="secondary">
                        {adherenceCounts(
                          data.adherence.taken,
                          data.adherence.skipped,
                          data.adherence.missed
                        )}
                      </AppText>
                    )}
                    <AppText variant="caption" tone="secondary">
                      {ADHERENCE_NOTE}
                    </AppText>
                  </View>
                ) : null}
              </Card>
            ) : null}

            {/* Appointments (section 26). */}
            {data.appointments !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Appointments
                </AppText>
                {data.appointments.length === 0 ? (
                  <AppText variant="body" tone="secondary">
                    {NO_UPCOMING_APPOINTMENTS}
                  </AppText>
                ) : (
                  data.appointments.map((appointment) => (
                    <View key={appointment.appointmentId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{appointment.title}</AppText>
                      <AppText variant="body" tone="secondary">
                        {appointment.whenLabel}
                      </AppText>
                      {appointment.locationName ? (
                        <AppText variant="caption" tone="secondary">
                          {appointment.locationName}
                        </AppText>
                      ) : null}
                    </View>
                  ))
                )}
              </Card>
            ) : null}

            {/* Symptoms (section 28). Read-only -- there is no write path. */}
            {data.symptoms !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Symptoms
                </AppText>
                {data.symptoms.length === 0 ? (
                  <AppText variant="body" tone="secondary">
                    {NOTHING_RECORDED}
                  </AppText>
                ) : (
                  data.symptoms.map((symptom) => (
                    <View key={symptom.episodeId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{symptom.name}</AppText>
                      <AppText variant="body" tone="secondary">
                        {symptom.severity === null
                          ? NO_SEVERITY_RECORDED
                          : severitySentence(symptom.severity)}
                      </AppText>
                    </View>
                  ))
                )}
              </Card>
            ) : null}

            {/*
              Routines (PRD 12, section 16). Read-only, like every other
              section here -- a caregiver's only route to a change is a
              suggestion the person approves (PRD 9, section 21).

              The scope note is section 42: a caregiver should be able to see
              where the edge is rather than wonder why the list looks short.
            */}
            {data.routines !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Routines
                </AppText>
                {data.routines.length === 0 ? (
                  <AppText variant="body" tone="secondary">
                    {NOTHING_RECORDED}
                  </AppText>
                ) : (
                  data.routines.map((routine) => (
                    <View key={routine.routineId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{routine.title}</AppText>
                      <AppText variant="body" tone="secondary">
                        {routine.scheduleLabel}
                        {routine.paused ? ' · paused' : ''}
                      </AppText>
                      {routine.todayProgressLabel ? (
                        <AppText variant="caption" tone="secondary">
                          {routine.todayProgressLabel}
                        </AppText>
                      ) : null}
                    </View>
                  ))
                )}
                <AppText variant="caption" tone="secondary">
                  {CAREGIVER_ROUTINES_ONLY}
                </AppText>
              </Card>
            ) : null}

            {/* Reports (section 29). That one exists, not its contents. */}
            {data.reports !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Health reports
                </AppText>
                {data.reports.length === 0 ? (
                  <AppText variant="body" tone="secondary">
                    {NOTHING_RECORDED}
                  </AppText>
                ) : (
                  data.reports.map((report) => (
                    <View key={report.reportId} style={{ gap: spacing.xxs }}>
                      <AppText variant="bodyStrong">{report.appointmentTitle}</AppText>
                      <AppText variant="caption" tone="secondary">
                        {reportVersionLabel(report.version)}
                      </AppText>
                    </View>
                  ))
                )}
              </Card>
            ) : null}

            {/* Counts, never names (section 67). */}
            {data.healthCounts !== null ? (
              <Card style={{ gap: spacing.xxs }}>
                <AppText variant="heading" accessibilityRole="header">
                  Health summary
                </AppText>
                <AppText variant="body" tone="secondary">
                  {healthCountsSentence(
                    data.healthCounts.activeConditions,
                    data.healthCounts.activeMedications,
                    data.healthCounts.activeSymptoms
                  )}
                </AppText>
              </Card>
            ) : null}

            {/* Messages (section 30). */}
            {data.unreadMessages !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  Messages
                </AppText>
                <AppText variant="body" tone="secondary">
                  {unreadSentence(data.unreadMessages)}
                </AppText>
                <Button
                  label="Open messages"
                  onPress={() => router.push('/family')}
                  accessibilityHint="Opens your messages with them"
                />
              </Card>
            ) : null}

            {/* Safety alerts (PRD 10, sections 31, 50 and 83). Absent, not
                empty, when the category was not granted. */}
            {data.safety !== null ? (
              <Card style={{ gap: spacing.sm }}>
                <AppText variant="heading" accessibilityRole="header">
                  {ALERTS_TITLE}
                </AppText>
                <AppText variant="body" tone="secondary">
                  {unreadAlertsSentence(data.safety.unreadCount)}
                </AppText>
                {data.safety.latestEventLabel ? (
                  <AppText variant="body" tone="secondary">
                    {data.safety.latestEventLabel}
                  </AppText>
                ) : null}
                <Button
                  label="Open safety alerts"
                  onPress={() => router.push('/care-mode/safety-alerts')}
                  accessibilityHint="Opens the safety alerts raised about them"
                />
              </Card>
            ) : null}

            {/* Granted, and nothing behind it yet (sections 94 and 27). */}
            {dormantPermissions(data).map((key) => (
              <Card key={key}>
                <AppText variant="caption" tone="secondary">
                  {PERMISSION_NOT_YET[key] ?? ''}
                </AppText>
              </Card>
            ))}

            <Button
              label="Notifications"
              variant="secondary"
              onPress={() => router.push('/care-mode/notifications')}
              accessibilityHint="Chooses what Nura tells you about this person"
            />
          </View>
        )}
      </AsyncState>
    </Screen>
  );
}
