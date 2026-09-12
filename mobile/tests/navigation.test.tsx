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

jest.setTimeout(60_000);

/** Tab label -> the route it should open and copy unique to that screen. */
const TAB_ROUTES: { label: string; path: string; content: RegExp }[] = [
  { label: 'Health', path: '/health', content: /health timeline, conditions/ },
  { label: 'Care', path: '/care', content: /Schedules, appointments, routines/ },
  { label: 'Nura', path: '/nura', content: /calm companion for everyday health/ },
  { label: 'More', path: '/more', content: /Light, Dark or System/ },
  { label: 'Today', path: '/', content: /Your daily dashboard will appear here/ },
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
      expect(screen.getByText(/Your daily dashboard will appear here/)).toBeTruthy();
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
