/**
 * Themed text. Use this instead of React Native's `Text` so typography and
 * colour always come from tokens.
 *
 * Font scaling is left enabled (React Native's default) so the app honours the
 * reader's system text-size setting (PRD 0, section 24).
 */
import { Text, type TextProps } from 'react-native';

import { useTheme } from '../theme';
import { fontSize, fontWeight } from '../theme/tokens';

export type TextVariant =
  'display' | 'title' | 'heading' | 'body' | 'bodyStrong' | 'caption';

export type TextTone =
  'primary' | 'secondary' | 'accent' | 'success' | 'warning' | 'danger' | 'onAccent';

interface AppTextProps extends TextProps {
  variant?: TextVariant;
  tone?: TextTone;
}

const VARIANTS: Record<
  TextVariant,
  { fontSize: number; fontWeight: '400' | '500' | '600' | '700'; lineHeight: number }
> = {
  display: { fontSize: fontSize.display, fontWeight: fontWeight.bold, lineHeight: 40 },
  title: { fontSize: fontSize.xxl, fontWeight: fontWeight.semibold, lineHeight: 34 },
  heading: { fontSize: fontSize.xl, fontWeight: fontWeight.semibold, lineHeight: 28 },
  body: { fontSize: fontSize.md, fontWeight: fontWeight.regular, lineHeight: 24 },
  bodyStrong: { fontSize: fontSize.md, fontWeight: fontWeight.medium, lineHeight: 24 },
  caption: { fontSize: fontSize.sm, fontWeight: fontWeight.regular, lineHeight: 20 },
};

export function AppText({
  variant = 'body',
  tone = 'primary',
  style,
  ...rest
}: AppTextProps) {
  const theme = useTheme();

  const colors: Record<TextTone, string> = {
    primary: theme.colors.textPrimary,
    secondary: theme.colors.textSecondary,
    accent: theme.colors.accentText,
    success: theme.colors.success,
    warning: theme.colors.warning,
    danger: theme.colors.danger,
    onAccent: theme.colors.onAccent,
  };

  return <Text style={[VARIANTS[variant], { color: colors[tone] }, style]} {...rest} />;
}
