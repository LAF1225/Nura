/**
 * One appointment in a list (PRD 7, sections 41 and 62).
 *
 * The three lists -- upcoming, past, cancelled -- use the same row, because they
 * are the same thing seen at different times. What changes is the wording
 * underneath: how far away it is, or what happened.
 *
 * Status is shown as a word, never as a colour alone (PRD 7, section 58).
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import {
  clinicianLine,
  PREPARATION_LABELS,
  questionCountSentence,
  STATUS_LABELS,
  TYPE_LABELS,
} from '../copy';
import type { Appointment } from '../types';

interface AppointmentRowProps {
  appointment: Appointment;
  onPress: () => void;
  /** Adds the "Saved on this phone" note for a queued appointment (s53). */
  pendingLabel?: string;
}

export function AppointmentRow({
  appointment,
  onPress,
  pendingLabel,
}: AppointmentRowProps) {
  const theme = useTheme();
  const who =
    clinicianLine(
      appointment.clinician?.name ?? null,
      appointment.clinician?.specialty ?? null
    ) ?? TYPE_LABELS[appointment.appointmentType];

  const isOpen = appointment.status === 'scheduled';

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${appointment.title}, ${appointment.whenLabel}`}
      accessibilityHint="Opens the appointment"
      style={({ pressed }) => ({
        minHeight: minTouchTarget,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.md,
        padding: spacing.md,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: pressed ? theme.colors.surfaceSecondary : theme.colors.surface,
      })}
    >
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{appointment.title}</AppText>
        <AppText variant="body" tone="secondary">
          {who}
        </AppText>
        <AppText variant="body" tone="secondary">
          {appointment.whenLabel}
        </AppText>
        {isOpen ? (
          <AppText variant="caption" tone="secondary">
            {PREPARATION_LABELS[appointment.preparationStatus]}
            {appointment.questionCount > 0
              ? ` · ${questionCountSentence(appointment.questionCount)}`
              : ''}
          </AppText>
        ) : (
          <AppText variant="caption" tone="secondary">
            {STATUS_LABELS[appointment.status]}
            {appointment.reportCount > 0 ? ' · Summary generated' : ''}
          </AppText>
        )}
        {pendingLabel ? (
          <AppText variant="caption" tone="secondary">
            {pendingLabel}
          </AppText>
        ) : null}
      </View>

      <Ionicons
        name="chevron-forward"
        size={iconSize.md}
        color={theme.colors.textSecondary}
        // Decorative: the row already announces itself as a button.
        accessibilityElementsHidden
        importantForAccessibility="no"
      />
    </Pressable>
  );
}
