/**
 * Nura design tokens.
 *
 * These are the raw, theme-independent values. Anything that varies between
 * Light and Dark lives in `themes.ts` instead. Screens and components should
 * import tokens from here rather than hard-coding numbers.
 */
import { Platform, type ViewStyle } from 'react-native';

/**
 * Brand palette (PRD 0, section 10). These are the identity colours and are
 * referenced by the themes; screens should normally use semantic theme colours
 * (`theme.colors.accent`) rather than reaching for a brand colour directly.
 */
export const brand = {
  darkTeal: '#1C605C',
  deepTeal: '#3D9086',
  midTeal: '#53A9A6',
  aqua: '#7ECFC4',
  mint: '#A5E3D1',
} as const;

/** Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40. */
export const spacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
} as const;

/** Corner radii. `pill` is for fully rounded elements such as status chips. */
export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

export const fontSize = {
  xs: 12,
  sm: 14,
  md: 16,
  lg: 18,
  xl: 22,
  xxl: 28,
  display: 34,
} as const;

export const fontWeight = {
  regular: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
} as const;

export const iconSize = {
  sm: 18,
  md: 24,
  lg: 28,
} as const;

/**
 * Minimum touch target. iOS HIG asks for 44pt, Android for 48dp; 48 satisfies
 * both and is used by every interactive component (PRD 0, section 24).
 */
export const minTouchTarget = 48;

/**
 * Typography note (PRD 0, section 12): no custom font is bundled in PRD 0.
 * React Native's default font is already SF Pro on iOS and Roboto on Android,
 * so we deliberately leave `fontFamily` unset rather than naming a family --
 * naming one risks falling back to a different face on one of the platforms.
 */

/**
 * Restrained elevation. Light surfaces get a soft shadow; Dark mode relies on
 * surface colour and borders instead, since shadows read as muddy on dark
 * backgrounds (PRD 0, section 9: avoid heavy shadows).
 */
export const elevation: Record<'none' | 'card' | 'raised', ViewStyle> = {
  none: {},
  card:
    Platform.select<ViewStyle>({
      ios: {
        shadowColor: '#0B2B28',
        shadowOpacity: 0.06,
        shadowRadius: 10,
        shadowOffset: { width: 0, height: 2 },
      },
      android: { elevation: 2 },
      default: {},
    }) ?? {},
  raised:
    Platform.select<ViewStyle>({
      ios: {
        shadowColor: '#0B2B28',
        shadowOpacity: 0.1,
        shadowRadius: 18,
        shadowOffset: { width: 0, height: 6 },
      },
      android: { elevation: 6 },
      default: {},
    }) ?? {},
};
