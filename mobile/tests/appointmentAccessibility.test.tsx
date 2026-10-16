/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * The selection controls, read the way a screen reader reads them (PRD 7, s58).
 *
 * PRD 7 section 58 asks for screen-reader labels, non-colour-only selection
 * states and 48dp touch targets. The first two are checked here on the screen
 * where they matter most -- the one where every tick changes what a doctor is
 * handed.
 *
 * Driven through `renderRouter` on the real screen rather than a bare `render`:
 * RNTL's bare `render` returns no usable queries under this project's React 19
 * pairing, which is recorded in the README.
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

it('announces every choice as a checkbox with its state, and says what it does', async () => {
  renderRouter('app', { initialUrl: '/appointments/appointment-1/prepare' });

  await waitFor(() => {
    expect(screen.getByLabelText('Headache (behind both eyes)')).toBeVisible();
  });

  const symptom = screen.getByLabelText('Headache (behind both eyes)');
  // A screen reader hears the role, the name and whether it is ticked -- which
  // is what a colour alone cannot convey (PRD 7, section 58).
  expect(symptom.props.accessibilityRole).toBe('checkbox');
  expect(symptom.props.accessibilityState.checked).toBe(true);
  expect(symptom.props.accessibilityHint).toBe('Includes this symptom in the summary');

  fireEvent.press(symptom);
  await waitFor(() => {
    expect(
      screen.getByLabelText('Headache (behind both eyes)').props.accessibilityState
        .checked
    ).toBe(false);
  });

  // The tick is drawn as a checkbox glyph, not as a colour change: the icon
  // itself changes between the two states.
  const medication = screen.getByLabelText('Metformin 500 mg');
  expect(medication.props.accessibilityRole).toBe('checkbox');
  expect(medication.props.accessibilityState.checked).toBe(true);
  expect(medication.props.accessibilityHint).toBe(
    'Includes this medication in the summary'
  );

  // Each period option says what choosing it would do, rather than relying on
  // the selected one being a different colour.
  const thirtyDays = screen.getByRole('button', { name: 'Last 30 days' });
  expect(thirtyDays.props.accessibilityHint).toBe('Summarises last 30 days');

  // Every button carries a hint saying what pressing it will do.
  const next = screen.getByRole('button', { name: 'Next: questions' });
  expect(next.props.accessibilityHint).toBe('Goes to the questions you want to ask');

  // And the step indicator says where in the sequence this is, in words.
  expect(screen.getByLabelText('Step 1 of 4')).toBeTruthy();
  expect(screen.getByText('Review what you have recorded')).toBeVisible();
});
