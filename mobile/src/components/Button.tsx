/**
 * Primary action control.
 *
 * Accessibility (PRD 0, section 24): every button carries an accessible label
 * (falling back to its visible text), announces itself as a button, reports
 * its disabled state, and is at least `minTouchTarget` tall.
 */
import { Pressable, type StyleProp, type ViewStyle } from 'react-native';

import { useTheme } from '../theme';
import { minTouchTarget, radius, spacing } from '../theme/tokens';
import { AppText, type TextTone } from './AppText';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  /** Defaults to `label`. Set when the visible text is not self-explanatory. */
  accessibilityLabel?: string;
  accessibilityHint?: string;
  style?: StyleProp<ViewStyle>;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  accessibilityLabel,
  accessibilityHint,
  style,
}: ButtonProps) {
  const theme = useTheme();

  const background: Record<ButtonVariant, string> = {
    primary: theme.colors.accentStrong,
    secondary: theme.colors.surfaceSecondary,
    ghost: 'transparent',
  };
  const tone: Record<ButtonVariant, TextTone> = {
    primary: 'onAccent',
    secondary: 'primary',
    ghost: 'accent',
  };

  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        {
          minHeight: minTouchTarget,
          justifyContent: 'center',
          alignItems: 'center',
          paddingHorizontal: spacing.lg,
          borderRadius: radius.md,
          backgroundColor: background[variant],
          borderWidth: variant === 'ghost' ? 0 : 1,
          borderColor:
            variant === 'primary' ? theme.colors.accentStrong : theme.colors.border,
          // Dim on press and when disabled. Disabled state is also announced
          // to screen readers above, so this is not the only signal.
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      <AppText variant="bodyStrong" tone={tone[variant]}>
        {label}
      </AppText>
    </Pressable>
  );
}
