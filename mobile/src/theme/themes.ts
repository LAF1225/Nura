/**
 * Light and Dark themes.
 *
 * Dark mode is a separate palette, not an inversion of Light (PRD 0, section
 * 11): deep charcoal-teal backgrounds, desaturated teal surfaces, off-white
 * text and muted aqua accents. Pure black is avoided.
 */
import { brand } from './tokens';

export type ThemeName = 'light' | 'dark';

/** What the user chose in More -> Appearance. `system` follows the device. */
export type ThemePreference = 'system' | 'light' | 'dark';

export interface ThemeColors {
  /** App background behind all screens. */
  background: string;
  /** Cards and raised panels. */
  surface: string;
  /** Grouped rows, inset areas, subtle fills. */
  surfaceSecondary: string;
  textPrimary: string;
  textSecondary: string;
  /** Primary accent, for icons, borders and selected states. */
  accent: string;
  /**
   * Accent used as a *filled* background behind `onAccent` text, e.g. the
   * primary button. Deep Teal under white text only reaches 3.8:1, which is
   * fine for UI shapes but short of the 4.5:1 that button labels need, so
   * filled surfaces use this darker step instead.
   */
  accentStrong: string;
  /**
   * Accent colour that is safe to use for *text* on `background`/`surface`.
   * The fill accent alone does not always reach text contrast on light
   * surfaces, so accent-coloured text uses this instead.
   */
  accentText: string;
  /** Secondary accent (mint / aqua) for soft fills and highlights. */
  accentSoft: string;
  /** Foreground colour to use on top of an `accent` fill. */
  onAccent: string;
  border: string;
  tabActive: string;
  tabInactive: string;
  success: string;
  warning: string;
  danger: string;
  info: string;
  /** Scrim behind modal content. */
  overlay: string;
}

export interface Theme {
  name: ThemeName;
  /** Convenience flag for status bar style and picking image variants. */
  isDark: boolean;
  colors: ThemeColors;
}

export const lightTheme: Theme = {
  name: 'light',
  isDark: false,
  colors: {
    background: '#F6FAF9',
    surface: '#FFFFFF',
    surfaceSecondary: '#EAF3F0',
    textPrimary: '#0F2B29',
    textSecondary: '#51625F',
    accent: brand.deepTeal,
    accentStrong: brand.darkTeal,
    accentText: brand.darkTeal,
    accentSoft: brand.mint,
    onAccent: '#FFFFFF',
    border: '#DCE8E5',
    tabActive: brand.darkTeal,
    tabInactive: '#637370',
    success: '#1F7A55',
    warning: '#7A4F00',
    danger: '#B3261E',
    info: '#1F6F92',
    overlay: 'rgba(11, 43, 40, 0.45)',
  },
};

export const darkTheme: Theme = {
  name: 'dark',
  isDark: true,
  colors: {
    background: '#0E1C1B',
    surface: '#162927',
    surfaceSecondary: '#1E3532',
    textPrimary: '#E7F1EF',
    textSecondary: '#A3B8B5',
    accent: brand.aqua,
    accentStrong: brand.aqua,
    accentText: brand.aqua,
    accentSoft: brand.midTeal,
    onAccent: '#08201E',
    border: '#27403D',
    tabActive: brand.aqua,
    tabInactive: '#93AAA7',
    success: '#7FD3A9',
    warning: '#E7BC5A',
    danger: '#F2B8B5',
    info: '#8CC6E6',
    overlay: 'rgba(0, 0, 0, 0.6)',
  },
};

/**
 * What React Native's `useColorScheme()` can report. Note `'unspecified'`,
 * which the platform returns when it has no appearance preference to give us.
 */
export type SystemColorScheme = ThemeName | 'unspecified' | null | undefined;

/**
 * Resolves the stored preference plus the current device appearance into the
 * theme that should actually render. Kept as a plain function so it can be
 * unit-tested without rendering anything.
 *
 * Anything other than an explicit `'dark'` resolves to Light, so an unknown or
 * `'unspecified'` device appearance lands on the safer default.
 */
export function resolveThemeName(
  preference: ThemePreference,
  systemScheme: SystemColorScheme
): ThemeName {
  if (preference === 'system') {
    return systemScheme === 'dark' ? 'dark' : 'light';
  }
  return preference;
}

export function getTheme(name: ThemeName): Theme {
  return name === 'dark' ? darkTheme : lightTheme;
}
