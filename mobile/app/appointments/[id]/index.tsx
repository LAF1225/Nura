/**
 * One appointment (PRD 7, sections 11, 38 and 40).
 *
 * The shape PRD 7 section 11 lays out: what it is, when and where, the one
 * prominent action -- Prepare for appointment -- then the questions, the summary,
 * the notes, and a way to edit.
 *
 * What happens *after* a visit lives here too (section 38), kept minimal: mark it
 * completed, write down what was said, and note a follow-up date. Adding the
 * follow-up appointment opens the ordinary form; nothing books anything
 * (section 40).
 */
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  ListGroup,
  ListRow,
  Screen,
  SkeletonCard,
  StatusChip,
} from '../../../src/components';
import { QuestionList } from '../../../src/features/appointments/components/QuestionList';
import {
  clinicianLine,
  PREPARATION_LABELS,
  PREPARE_ACTION,
  questionCountSentence,
  reportCountSentence,
  reportVersionLine,
  STATUS_LABELS,
  TYPE_LABELS,
} from '../../../src/features/appointments/copy';
import {
  useAppointment,
  useCancelAppointment,
  useCompleteAppointment,
  useDeleteAppointment,
  usePendingQuestions,
  useReopenAppointment,
  useSetReminders,
  useSyncPendingAppointments,
} from '../../../src/features/appointments/hooks';
import { pendingForAppointment } from '../../../src/features/appointments/pending';
import { apiErrorMessage } from '../../../src/services/api';
import { spacing } from '../../../src/theme/tokens';

export default function AppointmentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  const appointment = useAppointment(id);
  const pending = usePendingQuestions();
  const cancel = useCancelAppointment();
  const complete = useCompleteAppointment();
  const reopen = useReopenAppointment();
  const remove = useDeleteAppointment();
  const setReminders = useSetReminders();

  useSyncPendingAppointments();

  const record = appointment.data;
  const queued = pendingForAppointment(pending.data ?? [], id ?? '');

  if (appointment.isLoading || record === undefined) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={4} />
        </Card>
      </Screen>
    );
  }

  if (appointment.isError) {
    return (
      <Screen>
        <AsyncState
          status="error"
          error={appointment.error}
          onRetry={() => void appointment.refetch()}
        >
          {null}
        </AsyncState>
      </Screen>
    );
  }

  const who = clinicianLine(
    record.clinician?.name ?? null,
    record.clinician?.specialty ?? null
  );
  const isOpen = record.status === 'scheduled';
  const latestReport = record.reports?.[0];

  const run = (action: () => void) => {
    setError(null);
    action();
  };

  return (
    <Screen
      onRefresh={() => void appointment.refetch()}
      refreshing={appointment.isRefetching && !appointment.isLoading}
    >
      <View style={{ gap: spacing.xs }}>
        <AppText variant="title" accessibilityRole="header">
          {record.title}
        </AppText>
        {who ? (
          <AppText variant="body" tone="secondary">
            {who}
          </AppText>
        ) : null}
        <AppText variant="body" tone="secondary">
          {TYPE_LABELS[record.appointmentType]}
        </AppText>
        <AppText variant="bodyStrong">{record.whenLabel}</AppText>
        {record.locationName ? (
          <AppText variant="body" tone="secondary">
            {record.locationName}
          </AppText>
        ) : null}
        {record.address ? (
          <AppText variant="body" tone="secondary">
            {record.address}
          </AppText>
        ) : null}
        {record.phone ? (
          <AppText variant="body" tone="secondary">
            {record.phone}
          </AppText>
        ) : null}
        <View style={{ flexDirection: 'row', gap: spacing.xs, flexWrap: 'wrap' }}>
          <StatusChip
            label={STATUS_LABELS[record.status]}
            tone={isOpen ? 'info' : 'neutral'}
          />
          {isOpen ? (
            <StatusChip
              label={PREPARATION_LABELS[record.preparationStatus]}
              tone={record.preparationStatus === 'complete' ? 'success' : 'neutral'}
            />
          ) : null}
        </View>
      </View>

      <View style={{ height: spacing.lg }} />

      {isOpen ? (
        <Button
          label={PREPARE_ACTION}
          onPress={() =>
            router.push({
              pathname: '/appointments/[id]/prepare',
              params: { id: record.id },
            })
          }
          accessibilityHint="Reviews what you have recorded so you can choose what to bring"
        />
      ) : null}

      <View style={{ height: spacing.lg }} />

      <View style={{ gap: spacing.lg }}>
        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Questions</AppText>
          <AppText variant="body" tone="secondary">
            {questionCountSentence(record.questionCount + queued.length)}
          </AppText>
          <QuestionList
            questions={record.questions ?? []}
            pending={queued}
            emptyMessage="Nothing added yet."
          />
          <Button
            label={record.questionCount === 0 ? 'Add questions' : 'Edit questions'}
            variant="secondary"
            onPress={() =>
              router.push({
                pathname: '/appointments/[id]/questions',
                params: { id: record.id },
              })
            }
            accessibilityHint="Opens the list of questions for this appointment"
          />
        </Card>

        <Card style={{ gap: spacing.sm }}>
          <AppText variant="heading">Nura health summary</AppText>
          <AppText variant="body" tone="secondary">
            {reportCountSentence(record.reportCount)}
          </AppText>
          {latestReport ? (
            <AppText variant="body" tone="secondary">
              {reportVersionLine(latestReport.version, latestReport.generatedLabel)}
            </AppText>
          ) : null}
          <Button
            label={record.reportCount === 0 ? 'Make a summary' : 'View summaries'}
            variant="secondary"
            onPress={() =>
              router.push({
                pathname:
                  record.reportCount === 0
                    ? '/appointments/[id]/prepare'
                    : '/appointments/[id]/reports',
                params: { id: record.id },
              })
            }
            accessibilityHint="Opens the summaries generated for this appointment"
          />
        </Card>

        {record.notes ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="heading">Notes</AppText>
            <AppText variant="body" tone="secondary">
              {record.notes}
            </AppText>
          </Card>
        ) : null}

        {record.visitNotes ? (
          <Card style={{ gap: spacing.xxs }}>
            <AppText variant="heading">After the visit</AppText>
            <AppText variant="body" tone="secondary">
              {record.visitNotes}
            </AppText>
            {record.followUpDate ? (
              <AppText variant="caption" tone="secondary">
                {`Follow-up: ${record.followUpDate}`}
              </AppText>
            ) : null}
          </Card>
        ) : null}

        <ListGroup>
          <ListRow
            label="Edit appointment"
            leadingIcon="create-outline"
            showChevron
            onPress={() =>
              router.push({
                pathname: '/appointments/[id]/edit',
                params: { id: record.id },
              })
            }
            accessibilityHint="Changes the time, place or details"
          />
          <ListRow
            label={record.remindersEnabled ? 'Reminders are on' : 'Reminders are off'}
            description="A day before, and two hours before."
            leadingIcon="notifications-outline"
            onPress={() =>
              run(() =>
                setReminders.mutate(
                  { appointmentId: record.id, enabled: !record.remindersEnabled },
                  { onError: (cause) => setError(apiErrorMessage(cause)) }
                )
              )
            }
            accessibilityHint={
              record.remindersEnabled ? 'Turns reminders off' : 'Turns reminders on'
            }
          />
          {isOpen ? (
            <ListRow
              label="Mark as completed"
              description="Records that you went. Nura never decides this for you."
              leadingIcon="checkmark-circle-outline"
              onPress={() =>
                run(() =>
                  complete.mutate(
                    { appointmentId: record.id },
                    { onError: (cause) => setError(apiErrorMessage(cause)) }
                  )
                )
              }
              accessibilityHint="Marks this appointment as attended"
            />
          ) : (
            <ListRow
              label="Move back to scheduled"
              leadingIcon="arrow-undo-outline"
              onPress={() =>
                run(() =>
                  reopen.mutate(record.id, {
                    onError: (cause) => setError(apiErrorMessage(cause)),
                  })
                )
              }
              accessibilityHint="Puts this appointment back in the upcoming list"
            />
          )}
          {record.status === 'completed' ? (
            <ListRow
              label="Add follow-up appointment"
              leadingIcon="calendar-outline"
              showChevron
              onPress={() => router.push('/appointments/new')}
              accessibilityHint="Opens the form for a new appointment"
            />
          ) : null}
          {isOpen ? (
            <ListRow
              label="Cancel appointment"
              description="Keeps it in your history."
              leadingIcon="close-circle-outline"
              onPress={() =>
                run(() =>
                  cancel.mutate(record.id, {
                    onError: (cause) => setError(apiErrorMessage(cause)),
                  })
                )
              }
              accessibilityHint="Marks this appointment as cancelled"
            />
          ) : null}
          <ListRow
            label="Delete appointment"
            description="For one added by mistake. This cannot be undone."
            leadingIcon="trash-outline"
            onPress={() =>
              run(() =>
                remove.mutate(record.id, {
                  onSuccess: () => router.replace('/appointments'),
                  onError: (cause) => setError(apiErrorMessage(cause)),
                })
              )
            }
            accessibilityHint="Removes this appointment and its summaries"
          />
        </ListGroup>

        {error ? (
          <AppText variant="body" tone="secondary">
            {error}
          </AppText>
        ) : null}
      </View>
    </Screen>
  );
}
