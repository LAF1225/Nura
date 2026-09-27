/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * One symptom and its history (PRD 6, sections 35, 36, 37, 38 and 91).
 *
 * The history PRD 6 section 36 lays out -- date, severity, how it changed, newest
 * first -- with its photos, and the two ways a symptom can end.
 *
 * The distinction between them is the point of the confirmations asserted here:
 * **Mark as ended** keeps everything and takes it out of the active list
 * (section 37), while **Delete** removes it and says so. A user who wants the
 * first and gets the second has lost months of their own record.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';
import { Alert } from 'react-native';

import {
  mockBackend,
  signInAt,
  symptomEntryFixture,
  symptomEpisodeFixture,
  symptomPhotoFixture,
} from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;
let alertSpy: jest.SpyInstance;

const FIRST = symptomEntryFixture({
  id: 'entry-1',
  recorded_at: '2026-09-25T09:00:00Z',
  severity: 3,
  change_state: null,
  associated_symptoms: [],
});

const SECOND = symptomEntryFixture({
  id: 'entry-2',
  recorded_at: '2026-09-27T14:30:00Z',
  severity: 6,
  change_state: 'worsening',
  associated_symptoms: ['nausea'],
  negated_items: ['vomiting'],
  photos: [symptomPhotoFixture({ symptom_entry_id: 'entry-2' })],
});

beforeEach(() => {
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    symptoms: [
      symptomEpisodeFixture({
        entry_count: 2,
        latest_entry: SECOND,
        entries: [SECOND, FIRST],
        safety: {
          worsening: true,
          reasons: ['reported_worsening', 'severity_increase'],
          notice:
            'You have recorded this as worsening. If it keeps getting worse, becomes ' +
            'severe, or is affecting what you can normally do, consider contacting a ' +
            'healthcare professional.',
          urgent: false,
        },
      }),
    ],
  });
  alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
});

afterEach(() => {
  backend.restore();
  alertSpy.mockRestore();
});

it('shows the history, the reviewed guidance, and asks before ending or deleting', async () => {
  renderRouter('app', { initialUrl: '/symptoms/episode-1' });

  await waitFor(
    () => {
      expect(screen.getByText('Headache — 6/10')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // When it began, at the precision it was recorded (PRD 6, section 74).
  expect(screen.getByText(/this morning/)).toBeTruthy();

  // Both entries, newest first, each with its own number and direction. The
  // latest severity appears twice -- in the heading and on its own row.
  expect(screen.getAllByText(/6\/10/).length).toBeGreaterThanOrEqual(2);
  expect(screen.getByText(/3\/10/)).toBeTruthy();
  expect(screen.getAllByText(/Getting worse/).length).toBeGreaterThan(0);
  // What was denied is shown back, not dropped (PRD 6, section 24).
  expect(screen.getByText(/no vomiting/)).toBeTruthy();

  // The photo is listed, reached through the authenticated route.
  expect(screen.getByLabelText('Photo 1')).toBeTruthy();

  // The reviewed guidance, quietly, and not as an emergency
  // (PRD 6, sections 42 and 44).
  expect(screen.getByText(/consider contacting a healthcare professional/)).toBeTruthy();
  expect(screen.queryByText(/Please get help now/)).toBeNull();

  // --- ending it keeps everything (PRD 6, section 37) ----------------------
  fireEvent.press(screen.getByRole('button', { name: 'Mark as ended' }));

  expect(alertSpy).toHaveBeenCalled();
  const endCall = alertSpy.mock.calls.at(-1);
  expect(String(endCall?.[0])).toContain('ended');
  expect(String(endCall?.[1])).toContain('Everything you have logged is kept');

  // Confirming sends the resolve, which deletes nothing.
  const confirmEnd = (endCall?.[2] as { text: string; onPress?: () => void }[]).find(
    (button) => button.text === 'Mark as ended'
  );
  confirmEnd?.onPress?.();

  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) => request.method === 'POST' && request.path.endsWith('/resolve')
      )
    ).toBe(true);
  });
  expect(backend.requests.some((request) => request.method === 'DELETE')).toBe(false);

  // --- deleting says what goes, and points at the other option -------------
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Delete this symptom' })).toBeTruthy();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Delete this symptom' }));

  const deleteCall = alertSpy.mock.calls.at(-1);
  expect(String(deleteCall?.[0])).toContain('Delete');
  expect(String(deleteCall?.[1])).toContain('photos');
  expect(String(deleteCall?.[1])).toContain('mark it as ended instead');
});
