/**
 * The 0-10 severity control (PRD 6, sections 22 and 66).
 *
 * Eleven buttons rather than a slider, for accessibility reasons that are not
 * cosmetic: a slider is hard to land on a specific value with a tremor, its
 * screen-reader behaviour varies by platform, and it gives no way to see that
 * the scale is anchored. Eleven labelled targets of at least 48dp each are
 * unambiguous with a screen reader, with large text, and with an unsteady hand
 * (PRD 6, section 66).
 *
 * Only the two ends are labelled in words. PRD 6 section 22 asks for the scale
 * to be anchored, and deliberately does not ask for the middle to be named --
 * calling 5 "moderate" would turn the user's number into Nura's judgement of how
 * bad things are.
 *
 * `value` may be undefined, because a number is not always the right shape of
 * answer and nothing here forces one (section 22).
 */
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { minTouchTarget, radius, spacing } from '../../../theme/tokens';
import {
  SEVERITY_ANCHOR_HIGH,
  SEVERITY_ANCHOR_LOW,
  SEVERITY_MAX,
  SEVERITY_MIN,
  severityAccessibilityLabel,
} from '../copy';

interface SeverityInputProps {
  value: number | undefined;
  onChange: (value: number) => void;
  /** Lets the user take a number back, since it was never required. */
  onClear?: () => void;
  label?: string;
}

const VALUES = Array.from(
  { length: SEVERITY_MAX - SEVERITY_MIN + 1 },
  (_, index) => index + SEVERITY_MIN
);

export function SeverityInput({ value, onChange, onClear, label }: SeverityInputProps) {
  const theme = useTheme();

  return (
    <View
      style={{ gap: spacing.xs }}
      accessibilityRole="radiogroup"
      accessibilityLabel={label ?? 'How bad it is, from 0 to 10'}
    >
      {label ? <AppText variant="bodyStrong">{label}</AppText> : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs }}>
        {VALUES.map((option) => {
          const selected = value === option;
          return (
            <Pressable
              key={option}
              onPress={() => onChange(option)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={severityAccessibilityLabel(option)}
              style={{
                minWidth: minTouchTarget,
                minHeight: minTouchTarget,
                paddingHorizontal: spacing.xs,
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: radius.md,
                borderWidth: selected ? 2 : 1,
                borderColor: selected ? theme.colors.accent : theme.colors.border,
                backgroundColor: selected
                  ? theme.colors.surfaceSecondary
                  : theme.colors.surface,
              }}
            >
              <AppText variant="bodyStrong" tone={selected ? 'accent' : 'primary'}>
                {String(option)}
              </AppText>
            </Pressable>
          );
        })}
      </View>

      <View
        style={{ flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm }}
      >
        <AppText variant="caption" tone="secondary">
          {SEVERITY_ANCHOR_LOW}
        </AppText>
        <AppText variant="caption" tone="secondary">
          {SEVERITY_ANCHOR_HIGH}
        </AppText>
      </View>

      {value !== undefined && onClear ? (
        <Pressable
          onPress={onClear}
          accessibilityRole="button"
          accessibilityHint="Removes the number you chose"
          style={{ minHeight: minTouchTarget, justifyContent: 'center' }}
        >
          <AppText variant="caption" tone="accent">
            A number doesn’t fit this — remove it
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}
