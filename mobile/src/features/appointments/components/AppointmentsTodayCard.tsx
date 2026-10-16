/**
 * The Today appointments card (PRD 7, sections 9 and 10).
 *
 * Unlike the medication and symptom cards, this one draws something for
 * everybody: PRD 7 section 9 gives the empty state its own wording -- "No
 * upcoming appointments", with a way to add one -- because checking when the next
 * visit is, or noting one down, is a reason people open the app.
 *
 * Nothing on it is styled as an alert. An appointment is somewhere to be, and
 * PRD 7 section 10 says outright that one in Important Today is not an emergency.
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { Card } from '../../../components/Card';
import { spacing } from '../../../theme/tokens';
import {
  ADD_APPOINTMENT,
  clinicianLine,
  EMPTY_UPCOMING,
  PREPARATION_LABELS,
  PREPARE_ACTION,
  TODAY_CARD_TITLE,
  TYPE_LABELS,
  upcomingCountSentence,
} from '../copy';
import type { TodayAppointments } from '../types';

interface AppointmentsTodayCardProps {
  appointments: TodayAppointments | null;
}

export function AppointmentsTodayCard({ appointments }: AppointmentsTodayCardProps) {
  const router = useRouter();

  // Null only for an account with no profile yet, which has nobody to see a
  // doctor. Everything else draws.
  if (appointments === null) return null;

  const next = appointments.next;

  if (next === null) {
    return (
      <Card style={{ gap: spacing.sm }}>
        <AppText variant="heading">Appointments</AppText>
        <AppText variant="body" tone="secondary">
          {EMPTY_UPCOMING}
        </AppText>
        <Button
          label={ADD_APPOINTMENT}
          variant="secondary"
          onPress={() => router.push('/appointments/new')}
          accessibilityHint="Opens the form for adding an appointment"
        />
      </Card>
    );
  }

  const who = clinicianLine(next.clinicianName, next.clinicianSpecialty);
  const prepared = next.preparationStatus === 'complete';

  return (
    <Card style={{ gap: spacing.sm }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">{TODAY_CARD_TITLE}</AppText>
        <AppText variant="bodyStrong">{next.title}</AppText>
        {who ? (
          <AppText variant="body" tone="secondary">
            {who}
          </AppText>
        ) : (
          <AppText variant="body" tone="secondary">
            {TYPE_LABELS[next.appointmentType]}
          </AppText>
        )}
        <AppText variant="body" tone="secondary">
          {next.whenLabel}
        </AppText>
        <AppText variant="caption" tone="secondary">
          {PREPARATION_LABELS[next.preparationStatus]}
        </AppText>
        {appointments.upcomingCount > 1 ? (
          <AppText variant="caption" tone="secondary">
            {upcomingCountSentence(appointments.upcomingCount)}
          </AppText>
        ) : null}
      </View>

      <Button
        label={prepared ? 'View summary' : PREPARE_ACTION}
        onPress={() =>
          router.push({
            pathname: prepared
              ? '/appointments/[id]/reports'
              : '/appointments/[id]/prepare',
            params: { id: next.appointmentId },
          })
        }
        accessibilityHint={
          prepared
            ? 'Opens the summaries generated for this appointment'
            : 'Reviews what you have recorded so you can choose what to bring'
        }
      />
    </Card>
  );
}
