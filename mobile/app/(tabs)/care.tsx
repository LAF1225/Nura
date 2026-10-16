/**
 * Care -- the operational side of looking after yourself (PRD 5, sections 6, 30).
 *
 * The Health/Care boundary PRD 5 section 30 sets, and this screen is where it
 * becomes visible:
 *
 *     Health = what the medication is
 *     Care   = reminders, schedules, adherence, refills
 *
 * PRD 5 filled the first section of this tab, PRD 7 added the second, PRD 9
 * added the third and PRD 10 adds Safety: Medications, Appointments, the people
 * who help, and whether anybody is watching over you. Routines are the only
 * thing still named-but-absent, and the card says so rather than offering a
 * disabled row that promises something Nura cannot do (PRD 3, section 35).
 *
 * The Safety card says whether monitoring is on and how many emergency contacts
 * there are, and nothing else -- PRD 10 section 4 wants the state visible
 * without a tab load, and sections 64 and 72 rule out implying more capability
 * than the build has. What Nura can actually do is behind the Safety screen.
 *
 * The caregiver section shows counts and nothing else. Who is helping and what
 * they can see lives behind its own screen; a tab that loaded four screens'
 * worth of data to render three numbers is what PRD 3 section 16 warns against.
 * And nothing here reports that a caregiver *looked* at anything -- PRD 9
 * sections 49 and 50 rule out both the notification and the feed.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card, Screen } from '../../src/components';
import {
  clinicianLine,
  PREPARATION_LABELS,
  upcomingCountSentence,
} from '../../src/features/appointments/copy';
import {
  useAppointmentReminders,
  useAppointmentSummary,
  useSyncPendingAppointments,
  useUpcomingAppointments,
} from '../../src/features/appointments/hooks';
import {
  CARE_SECTION_TITLE,
  careSummarySentence,
  contactCountSentence,
  CONTACTS_TITLE,
  MESSAGES_TITLE,
  pendingRequestsSentence,
  unreadSentence,
} from '../../src/features/caregivers/copy';
import {
  ROUTINES_TITLE,
  routineCountSentence,
} from '../../src/features/productivity/copy';
import {
  useRoutines,
  useSyncPendingDailyLife,
} from '../../src/features/productivity/hooks';
import { useCareSummary } from '../../src/features/caregivers/hooks';
import { doseTitle, lowSupplySentence } from '../../src/features/medications/doses';
import {
  useMedicationSchedules,
  useSyncPendingDoseActions,
} from '../../src/features/medications/hooks';
import { CARE_CARD_TITLE, careCardSentence } from '../../src/features/safety/copy';
import { useSafetyStatus } from '../../src/features/safety/hooks';
import { useToday } from '../../src/hooks/useToday';
import { spacing } from '../../src/theme/tokens';

export default function CareScreen() {
  const router = useRouter();
  const today = useToday();
  const schedules = useMedicationSchedules();

  // Care is a place somebody lands after being offline, so this is a second
  // chance to send whatever is queued (PRD 5, section 62; PRD 7, section 53).
  useSyncPendingDoseActions();
  useSyncPendingAppointments();
  // PRD 13 section 32: PRD 12's queues get the same second chance.
  useSyncPendingDailyLife();

  const appointments = useAppointmentSummary();
  const care = useCareSummary();
  const safety = useSafetyStatus();
  const routines = useRoutines();
  const upcoming = useUpcomingAppointments();
  // Care is the appointment list's home, so this is where the phone's reminders
  // are brought back in step with it (PRD 7, section 54).
  useAppointmentReminders(upcoming.data);

  const medications = today.data?.medications ?? null;
  const scheduleCount = schedules.data?.length ?? 0;
  const next = medications?.nextDue ?? null;
  const low = medications?.lowSupply[0];
  const nextAppointment = appointments.data?.next ?? null;
  const upcomingCount = appointments.data?.upcomingCount ?? 0;
  const caregiverCount = care.data?.caregiverCount ?? 0;
  const pendingInvitations = care.data?.pendingInvitationCount ?? 0;
  const pendingRequests = care.data?.pendingSuggestionCount ?? 0;
  const unreadMessages = care.data?.unreadMessageCount ?? 0;
  const contactCount = care.data?.emergencyContactCount ?? 0;
  // PRD 12 section 20: Care gains a functional Routines section. The list is
  // read here rather than counted into the care summary, because a routine's
  // useful state is how today's run is going and that is not a number.
  const routineCount = routines.data?.activeCount ?? 0;
  const nextRoutine =
    routines.data?.routines.find((routine) => routine.status === 'active') ?? null;

  return (
    <Screen
      onRefresh={() => void today.refetch()}
      refreshing={today.isRefetching && !today.isLoading}
    >
      <AppText variant="title" accessibilityRole="header">
        Care
      </AppText>
      <AppText variant="body" tone="secondary" style={{ marginTop: spacing.xxs }}>
        Reminders, schedules and the people who help care for you.
      </AppText>

      <View style={{ height: spacing.lg }} />

      <View style={{ gap: spacing.lg }}>
        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Medications</AppText>
            <AppText variant="body" tone="secondary">
              {scheduleCount === 0
                ? 'No reminders set up yet.'
                : scheduleCount === 1
                  ? '1 reminder schedule'
                  : `${scheduleCount} reminder schedules`}
            </AppText>
          </View>

          {next ? (
            <View style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">Next</AppText>
              <AppText variant="body" tone="secondary">
                {doseTitle(next)}
              </AppText>
            </View>
          ) : null}

          {medications && medications.overdueCount > 0 ? (
            // Stated plainly. Not an alert, not a warning colour, not an
            // emergency (PRD 5, sections 24 and 29).
            <AppText variant="body" tone="secondary">
              {medications.overdueCount === 1
                ? '1 dose hasn’t been marked as taken.'
                : `${medications.overdueCount} doses haven’t been marked as taken.`}
            </AppText>
          ) : null}

          {low ? (
            <AppText variant="body" tone="secondary">
              {lowSupplySentence(low.medicationName, low.remainingDoses)}
            </AppText>
          ) : null}

          <Button
            label={scheduleCount === 0 ? 'Set up reminders' : 'View all'}
            onPress={() => router.push('/medications')}
            accessibilityHint="Opens medication reminders, supply and history"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Appointments</AppText>
            <AppText variant="body" tone="secondary">
              {upcomingCountSentence(upcomingCount)}
            </AppText>
          </View>

          {nextAppointment ? (
            <View style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">{nextAppointment.title}</AppText>
              <AppText variant="body" tone="secondary">
                {nextAppointment.whenLabel}
              </AppText>
              {clinicianLine(
                nextAppointment.clinicianName,
                nextAppointment.clinicianSpecialty
              ) ? (
                <AppText variant="body" tone="secondary">
                  {clinicianLine(
                    nextAppointment.clinicianName,
                    nextAppointment.clinicianSpecialty
                  )}
                </AppText>
              ) : null}
              <AppText variant="caption" tone="secondary">
                {PREPARATION_LABELS[nextAppointment.preparationStatus]}
              </AppText>
            </View>
          ) : null}

          <Button
            label={upcomingCount === 0 ? 'Add appointment' : 'View all'}
            onPress={() => router.push('/appointments')}
            accessibilityHint="Opens appointments, questions and health summaries"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">{CARE_SECTION_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {careSummarySentence(caregiverCount, pendingInvitations)}
            </AppText>
          </View>

          {pendingRequests > 0 ? (
            <AppText variant="bodyStrong">
              {pendingRequestsSentence(pendingRequests)}
            </AppText>
          ) : null}

          <Button
            label={caregiverCount === 0 ? 'Invite someone' : 'View all'}
            onPress={() => router.push('/caregivers')}
            accessibilityHint="Opens caregivers, what each can see, and care requests"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">{MESSAGES_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {unreadSentence(unreadMessages)}
            </AppText>
          </View>
          <Button
            label="Open messages"
            onPress={() => router.push('/family')}
            accessibilityHint="Opens messages with the people who help you"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">{CONTACTS_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {contactCountSentence(contactCount)}
            </AppText>
          </View>
          <Button
            label={contactCount === 0 ? 'Add contacts' : 'View all'}
            onPress={() => router.push('/emergency-contacts')}
            accessibilityHint="Opens emergency contacts and their order"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">{CARE_CARD_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {careCardSentence(
                safety.data?.monitoring !== null && safety.data?.monitoring !== undefined,
                safety.data?.emergencyContactCount ?? contactCount
              )}
            </AppText>
          </View>
          <Button
            label="Open Safety"
            onPress={() => router.push('/safety')}
            accessibilityHint="Safety Monitoring, emergency requests and what Nura can do"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <View style={{ gap: spacing.xxs }}>
            <AppText variant="heading">{ROUTINES_TITLE}</AppText>
            <AppText variant="body" tone="secondary">
              {routineCountSentence(routineCount)}
            </AppText>
          </View>
          {nextRoutine ? (
            <View style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">{nextRoutine.title}</AppText>
              <AppText variant="body" tone="secondary">
                {nextRoutine.scheduleLabel}
              </AppText>
              {nextRoutine.todayRun ? (
                <AppText variant="caption" tone="secondary">
                  {nextRoutine.todayRun.progressLabel}
                </AppText>
              ) : null}
            </View>
          ) : null}
          <Button
            label={routineCount === 0 ? 'Set up a routine' : 'View all'}
            onPress={() => router.push('/daily/routines')}
            accessibilityHint="Opens routines, their steps and today's progress"
          />
        </Card>
      </View>
    </Screen>
  );
}
