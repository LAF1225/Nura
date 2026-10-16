/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Choosing, generating, previewing and sharing a summary (PRD 7, ss25, 27, 32-34).
 *
 * The end of the flow, in one pass: turn a section off, turn the appendix on,
 * generate, read the preview, and press Share.
 *
 * Two things are asserted that are easy to get wrong:
 *
 * **The preview is the report's own frozen content**, not a re-render of the
 * review -- so what somebody approves and what they export cannot disagree
 * (PRD 7, sections 30 and 32).
 *
 * **Sharing hands over the file that was just downloaded** (section 67's "share
 * uses generated file"), and Nura sends it nowhere itself (section 34).
 *
 * `expo-file-system` and `expo-sharing` are recording stubs. No report PDF has
 * ever been shared from a phone; the README says so.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useReportSelectionStore } from '../src/features/appointments/selectionStore';
import { appointmentFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

const downloads: { url: string; destination: string }[] = [];
const shares: { uri: string }[] = [];

jest.mock('expo-file-system', () => {
  class FakeDirectory {
    uri: string;
    exists = true;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((part) => String((part as any)?.uri ?? part)).join('/');
    }
    create() {}
    list() {
      return [];
    }
  }
  class FakeFile {
    uri: string;
    constructor(...parts: unknown[]) {
      this.uri = parts.map((part) => String((part as any)?.uri ?? part)).join('/');
    }
    static downloadFileAsync = async (url: string, destination: { uri: string }) => {
      downloads.push({ url, destination: destination.uri });
      return destination;
    };
  }
  return {
    Directory: FakeDirectory,
    File: FakeFile,
    Paths: { cache: { uri: 'file:///cache' } },
  };
});

jest.mock('expo-sharing', () => ({
  isAvailableAsync: async () => true,
  shareAsync: async (uri: string) => {
    shares.push({ uri });
  },
}));

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  downloads.length = 0;
  shares.length = 0;
  await AsyncStorage.clear();
  useReportSelectionStore.getState().clear();
  useReportSelectionStore.getState().start('appointment-1');
  useReportSelectionStore.getState().setSymptoms(['episode-1', 'episode-2']);
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [appointmentFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

it('chooses the content, generates a summary, previews it and shares the file', async () => {
  renderRouter('app', { initialUrl: '/appointments/appointment-1/select' });

  await waitFor(() => {
    expect(
      screen.getByText('Only what you tick will appear in the summary.')
    ).toBeVisible();
  });

  // Every section is a switch, and only what is ticked appears (s25).
  expect(screen.getByLabelText('Questions for the clinician')).toBeVisible();
  expect(screen.getByLabelText('Daily check-ins')).toBeVisible();

  fireEvent.press(screen.getByLabelText('Daily check-ins'));
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.include.daily_checkins).toBe(
      false
    );
  });
  // The switch itself must show it, not just the store behind it.
  await waitFor(() => {
    expect(
      screen.getByLabelText('Daily check-ins').props.accessibilityState.checked
    ).toBe(false);
  });

  // The appendix is a toggle with its own explanation (s27).
  expect(
    screen.getByText(
      'Adds the full symptom timeline and dose history after the one-page summary.'
    )
  ).toBeVisible();
  // A Switch, so the event is a value change rather than a press.
  fireEvent(
    screen.getByLabelText('Include detailed history appendix'),
    'valueChange',
    true
  );
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.includeAppendix).toBe(true);
  });
  // Waited for on the control rather than in the store: a press that arrives
  // before the re-render would read a stale selection, which is the harness fact
  // the README records.
  await waitFor(() => {
    expect(screen.getByLabelText('Include detailed history appendix').props.value).toBe(
      true
    );
  });

  // Photos are counted and explicitly left out of the PDF (s28).
  expect(
    screen.getByText(
      'You have 1 symptom photo. Photos stay in Nura and are not put in the PDF.'
    )
  ).toBeVisible();

  fireEvent.press(screen.getByRole('button', { name: 'Make the summary' }));

  await waitFor(() => {
    const post = backend.requests.find(
      (request) => request.method === 'POST' && request.path.endsWith('/reports')
    );
    expect(post).toBeDefined();
  });

  const sent = (backend.requests.find(
    (request) => request.method === 'POST' && request.path.endsWith('/reports')
  )?.body ?? {}) as Record<string, any>;
  expect(sent.selection.include.daily_checkins).toBe(false);
  expect(sent.selection.include_appendix).toBe(true);
  expect(sent.selection.symptom_episode_ids).toEqual(['episode-1', 'episode-2']);
  // A fresh id per press, so a double tap makes one version (s31).
  expect(String(sent.client_report_id)).toMatch(/^report-/);

  // The preview renders the report's own frozen content (s30, s32).
  await waitFor(() => {
    expect(screen.getByText('Nura Health Summary')).toBeVisible();
  });
  expect(
    screen.getByText(
      'This is exactly what the PDF will say. You can go back and change it.'
    )
  ).toBeVisible();
  expect(screen.getByText('Logged 2 times during this period.')).toBeVisible();
  expect(screen.getByText('Severity ranged from 3/10 to 6/10.')).toBeVisible();
  // The disclaimer travels with the report, not with the screen (s45).
  expect(
    screen.getByText(
      'This is a summary of information recorded in the Nura app. It is not a diagnosis, an assessment or medical advice.'
    )
  ).toBeVisible();
  // Named the way PRD 7 section 31 names it.
  expect(
    screen.getByText('Report v1 · 28 September 2026, 9:15 AM · 1 page')
  ).toBeVisible();

  // Going back to change the selections is offered, not forced (s32).
  expect(screen.getByRole('button', { name: 'Change what is included' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Regenerate' })).toBeVisible();

  // Nothing has been exported until the button is pressed (s13).
  expect(downloads).toEqual([]);

  fireEvent.press(screen.getByRole('button', { name: 'Share or save PDF' }));

  await waitFor(() => {
    expect(downloads.length).toBe(1);
  });
  // Downloaded from the authenticated route, with the safe filename (s33, s52).
  expect(downloads[0]?.url).toContain('/reports/report-1/pdf');
  expect(downloads[0]?.destination).toContain('Nura_Health_Summary_2026-09-28.pdf');

  // And shared -- the same file, nowhere Nura chose (s34).
  await waitFor(() => {
    expect(shares.length).toBe(1);
  });
  expect(shares[0]?.uri).toBe(downloads[0]?.destination);
});
