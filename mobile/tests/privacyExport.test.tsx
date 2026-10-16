/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Exporting your data, on screen (PRD 13, sections 17 to 20, 43 and 50).
 *
 * The screen's job is to say what the file is *before* offering to make one.
 * Section 18 requires an archive that is explicitly requested, private,
 * temporary and free of secrets, and none of that is verifiable by somebody
 * who was not told. So the assertions below are mostly about three sentences
 * being present -- including the one about tokens, which the client's parser
 * requires rather than reads optionally.
 *
 * One `renderRouter` per file, as every screen test here has.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { dataExportFixture, mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(120_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('onboarding_complete');
});

afterEach(() => {
  backend?.restore();
});

it('says what the archive is, shows a ready one, and offers to delete it', async () => {
  backend = mockBackend({
    status: 'onboarding_complete',
    exports: [
      dataExportFixture(),
      // A failed one, so section 20's states are visible rather than hidden:
      // an export that did not finish is something somebody should be told
      // about, not something that quietly vanishes.
      dataExportFixture({
        id: 'export-0',
        status: 'failed',
        status_label: 'That export did not finish',
        downloadable: false,
        failure_reason: 'Nura could not finish building this export.',
        expires_at: null,
        generated_at: null,
        byte_size: null,
        file_count: 0,
      }),
    ],
  });

  renderRouter('app', { initialUrl: '/privacy/export' });

  await waitFor(() => {
    expect(screen.getByText('What is included')).toBeTruthy();
  });

  // --- what it is (section 18) --------------------------------------------
  expect(
    screen.getByText(/A single private file holding everything recorded/)
  ).toBeTruthy();
  expect(screen.getByText(/not emailed anywhere/)).toBeTruthy();
  // The sentence the parser requires. A screen that offered an export without
  // it would be dropping the one claim that makes the offer safe to accept.
  expect(
    screen.getByText(/no passwords, sign-in tokens, invitation links or device secrets/)
  ).toBeTruthy();
  // And what would be in it, before it is asked for.
  expect(screen.getByText(/profile, health, medications/)).toBeTruthy();

  // --- the one that is waiting --------------------------------------------
  expect(screen.getByText('Ready to download')).toBeTruthy();
  expect(screen.getByText('11 files')).toBeTruthy();
  expect(screen.getByText('47 KB')).toBeTruthy();
  expect(screen.getByText('Delete this export')).toBeTruthy();

  // Section 53's repeat-export case, said rather than discovered through a
  // refusal: one at a time, and the offer to make another is not shown.
  expect(screen.getByText(/one export at a time/)).toBeTruthy();
  expect(screen.queryByText('Create an export')).toBeNull();

  // --- the one that failed (section 20) -----------------------------------
  expect(screen.getByText('That export did not finish')).toBeTruthy();
  expect(screen.getByText('Nura could not finish building this export.')).toBeTruthy();

  // --- and nothing says the file was saved anywhere (section 35) ----------
  // A download is the operating system's business once the request succeeds,
  // so the screen says "ready" and never "saved".
  for (const forbidden of [/\bSaved\b/, /\bSynced\b/, /\bDelivered\b/]) {
    expect(screen.queryByText(forbidden)).toBeNull();
  }
});
