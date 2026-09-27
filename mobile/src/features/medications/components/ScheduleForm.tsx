/**
 * The reminder schedule form (PRD 5, sections 9, 11 and 61).
 *
 * Presentational: the screen owns the values, and every decision about what
 * they *mean* -- what is refused, what is actually sent, how the pattern reads
 * back -- lives in `schedule.ts`, where it is testable without rendering
 * anything.
 *
 * Times are typed as `HH:MM` with quick chips for the common ones rather than
 * opened in a native picker. That is a deliberate trade: a picker would mean
 * another native dependency and a control that cannot be driven in a test,
 * while a 24-hour field is unambiguous, works with a screen reader, and shows
 * back what it will mean in words ("8:00 AM") as it is typed.
 *
 * There is nowhere here to express a taper, a sliding scale or a calculated
 * dose, and that is the point (PRD 5, section 10).
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { Button } from '../../../components/Button';
import { TextField } from '../../../components/TextField';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import {
  formatTimeOfDay,
  MAX_TIMES,
  SUGGESTED_TIMES,
  WEEKDAYS,
  type ScheduleErrors,
  type ScheduleFormValues,
} from '../schedule';
import type { ScheduleType, Weekday } from '../types';

const PATTERNS: { value: ScheduleType; label: string; hint: string }[] = [
  { value: 'daily', label: 'Every day', hint: 'The same times every day' },
  { value: 'specific_days', label: 'Selected days', hint: 'Only on the days you choose' },
];

interface ChipProps {
  label: string;
  selected: boolean;
  onPress: () => void;
  role?: 'radio' | 'checkbox';
  accessibilityHint?: string;
}

function Chip({
  label,
  selected,
  onPress,
  role = 'radio',
  accessibilityHint,
}: ChipProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole={role}
      accessibilityLabel={label}
      accessibilityState={role === 'checkbox' ? { checked: selected } : { selected }}
      accessibilityHint={accessibilityHint}
      style={({ pressed }) => ({
        minHeight: minTouchTarget,
        justifyContent: 'center',
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.md,
        borderRadius: radius.pill,
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? theme.colors.accentStrong : theme.colors.border,
        backgroundColor:
          selected || pressed ? theme.colors.surfaceSecondary : theme.colors.surface,
      })}
    >
      {/* Selection is announced and is carried by the border width as well as
          by colour, so it survives a colour-vision difference. */}
      <AppText variant="bodyStrong">{label}</AppText>
    </Pressable>
  );
}

interface ScheduleFormProps {
  values: ScheduleFormValues;
  errors: ScheduleErrors;
  disabled?: boolean;
  onChange: (values: ScheduleFormValues) => void;
}

export function ScheduleForm({
  values,
  errors,
  disabled = false,
  onChange,
}: ScheduleFormProps) {
  const theme = useTheme();
  const set = (patch: Partial<ScheduleFormValues>) => onChange({ ...values, ...patch });

  const setTime = (index: number, next: string) =>
    set({ times: values.times.map((entry, at) => (at === index ? next : entry)) });

  const removeTime = (index: number) =>
    set({ times: values.times.filter((_, at) => at !== index) });

  const addTime = (value: string) => {
    if (values.times.includes(value) || values.times.length >= MAX_TIMES) return;
    set({ times: [...values.times, value] });
  };

  const toggleWeekday = (day: Weekday) =>
    set({
      weekdays: values.weekdays.includes(day)
        ? values.weekdays.filter((entry) => entry !== day)
        : [...values.weekdays, day],
    });

  return (
    <View style={{ gap: spacing.lg }}>
      <View style={{ gap: spacing.xs }}>
        <AppText variant="bodyStrong">How often?</AppText>
        <View
          accessibilityRole="radiogroup"
          accessibilityLabel="How often"
          style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}
        >
          {PATTERNS.map((pattern) => (
            <Chip
              key={pattern.value}
              label={pattern.label}
              selected={values.scheduleType === pattern.value}
              onPress={() => set({ scheduleType: pattern.value })}
              accessibilityHint={pattern.hint}
            />
          ))}
        </View>
      </View>

      {values.scheduleType === 'specific_days' ? (
        <View style={{ gap: spacing.xs }}>
          <AppText variant="bodyStrong">Which days?</AppText>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
            {WEEKDAYS.map((day) => (
              <Chip
                key={day.value}
                label={day.short}
                role="checkbox"
                selected={values.weekdays.includes(day.value)}
                onPress={() => toggleWeekday(day.value)}
                accessibilityHint={day.label}
              />
            ))}
          </View>
          {errors.weekdays ? (
            <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">
              {errors.weekdays}
            </AppText>
          ) : null}
        </View>
      ) : null}

      <View style={{ gap: spacing.sm }}>
        <AppText variant="bodyStrong">
          {values.times.length === 1 ? 'Time' : 'Times'}
        </AppText>

        {values.times.map((entry, index) => (
          <View
            key={`time-${index}`}
            style={{ flexDirection: 'row', alignItems: 'flex-end', gap: spacing.xs }}
          >
            <View style={{ flex: 1 }}>
              <TextField
                label={`Time ${index + 1}`}
                value={entry}
                onChangeText={(next) => setTime(index, next)}
                placeholder="08:00"
                keyboardType="numbers-and-punctuation"
                maxLength={5}
                editable={!disabled}
                hint={formatTimeOfDay(entry)}
              />
            </View>
            {values.times.length > 1 ? (
              <Pressable
                onPress={() => removeTime(index)}
                disabled={disabled}
                accessibilityRole="button"
                accessibilityLabel={`Remove time ${index + 1}`}
                style={{
                  minHeight: minTouchTarget,
                  minWidth: minTouchTarget,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: radius.md,
                  borderWidth: 1,
                  borderColor: theme.colors.border,
                  marginBottom: spacing.lg,
                }}
              >
                <Ionicons
                  name="close"
                  size={iconSize.md}
                  color={theme.colors.textSecondary}
                />
              </Pressable>
            ) : null}
          </View>
        ))}

        {errors.times ? (
          <AppText variant="caption" tone="danger" accessibilityLiveRegion="polite">
            {errors.times}
          </AppText>
        ) : null}

        {values.times.length < MAX_TIMES ? (
          <View style={{ gap: spacing.xs }}>
            <AppText variant="caption" tone="secondary">
              Add another time
            </AppText>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
              {SUGGESTED_TIMES.filter((time) => !values.times.includes(time)).map(
                (time) => (
                  <Chip
                    key={time}
                    label={formatTimeOfDay(time)}
                    role="checkbox"
                    selected={false}
                    onPress={() => addTime(time)}
                    accessibilityHint="Adds this time to the schedule"
                  />
                )
              )}
            </View>
          </View>
        ) : null}
      </View>

      <TextField
        label="Start date"
        value={values.startDate}
        onChangeText={(next) => set({ startDate: next })}
        placeholder="2026-09-13"
        editable={!disabled}
        error={errors.startDate}
        hint="YYYY-MM-DD"
      />

      <TextField
        label="End date (optional)"
        value={values.endDate ?? ''}
        onChangeText={(next) => set({ endDate: next.length > 0 ? next : null })}
        placeholder="No end date"
        editable={!disabled}
        error={errors.endDate}
        hint="Leave blank for a medication you take ongoing."
      />

      {/* Stated rather than editable: the zone comes from the phone when the
          schedule is made, and it is what keeps 8am at 8am through a
          daylight-saving change (PRD 5, section 12). */}
      <AppText variant="caption" tone="secondary">
        Reminders use {values.timezone} time.
      </AppText>
    </View>
  );
}

interface ScheduleActionsProps {
  isNew: boolean;
  paused: boolean;
  busy: boolean;
  onSave: () => void;
  onTogglePause: () => void;
  onDelete: () => void;
}

export function ScheduleActions({
  isNew,
  paused,
  busy,
  onSave,
  onTogglePause,
  onDelete,
}: ScheduleActionsProps) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Button
        label={isNew ? 'Save schedule' : 'Save changes'}
        onPress={onSave}
        disabled={busy}
      />
      {isNew ? null : (
        <>
          <Button
            label={paused ? 'Resume reminders' : 'Pause reminders'}
            variant="secondary"
            onPress={onTogglePause}
            disabled={busy}
            accessibilityHint={
              paused
                ? 'Starts reminding you again from now on'
                : 'Stops future reminders. Nothing you have recorded is changed.'
            }
          />
          <Button
            label="Remove this schedule"
            variant="ghost"
            onPress={onDelete}
            disabled={busy}
            accessibilityHint="Stops future reminders and keeps your history"
          />
        </>
      )}
    </View>
  );
}
