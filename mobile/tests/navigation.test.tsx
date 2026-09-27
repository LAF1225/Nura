/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Navigation renders (PRD 0, section 22), and tapping each of Today, Health,
 * Care, Nura and More shows the correct screen with no broken routes
 * (PRD 0, section 39).
 *
 * Runs against the real `app/` directory via expo-router's testing helper, and
 * drives the actual tab bar rather than calling the router directly.
 *
 * One `renderRouter` per test file on purpose: expo-router keeps a
 * module-level router store, and a second mount in the same file interferes
 * with the first. The Appearance screen therefore has its own file.
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { mockBackend, signInAt } from './helpers';

// Stands in for a configured Supabase project so the auth gate can let us in.
jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(() => {
  // The auth gate only lets a signed-in, fully onboarded user reach the main
  // tabs; without this every render would redirect to the welcome screen.
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing' });
});

afterEach(() => {
  backend.restore();
});

/** Tab label -> the route it should open and copy unique to that screen. */
const TAB_ROUTES: { label: string; path: string; content: RegExp }[] = [
  { label: 'Health', path: '/health', content: /health timeline, conditions/ },
  // PRD 5 gave Care its first real section, so the placeholder sentence it
  // used to be identified by has gone.
  { label: 'Care', path: '/care', content: /Reminders, schedules and the people/ },
  { label: 'Nura', path: '/nura', content: /calm companion for everyday health/ },
  { label: 'More', path: '/more', content: /Light, Dark or System/ },
  { label: 'Today', path: '/', content: /Nothing needs your attention right now/ },
];

/**
 * The tab bar labels buttons as "Health, tab, 2 of 5", so match on the prefix.
 */
function tabButton(label: string) {
  return screen.getByRole('button', { name: new RegExp(`^${label}, tab`) });
}

it('renders the app shell and navigates between all five tabs', async () => {
  const router = renderRouter('app', { initialUrl: '/' });

  // The root layout holds render until the persisted theme has been read back,
  // so the first assertion waits for hydration.
  await waitFor(
    () => {
      expect(screen.getByText(/Nothing needs your attention right now/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // All five tabs exist, in the locked order (PRD 0, section 8).
  const labels = screen
    .getAllByRole('button')
    .map((node) => String(node.props.accessibilityLabel ?? ''))
    .filter((label) => label.includes(', tab, '));
  expect(labels.map((label) => label.split(',')[0])).toEqual([
    'Today',
    'Health',
    'Care',
    'Nura',
    'More',
  ]);

  for (const { label, path, content } of TAB_ROUTES) {
    fireEvent.press(tabButton(label));

    await waitFor(() => {
      expect(router.getPathname()).toBe(path);
    });
    expect(screen.getByText(content)).toBeTruthy();
  }
});
