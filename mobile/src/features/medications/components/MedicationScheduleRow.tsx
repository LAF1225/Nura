/**
 * One schedule in the schedule list (PRD 5, sections 7, 11 and 37).
 *
 * Reads as a sentence -- "Every day at 8:00 AM and 8:00 PM" -- rather than as
 * a table of rows, because that is how people describe a medication routine
 * and how they will check it is right.
 *
 * A paused schedule says so in words as well as by looking quieter, and says
 * nothing about *why*: Nura does not infer a reason for a pause and does not
 * ask for one (PRD 5, section 37).
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { describeEnd, describeSchedule } from '../schedule';
import type { MedicationSchedule } from '../types';

interface MedicationScheduleRowProps {
  schedule: MedicationSchedule;
  onPress: () => void;
}

export function MedicationScheduleRow({ schedule, onPress }: MedicationScheduleRowProps) {
  const theme = useTheme();
  const pattern = describeSchedule(schedule);
  const until = describeEnd(schedule);
  const paused = !schedule.isActive;

  const name = schedule.medicationDose
    ? `${schedule.medicationName} — ${schedule.medicationDose}`
    : schedule.medicationName;

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${name}. ${pattern}.${paused ? ' Paused.' : ''}`}
      accessibilityHint="Opens this schedule to change or remove it"
      style={({ pressed }) => ({
        minHeight: minTouchTarget,
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        padding: spacing.md,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: pressed ? theme.colors.surfaceSecondary : theme.colors.surface,
      })}
    >
      <View style={{ flex: 1, gap: spacing.xxs }}>
        <AppText variant="bodyStrong">{name}</AppText>
        <AppText variant="body" tone="secondary">
          {pattern}
        </AppText>
        {until ? (
          <AppText variant="caption" tone="secondary">
            {until}
          </AppText>
        ) : null}
        {paused ? (
          // Words, not just a colour or a dimmed row (PRD 5, section 61).
          <AppText variant="caption" tone="secondary">
            Reminders paused
          </AppText>
        ) : null}
      </View>
      <Ionicons
        name="chevron-forward"
        size={iconSize.sm}
        color={theme.colors.textSecondary}
      />
    </Pressable>
  );
}
