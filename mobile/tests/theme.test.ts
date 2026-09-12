/**
 * Theme preference behaviour (PRD 0, section 22).
 *
 * Covers the pure resolution rules, the store transition the Appearance screen
 * drives, and that the choice actually reaches disk so it survives a restart.
 *
 * The palette reaching rendered styles is covered by themeRendering.test.tsx.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { useAppStore } from '../src/store/appStore';
import { darkTheme, getTheme, lightTheme, resolveThemeName } from '../src/theme/themes';

const STORAGE_KEY = 'nura-app-state';

/** Zustand's persist middleware writes asynchronously. */
const flushWrites = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('resolveThemeName', () => {
  it('follows the device when the preference is "system"', () => {
    expect(resolveThemeName('system', 'dark')).toBe('dark');
    expect(resolveThemeName('system', 'light')).toBe('light');
  });

  it('falls back to light when the device appearance is not usable', () => {
    expect(resolveThemeName('system', null)).toBe('light');
    expect(resolveThemeName('system', undefined)).toBe('light');
    // React Native reports this when the platform has no preference.
    expect(resolveThemeName('system', 'unspecified')).toBe('light');
  });

  it('lets an explicit choice override the device', () => {
    expect(resolveThemeName('light', 'dark')).toBe('light');
    expect(resolveThemeName('dark', 'light')).toBe('dark');
  });
});

describe('getTheme', () => {
  it('returns a distinct palette per theme, not an inversion', () => {
    expect(getTheme('light')).toBe(lightTheme);
    expect(getTheme('dark')).toBe(darkTheme);
    expect(darkTheme.colors.background).not.toBe(lightTheme.colors.background);
    // Dark mode must avoid pure black (PRD 0, section 11).
    expect(darkTheme.colors.background.toLowerCase()).not.toBe('#000000');
  });
});

describe('theme preference store', () => {
  beforeEach(() => {
    useAppStore.setState({ themePreference: 'system' });
  });

  it('defaults to following the system', () => {
    expect(useAppStore.getState().themePreference).toBe('system');
  });

  it('changes the resolved theme when the preference changes', () => {
    const { setThemePreference } = useAppStore.getState();

    setThemePreference('dark');
    expect(useAppStore.getState().themePreference).toBe('dark');
    expect(
      getTheme(resolveThemeName(useAppStore.getState().themePreference, 'light'))
    ).toBe(darkTheme);

    setThemePreference('light');
    expect(
      getTheme(resolveThemeName(useAppStore.getState().themePreference, 'dark'))
    ).toBe(lightTheme);
  });
});

describe('theme preference persistence', () => {
  it('writes the chosen preference to storage so it survives a restart', async () => {
    useAppStore.getState().setThemePreference('dark');
    await flushWrites();

    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    expect(stored).toBeTruthy();
    expect(JSON.parse(stored as string).state.themePreference).toBe('dark');
  });

  it('persists only preferences -- never the auth session', async () => {
    // Tokens belong in secure storage, not AsyncStorage (PRD 0, section 18).
    useAppStore.setState({
      session: { userId: 'u1', provider: 'email', expiresAt: '2030-01-01T00:00:00Z' },
    });
    useAppStore.getState().setThemePreference('light');
    await flushWrites();

    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    const persisted = JSON.parse(stored as string).state;

    expect(Object.keys(persisted).sort()).toEqual([
      'selectedDeviceId',
      'themePreference',
    ]);
    expect(persisted).not.toHaveProperty('session');
  });
});
