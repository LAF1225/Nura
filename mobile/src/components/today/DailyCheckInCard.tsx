/**
 * The daily wellbeing check-in (PRD 3, sections 9-13, 42 and 45).
 *
 * Three things this card is careful about:
 *
 * **One tap.** Choosing an answer submits it. Asking someone to pick a mood
 * and then press Save turns a small daily courtesy into a form.
 *
 * **No guilt.** There is no streak, no "you missed yesterday", no red state.
 * Missing a day is not a failure (PRD 3, section 13).
 *
 * **No interpretation.** "Not great" is acknowledged exactly as warmly as
 * "Good". Nura does not tell anyone what their answer might mean
 * (PRD 3, section 45).
 */
import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { useTheme } from '../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../theme/tokens';
import type { DailyCheckIn, WellbeingLevel } from '../../types/today';
import { AppText } from '../AppText';
import { Button } from '../Button';
import { Card } from '../Card';
import { StatusChip } from '../StatusChip';
import { TextField } from '../TextField';
import { checkInSentence, WELLBEING_OPTIONS } from './wellbeing';

/** Matches the backend's column, so the field cannot accept an unstorable note. */
const NOTE_MAX_LENGTH = 280;

interface WellbeingChoiceProps {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  selected: boolean;
  disabled?: boolean;
  onPress: () => void;
}

function WellbeingChoice({
  label,
  icon,
  selected,
  disabled,
  onPress,
}: WellbeingChoiceProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      // `radio` so a screen reader announces the group as a choice of one, and
      // says which is selected -- the selection is never colour alone.
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityState={{ selected, disabled: Boolean(disabled) }}
      style={({ pressed }) => ({
        flex: 1,
        minHeight: minTouchTarget + spacing.lg,
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.xxs,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.xs,
        borderRadius: radius.md,
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? theme.colors.accentStrong : theme.colors.border,
        backgroundColor: selected
          ? theme.colors.surfaceSecondary
          : pressed
            ? theme.colors.surfaceSecondary
            : theme.colors.surface,
        opacity: disabled ? 0.6 : 1,
      })}
    >
      <Ionicons
        name={icon}
        size={iconSize.lg}
        color={selected ? theme.colors.accentText : theme.colors.textSecondary}
      />
      {/* Text is always present, never an icon on its own. */}
      <AppText variant="bodyStrong" style={{ textAlign: 'center' }}>
        {label}
      </AppText>
    </Pressable>
  );
}

interface DailyCheckInCardProps {
  /** Today's answer, from the backend or from the on-device queue. */
  checkIn: DailyCheckIn | null;
  /** True while a submission is in flight. */
  isSaving?: boolean;
  /** Set when the last attempt failed for a reason worth showing. */
  errorMessage?: string | null;
  /** Days in the recent window that have a check-in (PRD 3, section 12). */
  recentCompletedCount?: number;
  onSubmit: (level: WellbeingLevel, note: string | null) => void;
}

export function DailyCheckInCard({
  checkIn,
  isSaving = false,
  errorMessage,
  recentCompletedCount = 0,
  onSubmit,
}: DailyCheckInCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [note, setNote] = useState(checkIn?.note ?? '');

  const answered = checkIn !== null;
  const pending = checkIn?.syncStatus === 'pending';
  const choosing = !answered || isEditing;

  const choose = (level: WellbeingLevel) => {
    const trimmed = note.trim();
    onSubmit(level, trimmed.length > 0 ? trimmed : null);
    setIsEditing(false);
  };

  return (
    <Card style={{ gap: spacing.md }}>
      <View style={{ gap: spacing.xxs }}>
        <AppText variant="heading">
          {choosing ? 'How are you feeling today?' : 'Today’s check-in'}
        </AppText>
        {answered && !choosing ? (
          <AppText variant="body" tone="secondary">
            {checkInSentence(checkIn.wellbeingLevel, pending)}
          </AppText>
        ) : null}
      </View>

      {choosing ? (
        <>
          <View
            accessibilityRole="radiogroup"
            accessibilityLabel="How are you feeling today?"
            style={{ flexDirection: 'row', gap: spacing.xs }}
          >
            {WELLBEING_OPTIONS.map((option) => (
              <WellbeingChoice
                key={option.level}
                label={option.label}
                icon={option.icon}
                selected={checkIn?.wellbeingLevel === option.level}
                disabled={isSaving}
                onPress={() => choose(option.level)}
              />
            ))}
          </View>

          <TextField
            label="Add a note (optional)"
            value={note}
            onChangeText={setNote}
            placeholder="Anything you want to remember about today"
            maxLength={NOTE_MAX_LENGTH}
            multiline
          />

          {isEditing ? (
            <Button
              label="Cancel"
              variant="ghost"
              onPress={() => {
                setNote(checkIn?.note ?? '');
                setIsEditing(false);
              }}
            />
          ) : null}
        </>
      ) : (
        <>
          {checkIn.note ? <AppText variant="body">{checkIn.note}</AppText> : null}

          {/* PRD 3, section 45: an acknowledgement, and nothing that reads as
              an assessment of how they are. */}
          <AppText variant="body" tone="secondary">
            Thanks for checking in.
          </AppText>

          <Button
            label="Change"
            variant="secondary"
            onPress={() => {
              setNote(checkIn.note ?? '');
              setIsEditing(true);
            }}
            accessibilityHint="Lets you change today’s check-in"
          />
        </>
      )}

      {pending ? (
        <StatusChip
          label="Saved on this phone — will sync when you’re back online"
          tone="info"
          icon="cloud-offline-outline"
        />
      ) : null}

      {errorMessage ? (
        <AppText variant="caption" tone="secondary">
          {errorMessage}
        </AppText>
      ) : null}

      {recentCompletedCount > 0 ? (
        // A plain count. No streaks, no charts, nothing that turns a daily
        // courtesy into a target (PRD 3, sections 12 and 13).
        <AppText variant="caption" tone="secondary">
          {recentCompletedCount === 1
            ? 'This week: 1 check-in completed'
            : `This week: ${recentCompletedCount} check-ins completed`}
        </AppText>
      ) : null}
    </Card>
  );
}
