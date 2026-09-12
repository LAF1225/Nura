/**
 * Labelled text input with validation feedback (PRD 1, sections 37 and 40).
 *
 * Accessibility: the label is tied to the field, the error is announced when
 * it appears, and an invalid field is marked as such for screen readers rather
 * than being indicated by a red border alone.
 */
import { forwardRef } from 'react';
import { TextInput, View, type TextInputProps } from 'react-native';

import { useTheme } from '../theme';
import { fontSize, minTouchTarget, radius, spacing } from '../theme/tokens';
import { AppText } from './AppText';

interface TextFieldProps extends Omit<TextInputProps, 'style'> {
  label: string;
  /** Shown under the field and announced. Presence also marks it invalid. */
  error?: string | null;
  /** Quiet guidance shown under the field when there is no error. */
  hint?: string;
}

export const TextField = forwardRef<TextInput, TextFieldProps>(function TextField(
  { label, error, hint, ...inputProps },
  ref
) {
  const theme = useTheme();
  const hasError = Boolean(error);

  return (
    <View style={{ gap: spacing.xxs }}>
      <AppText variant="bodyStrong">{label}</AppText>

      <TextInput
        ref={ref}
        // React Native's AccessibilityState has no "invalid" flag and no
        // aria-invalid on TextInput, so the error is folded into the label.
        // That way focusing the field announces what is wrong, rather than the
        // problem being conveyed by a red border alone.
        accessibilityLabel={hasError ? `${label}. Error: ${error}` : label}
        placeholderTextColor={theme.colors.textSecondary}
        {...inputProps}
        style={{
          minHeight: minTouchTarget,
          paddingHorizontal: spacing.sm,
          paddingVertical: spacing.xs,
          borderRadius: radius.md,
          borderWidth: 1,
          borderColor: hasError ? theme.colors.danger : theme.colors.border,
          backgroundColor: theme.colors.surface,
          color: theme.colors.textPrimary,
          fontSize: fontSize.md,
        }}
      />

      {hasError ? (
        <AppText
          variant="caption"
          tone="danger"
          // Announced as soon as it appears, without stealing focus.
          accessibilityLiveRegion="polite"
        >
          {error}
        </AppText>
      ) : hint ? (
        <AppText variant="caption" tone="secondary">
          {hint}
        </AppText>
      ) : null}
    </View>
  );
});
