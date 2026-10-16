/**
 * Adding an appointment (PRD 7, sections 4, 8 and 53).
 *
 * Manual entry, and only manual entry: there is no calendar import in PRD 7 and
 * nothing on this screen suggests one (section 4).
 *
 * A save with no connection is kept on the phone and reported as such rather than
 * failing, which is the draft PRD 7 section 53 asks for. The screen says which
 * happened.
 */
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { View } from 'react-native';

import { AppText, Screen } from '../../src/components';
import { OfflineBanner } from '../../src/components/today';
import { AppointmentForm } from '../../src/features/appointments/components/AppointmentForm';
import { PENDING_HINT, PENDING_LABEL } from '../../src/features/appointments/copy';
import { useAppointmentFormStore } from '../../src/features/appointments/formStore';
import {
  useClinicianOptions,
  useSaveAppointment,
} from '../../src/features/appointments/hooks';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { apiErrorMessage } from '../../src/services/api';
import { spacing } from '../../src/theme/tokens';

export default function NewAppointmentScreen() {
  const router = useRouter();
  const isOffline = useIsOffline();
  const [error, setError] = useState<string | null>(null);

  const draft = useAppointmentFormStore((state) => state.draft);
  const startNew = useAppointmentFormStore((state) => state.startNew);
  const clear = useAppointmentFormStore((state) => state.clear);

  const clinicians = useClinicianOptions();
  const save = useSaveAppointment();

  // On focus rather than on mount: a save clears the store, and an unfocused
  // screen must not start a fresh draft behind the user's back.
  useFocusEffect(
    useCallback(() => {
      startNew();
    }, [startNew])
  );

  const onSave = () => {
    if (draft === null) return;
    setError(null);
    save.mutate(
      { draft },
      {
        onSuccess: (outcome) => {
          clear();
          if (outcome.status === 'synced' && outcome.record !== null) {
            router.replace({
              pathname: '/appointments/[id]',
              params: { id: outcome.record.id },
            });
          } else {
            // Saved on the phone. There is no appointment id yet, so the list is
            // where it can be seen with its pending note.
            router.replace('/appointments');
          }
        },
        onError: (cause) => setError(apiErrorMessage(cause)),
      }
    );
  };

  return (
    <Screen>
      {isOffline ? (
        <View style={{ gap: spacing.xs, marginBottom: spacing.md }}>
          <OfflineBanner />
          <AppText variant="caption" tone="secondary">
            {`${PENDING_LABEL} · ${PENDING_HINT}`}
          </AppText>
        </View>
      ) : null}

      <AppointmentForm
        clinicians={clinicians.options}
        isSaving={save.isPending}
        saveLabel="Save appointment"
        onSave={onSave}
        errorMessage={error}
      />
    </Screen>
  );
}
