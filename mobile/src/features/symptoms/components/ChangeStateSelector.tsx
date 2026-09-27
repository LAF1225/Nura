/**
 * Improving / about the same / worsening / not sure (PRD 6, sections 23 and 66).
 *
 * Four buttons, each with a word and a marker. The marker is an arrow rather
 * than a colour, because PRD 6 section 66 requires change state not to be
 * conveyed by colour alone -- and because "getting worse" in red would be Nura
 * adding alarm to something the user simply reported.
 *
 * "Not sure" is offered as an equal option, not tucked away. It is a real
 * answer and storing it is better than leaving the field blank and guessing
 * later which was meant (PRD 6, section 23).
 */
import { Pressable, View } from 'react-native';

import { AppText } from '../../../components/AppText';
import { useTheme } from '../../../theme';
import { minTouchTarget, radius, spacing } from '../../../theme/tokens';
import { CHANGE_MARKER, CHANGE_STATES } from '../copy';
import type { ChangeState } from '../types';

interface ChangeStateSelectorProps {
  value: ChangeState | undefined;
  onChange: (value: ChangeState) => void;
  label?: string;
}

export function ChangeStateSelector({
  value,
  onChange,
  label,
}: ChangeStateSelectorProps) {
  const theme = useTheme();

  return (
    <View
      style={{ gap: spacing.xs }}
      accessibilityRole="radiogroup"
      accessibilityLabel={label ?? 'How it has changed'}
    >
      {label ? <AppText variant="bodyStrong">{label}</AppText> : null}

      <View style={{ gap: spacing.xs }}>
        {CHANGE_STATES.map((option) => {
          const selected = value === option.value;
          return (
            <Pressable
              key={option.value}
              onPress={() => onChange(option.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={option.label}
              style={{
                minHeight: minTouchTarget,
                flexDirection: 'row',
                alignItems: 'center',
                gap: spacing.sm,
                paddingHorizontal: spacing.md,
                borderRadius: radius.md,
                borderWidth: selected ? 2 : 1,
                borderColor: selected ? theme.colors.accent : theme.colors.border,
                backgroundColor: selected
                  ? theme.colors.surfaceSecondary
                  : theme.colors.surface,
              }}
            >
              {/* Decorative: the label beside it is what a screen reader says. */}
              <AppText
                variant="bodyStrong"
                tone="secondary"
                accessibilityElementsHidden
                importantForAccessibility="no"
              >
                {CHANGE_MARKER[option.value]}
              </AppText>
              <AppText variant="body" tone={selected ? 'accent' : 'primary'}>
                {option.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
