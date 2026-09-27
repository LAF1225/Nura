/**
 * Taken, Snooze and Skip (PRD 5, sections 16, 18, 19 and 61).
 *
 * The three actions every scheduled dose must support, wherever a dose is
 * shown. Written once so they behave identically on Today, on the medication
 * screen and in the history -- three copies would be three chances for one of
 * them to lose a label or a touch target.
 *
 * Accessibility, all of it required by PRD 5 section 61 and none of it
 * optional here: every control carries visible text as well as an icon, is at
 * least 48dp, announces itself as a button, and takes its meaning from words
 * rather than from colour. There are deliberately no icon-only controls.
 *
 * Snooze opens its durations in place rather than navigating, and Skip
 * navigates to a screen where a reason can be chosen -- because a reason is
 * optional and a modal that can be dismissed without answering is the honest
 * way to offer something optional (PRD 5, section 19).
 */
import { Ionicons } from '@expo/vector-icons';
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { iconSize, minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { SNOOZE_OPTIONS } from '../doses';

interface ActionProps {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  disabled?: boolean;
  emphasis?: boolean;
  accessibilityHint?: string;
}

function DoseAction({
  label,
  icon,
  onPress,
  disabled = false,
  emphasis = false,
  accessibilityHint,
}: ActionProps) {
  const theme = useTheme();

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled }}
      style={({ pressed }) => ({
        flex: 1,
        minHeight: minTouchTarget,
        alignItems: 'center',
        justifyContent: 'center',
        gap: spacing.xxs,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.xs,
        borderRadius: radius.md,
        borderWidth: emphasis ? 2 : 1,
        borderColor: emphasis ? theme.colors.accentStrong : theme.colors.border,
        backgroundColor: pressed
          ? theme.colors.surfaceSecondary
          : emphasis
            ? theme.colors.surfaceSecondary
            : theme.colors.surface,
        opacity: disabled ? 0.5 : 1,
      })}
    >
      <Ionicons
        name={icon}
        size={iconSize.md}
        color={emphasis ? theme.colors.accentText : theme.colors.textSecondary}
      />
      {/* Always text, never an icon on its own (PRD 5, section 61). */}
      <AppText variant="bodyStrong" style={{ textAlign: 'center' }}>
        {label}
      </AppText>
    </Pressable>
  );
}

interface DoseActionButtonsProps {
  /** False once the snooze limit is reached. Taken and Skip stay available. */
  canSnooze: boolean;
  /** True while the snooze durations are showing. */
  choosingSnooze?: boolean;
  busy?: boolean;
  onTaken: () => void;
  onSnooze: (minutes: number) => void;
  onOpenSnooze: () => void;
  onSkip: () => void;
}

export function DoseActionButtons({
  canSnooze,
  choosingSnooze = false,
  busy = false,
  onTaken,
  onSnooze,
  onOpenSnooze,
  onSkip,
}: DoseActionButtonsProps) {
  if (choosingSnooze) {
    return (
      <View style={{ gap: spacing.xs }}>
        <AppText variant="bodyStrong">Remind me again in</AppText>
        <View style={{ flexDirection: 'row', gap: spacing.xs }}>
          {SNOOZE_OPTIONS.map((option) => (
            <DoseAction
              key={option.minutes}
              label={option.label}
              icon="time-outline"
              disabled={busy}
              onPress={() => onSnooze(option.minutes)}
            />
          ))}
        </View>
      </View>
    );
  }

  return (
    <View style={{ flexDirection: 'row', gap: spacing.xs }}>
      <DoseAction
        label="Taken"
        icon="checkmark-circle-outline"
        emphasis
        disabled={busy}
        onPress={onTaken}
        accessibilityHint="Records this dose as taken"
      />
      <DoseAction
        label="Snooze"
        icon="alarm-outline"
        disabled={busy || !canSnooze}
        onPress={onOpenSnooze}
        accessibilityHint={
          canSnooze
            ? 'Choose how long to wait before being reminded again'
            : 'This dose has already been snoozed a few times'
        }
      />
      <DoseAction
        label="Skip"
        icon="close-circle-outline"
        disabled={busy}
        onPress={onSkip}
        accessibilityHint="Records this dose as not taken, with an optional reason"
      />
    </View>
  );
}
