/**
 * Editing an appointment (PRD 7, sections 8 and 54).
 *
 * The same form as adding one, reading the same store. What is different is what
 * happens after: changing the time invalidates the upcoming list, and the list
 * screen rebuilds the phone's reminders from it -- so a rescheduled appointment
 * reminds at the new time without this screen knowing anything about
 * notifications (PRD 7, section 54).
 */
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';

import { Card, Screen, SkeletonCard } from '../../../src/components';
import { AppointmentForm } from '../../../src/features/appointments/components/AppointmentForm';
import { useAppointmentFormStore } from '../../../src/features/appointments/formStore';
import {
  useAppointment,
  useClinicianOptions,
  useUpdateAppointment,
} from '../../../src/features/appointments/hooks';
import { apiErrorMessage } from '../../../src/services/api';

export default function EditAppointmentScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  const appointment = useAppointment(id);
  const clinicians = useClinicianOptions();
  const update = useUpdateAppointment();

  const draft = useAppointmentFormStore((state) => state.draft);
  const startEdit = useAppointmentFormStore((state) => state.startEdit);
  const clear = useAppointmentFormStore((state) => state.clear);

  const record = appointment.data;

  // On focus rather than on mount, and only once the appointment has loaded: the
  // draft is filled from the stored record, so it cannot be started before there
  // is something to fill it from.
  useFocusEffect(
    useCallback(() => {
      if (record !== undefined) startEdit(record);
    }, [record, startEdit])
  );

  if (record === undefined || draft === null) {
    return (
      <Screen>
        <Card>
          <SkeletonCard lines={4} />
        </Card>
      </Screen>
    );
  }

  const onSave = () => {
    setError(null);
    update.mutate(
      { appointmentId: record.id, draft },
      {
        onSuccess: () => {
          clear();
          router.back();
        },
        onError: (cause) => setError(apiErrorMessage(cause)),
      }
    );
  };

  return (
    <Screen>
      <AppointmentForm
        clinicians={clinicians.options}
        isSaving={update.isPending}
        saveLabel="Save changes"
        onSave={onSave}
        errorMessage={error}
      />
    </Screen>
  );
}
