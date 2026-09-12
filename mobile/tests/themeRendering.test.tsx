/**
 * Theme applied end to end (PRD 0, sections 22 and 27).
 *
 * `theme.test.ts` covers the resolution rules in isolation. This mounts the
 * real app and checks the chosen palette actually reaches rendered styles, so
 * a break anywhere in store -> ThemeProvider -> component is caught.
 *
 * One `renderRouter` per test file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useAppStore } from '../src/store/appStore';
import { darkTheme, lightTheme } from '../src/theme/themes';

jest.setTimeout(60_000);

/** Flattens a React Native style prop into one object. */
function flattenStyle(style: unknown): Record<string, unknown> {
  if (Array.isArray(style)) {
    return Object.assign({}, ...style.map(flattenStyle));
  }
  if (style && typeof style === 'object') {
    return style as Record<string, unknown>;
  }
  return {};
}

it('renders the dark palette when Dark is chosen, not the light one', async () => {
  // Chosen explicitly, so this does not depend on the host's appearance.
  useAppStore.setState({ themePreference: 'dark' });

  renderRouter('app', { initialUrl: '/' });

  const body = await waitFor(
    () => screen.getByText(/Your daily dashboard will appear here/),
    { timeout: 30_000 }
  );

  const { color } = flattenStyle(body.props.style);
  expect(color).toBe(darkTheme.colors.textSecondary);
  expect(color).not.toBe(lightTheme.colors.textSecondary);

  // Switching live re-themes the same mounted tree, which is what makes the
  // Appearance screen feel immediate.
  useAppStore.getState().setThemePreference('light');

  await waitFor(() => {
    const next = screen.getByText(/Your daily dashboard will appear here/);
    expect(flattenStyle(next.props.style).color).toBe(lightTheme.colors.textSecondary);
  });
});
