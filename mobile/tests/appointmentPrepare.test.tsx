/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Prepare for Appointment, the review step (PRD 7, sections 13-21 and 25).
 *
 * The screen shows what the person recorded and lets them tick what to bring.
 * Three rules are asserted rather than read:
 *
 * **Nothing is chosen for them.** Every symptom starts ticked and each can be
 * unticked; no row is marked recommended or significant, which PRD 7 section 15
 * rules out.
 *
 * **The selections persist.** They live in a store, so moving to the next step
 * and back keeps them (section 32) -- and PRD 7 section 67 asks for exactly this.
 *
 * **Nothing is graded or interpreted.** The dose line is counts with its
 * denominator and no percentage (section 18), and the wellbeing line is three
 * counts (section 20).
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

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  useReportSelectionStore.getState().clear();
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

it('reviews what was recorded and remembers what the user ticked', async () => {
  renderRouter('app', { initialUrl: '/appointments/appointment-1/prepare' });

  await waitFor(() => {
    expect(screen.getByText('Recent symptoms')).toBeVisible();
  });

  // The period, and why it is what it is (PRD 7, section 14).
  expect(screen.getByText('30 August to 28 September 2026')).toBeVisible();
  expect(
    screen.getByText(
      'This appointment isn’t linked to a clinician, so Nura can’t tell when you last saw them. Showing the last 30 days.'
    )
  ).toBeVisible();

  // Each symptom, counted, with the user's own change answer -- and nothing
  // ranking one above another (PRD 7, sections 15 and 16).
  expect(
    screen.getByText('Logged 2 times · Latest severity: 6/10 · Change: worsening')
  ).toBeVisible();
  expect(screen.getByText('Dizziness')).toBeVisible();
  expect(screen.queryByText(/recommended/i)).toBeNull();
  expect(screen.queryByText(/most important/i)).toBeNull();

  // The medication, as the report would list it (PRD 7, section 17).
  expect(screen.getByText('Metformin 500 mg')).toBeVisible();
  expect(screen.getByText('Twice daily')).toBeVisible();

  // Counts, with the denominator in the same sentence and no percentage
  // (PRD 7, section 18).
  expect(screen.getByText('13 of 14 scheduled doses marked taken')).toBeVisible();
  expect(screen.getByText('1 dose skipped')).toBeVisible();
  expect(screen.queryByText(/92%/)).toBeNull();

  // Three counts, no interpretation (PRD 7, section 20).
  expect(
    screen.getByText('Good: 8 days · Okay: 11 days · Not great: 4 days')
  ).toBeVisible();

  // Everything starts ticked, because the narrowing is the user's to do.
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.symptomEpisodeIds).toEqual([
      'episode-1',
      'episode-2',
    ]);
  });

  // Unticking one symptom keeps the other.
  fireEvent.press(screen.getByLabelText('Dizziness'));
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.symptomEpisodeIds).toEqual([
      'episode-1',
    ]);
  });

  // "All the active medications" becomes an explicit list once one is unticked.
  fireEvent.press(screen.getByLabelText('Metformin 500 mg'));
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.medicationIds).toEqual([]);
  });

  // A note the person wrote is offered separately, and is off until ticked
  // (PRD 7, section 16).
  expect(screen.getByText('worse in the mornings')).toBeVisible();
  expect(useReportSelectionStore.getState().selection.symptomNoteEntryIds).toEqual([]);
  fireEvent.press(screen.getByLabelText('worse in the mornings'));
  await waitFor(() => {
    expect(useReportSelectionStore.getState().selection.symptomNoteEntryIds).toEqual([
      'entry-1',
    ]);
  });

  // Moving to the next step and back keeps all of it (PRD 7, section 32).
  fireEvent.press(screen.getByRole('button', { name: 'Next: questions' }));
  await waitFor(() => {
    expect(screen.getByText('Questions for your doctor')).toBeVisible();
  });

  expect(useReportSelectionStore.getState().selection.symptomEpisodeIds).toEqual([
    'episode-1',
  ]);
  expect(useReportSelectionStore.getState().selection.medicationIds).toEqual([]);
  expect(useReportSelectionStore.getState().selection.symptomNoteEntryIds).toEqual([
    'entry-1',
  ]);
});
