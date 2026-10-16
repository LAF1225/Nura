/**
 * The appointments list (PRD 7, sections 41 and 61).
 *
 * Three lists behind one tab bar -- Upcoming, Past, Cancelled -- because that is
 * how PRD 7 section 41 divides them and because they answer three different
 * questions: what is coming, what happened, and what did not.
 *
 * It also drains the offline queue on focus, so an appointment or a question
 * written down on a train reaches the backend as soon as there is a signal
 * (PRD 7, section 53). The phone's reminders are rebuilt by this stack's layout,
 * which is mounted for every appointment route (section 54).
 */
import { useRouter } from 'expo-router';
import { View } from 'react-native';

import {
  AppText,
  AsyncState,
  Button,
  Card,
  Screen,
  SkeletonCard,
} from '../../src/components';
import { OfflineBanner } from '../../src/components/today';
import { AppointmentRow } from '../../src/features/appointments/components/AppointmentRow';
import {
  ADD_APPOINTMENT,
  EMPTY_CANCELLED,
  EMPTY_PAST,
  EMPTY_UPCOMING,
  PENDING_HINT,
  PENDING_LABEL,
} from '../../src/features/appointments/copy';
import {
  useAppointments,
  usePendingAppointments,
  useSyncPendingAppointments,
} from '../../src/features/appointments/hooks';
import { useAppointmentListStore } from '../../src/features/appointments/listStore';
import type { AppointmentScope } from '../../src/features/appointments/types';
import { useIsOffline } from '../../src/hooks/useNetworkStatus';
import { spacing } from '../../src/theme/tokens';

const TABS: { scope: AppointmentScope; label: string; empty: string }[] = [
  { scope: 'upcoming', label: 'Upcoming', empty: EMPTY_UPCOMING },
  { scope: 'past', label: 'Past', empty: EMPTY_PAST },
  { scope: 'cancelled', label: 'Cancelled', empty: EMPTY_CANCELLED },
];

export default function AppointmentsScreen() {
  const router = useRouter();
  const isOffline = useIsOffline();
  // In a store so the chosen list survives opening an appointment and coming
  // back (PRD 7, section 41).
  const scope = useAppointmentListStore((state) => state.scope);
  const setScope = useAppointmentListStore((state) => state.setScope);

  const list = useAppointments(scope);
  const pending = usePendingAppointments();

  // Reminders are rebuilt by the stack's layout, which is mounted for every
  // appointment route (PRD 7, section 54).
  useSyncPendingAppointments();

  const rows = list.data ?? [];
  const queued = pending.data ?? [];
  const tab = TABS.find((entry) => entry.scope === scope) ?? TABS[0]!;

  return (
    <Screen
      onRefresh={() => void list.refetch()}
      refreshing={list.isRefetching && !list.isLoading}
    >
      {isOffline ? <OfflineBanner /> : null}

      <Button
        label={ADD_APPOINTMENT}
        onPress={() => router.push('/appointments/new')}
        accessibilityHint="Opens the form for adding an appointment"
      />

      <View style={{ height: spacing.lg }} />

      {/* A radio group rather than tabs: three mutually exclusive lists, and a
          screen reader should say which one is chosen (PRD 7, section 58). */}
      <View
        accessibilityRole="radiogroup"
        style={{ flexDirection: 'row', gap: spacing.xs }}
      >
        {TABS.map((entry) => (
          <Button
            key={entry.scope}
            label={entry.label}
            variant={entry.scope === scope ? 'primary' : 'secondary'}
            onPress={() => setScope(entry.scope)}
            accessibilityHint={`Shows ${entry.label.toLowerCase()} appointments`}
            style={{ flex: 1 }}
          />
        ))}
      </View>

      <View style={{ height: spacing.lg }} />

      {scope === 'upcoming' && queued.length > 0 ? (
        <View style={{ gap: spacing.xs, marginBottom: spacing.lg }}>
          {queued.map((record) => (
            <Card key={record.clientAppointmentId} style={{ gap: spacing.xxs }}>
              <AppText variant="bodyStrong">{record.displayTitle}</AppText>
              <AppText variant="caption" tone="secondary">
                {`${PENDING_LABEL} · ${PENDING_HINT}`}
              </AppText>
            </Card>
          ))}
        </View>
      ) : null}

      {list.isLoading ? (
        <Card>
          <SkeletonCard lines={3} />
        </Card>
      ) : (
        <AsyncState
          status={list.isError ? 'error' : 'success'}
          error={list.error}
          isEmpty={rows.length === 0}
          emptyMessage={tab.empty}
          onRetry={() => void list.refetch()}
        >
          <View style={{ gap: spacing.xs }}>
            {rows.map((appointment) => (
              <AppointmentRow
                key={appointment.id}
                appointment={appointment}
                onPress={() =>
                  router.push({
                    pathname: '/appointments/[id]',
                    params: { id: appointment.id },
                  })
                }
              />
            ))}
          </View>
        </AsyncState>
      )}
    </Screen>
  );
}
