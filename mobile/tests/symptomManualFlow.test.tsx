/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Logging a symptom by hand (PRD 6, sections 4, 11, 25, 30, 59 and 91).
 *
 * The manual half of PRD 6 section 4's promise: the same draft, the same review
 * screen and the same request as the guided flow, differing only in the `source`
 * the server records.
 *
 * **Typing is genuinely exercised here**, unlike the health and schedule forms.
 * Every field on this screen writes into a Zustand store rather than into local
 * component state, and a store update does re-render under React 19 -- which is
 * why the whole form could be driven the way a user drives it. That was the
 * reason for putting the draft in a store in the first place.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { useSymptomDraftStore } from '../src/features/symptoms/draftStore';
import {
  clearAllPendingEntries,
  loadPendingEntries,
} from '../src/features/symptoms/pendingEntries';
import { ApiError } from '../src/services/api/errors';
import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(90_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await clearAllPendingEntries();
  signInAt('ready_for_pairing');
  backend = mockBackend({ status: 'ready_for_pairing', todayDevice: null, symptoms: [] });
  useSymptomDraftStore.setState({
    draft: null,
    conversation: null,
    episodeName: null,
    recurOf: null,
    hydrated: true,
  });
  useSymptomDraftStore.getState().start('manual_app');
});

afterEach(() => {
  backend.restore();
  useSymptomDraftStore.getState().clear();
});

it('fills in a symptom, reviews it, and keeps it on the phone when there is no signal', async () => {
  renderRouter('app', { initialUrl: '/symptoms/log' });

  await waitFor(
    () => {
      expect(screen.getByLabelText('What are you experiencing?')).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // Every field is optional except the first, and says so (PRD 6, section 11).
  expect(screen.getByLabelText(/When did it start\? \(optional\)/)).toBeTruthy();
  expect(screen.getByLabelText(/Where do you feel it\? \(optional\)/)).toBeTruthy();

  // --- typing -------------------------------------------------------------
  fireEvent.changeText(screen.getByLabelText('What are you experiencing?'), 'Headache');
  fireEvent.changeText(
    screen.getByLabelText(/When did it start\? \(optional\)/),
    'this morning'
  );
  fireEvent.changeText(
    screen.getByLabelText(/Where do you feel it\? \(optional\)/),
    'behind both eyes'
  );
  fireEvent.changeText(
    screen.getByLabelText(/Anything else along with it\? \(optional\)/),
    'nausea, light sensitivity'
  );

  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft?.mainSymptom).toBe('Headache');
  });
  // A comma-separated answer becomes a list, as the server stores it.
  expect(useSymptomDraftStore.getState().draft?.associatedSymptoms).toEqual([
    'nausea',
    'light sensitivity',
  ]);

  // --- the severity scale (PRD 6, sections 22 and 66) ----------------------
  // Anchored at both ends, and every point is its own labelled target.
  expect(screen.getByText('0 — no symptom')).toBeTruthy();
  expect(screen.getByText('10 — the worst you can imagine')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('6 out of 10'));

  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft?.severity).toBe(6);
  });

  // --- how it is going (PRD 6, section 23) --------------------------------
  fireEvent.press(screen.getByLabelText('Getting worse'));
  await waitFor(() => {
    expect(useSymptomDraftStore.getState().draft?.changeState).toBe('worsening');
  });

  // --- the review screen --------------------------------------------------
  // Waiting on the button, not only on the store: it stays disabled until the
  // symptom has a name, and a press that arrives before the screen re-renders
  // lands on a disabled control and correctly does nothing.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Review and save' })).toBeEnabled();
  });
  fireEvent.press(screen.getByRole('button', { name: 'Review and save' }));

  await waitFor(() => {
    expect(screen.getByText('Review symptom')).toBeTruthy();
  });
  expect(screen.getByLabelText('Symptom: Headache')).toBeTruthy();
  expect(screen.getByLabelText('Where: behind both eyes')).toBeTruthy();
  expect(screen.getByLabelText('How bad: 6/10')).toBeTruthy();
  expect(screen.getByLabelText('Along with it: nausea, light sensitivity')).toBeTruthy();
  expect(screen.getByLabelText('Compared with last time: Getting worse')).toBeTruthy();

  // The reviewed worsening guidance is shown here, above Save, and does not
  // block it (PRD 6, sections 42 and 77).
  expect(screen.getByText(/consider contacting a healthcare professional/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();

  // --- saving with no signal (PRD 6, section 59) --------------------------
  const online = globalThis.fetch;
  globalThis.fetch = (async () => {
    throw new ApiError('offline', 'no connection');
  }) as typeof fetch;

  fireEvent.press(screen.getByRole('button', { name: 'Save' }));

  await waitFor(async () => {
    expect(await loadPendingEntries()).toHaveLength(1);
  });

  const queued = await loadPendingEntries();
  // Nothing was lost: the whole description is on the phone, with the flow it
  // came from and the id that makes a retry safe.
  expect(queued[0]?.episode?.name).toBe('Headache');
  expect(queued[0]?.episode?.first_noticed_text).toBe('this morning');
  expect(queued[0]?.entry.severity).toBe(6);
  expect(queued[0]?.entry.change_state).toBe('worsening');
  expect(queued[0]?.entry.associated_symptoms).toEqual(['nausea', 'light sensitivity']);
  expect(queued[0]?.entry.source).toBe('manual_app');
  expect(String(queued[0]?.clientEntryId)).toMatch(/^entry-/);

  globalThis.fetch = online;
});
