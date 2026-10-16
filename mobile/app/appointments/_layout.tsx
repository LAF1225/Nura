/**
 * The appointment stack (PRD 7, sections 5, 11, 13 and 61).
 *
 * Reached from Care -- which is where the operational side of looking after
 * yourself lives -- and from the Today card.
 *
 *     Health = what the record says
 *     Care   = reminders, schedules, appointments
 *
 * Its own stack rather than a section of Care because Prepare for Appointment is
 * a sequence of screens with state carried between them, and a tab cannot hold
 * that.
 */
import { Stack } from 'expo-router';

import {
  useAppointmentReminders,
  useUpcomingAppointments,
} from '../../src/features/appointments/hooks';
import { useTheme } from '../../src/theme';

export default function AppointmentsLayout() {
  const theme = useTheme();

  // The phone's reminders are rebuilt here rather than on one screen, because
  // this layout is mounted for every appointment route -- so creating, editing,
  // cancelling or completing one reschedules without each screen having to
  // remember to (PRD 7, section 54). Every write invalidates the upcoming list,
  // which is what this reads.
  const upcoming = useUpcomingAppointments();
  useAppointmentReminders(upcoming.data);

  return (
    <Stack
      screenOptions={{
        contentStyle: { backgroundColor: theme.colors.background },
        headerStyle: { backgroundColor: theme.colors.background },
        headerTintColor: theme.colors.textPrimary,
        headerTitleStyle: { color: theme.colors.textPrimary },
        headerShadowVisible: false,
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Appointments' }} />
      <Stack.Screen name="new" options={{ title: 'Add appointment' }} />
      <Stack.Screen name="[id]/index" options={{ title: '' }} />
      <Stack.Screen name="[id]/edit" options={{ title: 'Edit appointment' }} />
      <Stack.Screen name="[id]/prepare" options={{ title: 'Prepare' }} />
      <Stack.Screen name="[id]/questions" options={{ title: 'Questions' }} />
      <Stack.Screen name="[id]/select" options={{ title: 'What to include' }} />
      <Stack.Screen name="[id]/preview" options={{ title: 'Preview' }} />
      <Stack.Screen name="[id]/reports" options={{ title: 'Summaries' }} />
    </Stack>
  );
}
