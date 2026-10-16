/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Questions for the clinician (PRD 7, sections 23, 24 and 39).
 *
 * Two rules are tested rather than read:
 *
 * **A question is stored exactly as typed.** Nothing rewrites it, trims it into
 * a different sentence or expands an abbreviation -- it is going to be read out
 * in a consulting room by the person who wrote it (section 23).
 *
 * **A suggestion is an offer, and accepting it makes an ordinary question.**
 * Nothing is added until the button is pressed, and what lands is
 * indistinguishable from a typed one, because at that point it is theirs
 * (section 24).
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { appointmentFixture, mockBackend, questionFixture, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

beforeEach(async () => {
  await AsyncStorage.clear();
  signInAt('ready_for_pairing');
  backend = mockBackend({
    status: 'ready_for_pairing',
    todayDevice: null,
    appointments: [appointmentFixture()],
    appointmentQuestions: [questionFixture()],
  });
});

afterEach(() => {
  backend.restore();
});

function postedQuestions(): string[] {
  return backend.requests
    .filter((request) => request.method === 'POST' && request.path.endsWith('/questions'))
    .map((request) => String(((request.body ?? {}) as Record<string, unknown>).text));
}

it('keeps the user’s wording, offers neutral prompts, and adds one only on request', async () => {
  renderRouter('app', { initialUrl: '/appointments/appointment-1/questions' });

  await waitFor(() => {
    expect(
      screen.getByText('Could this medication be contributing to my fatigue?')
    ).toBeVisible();
  });

  // The screen says plainly that nothing is reworded (PRD 7, section 23).
  expect(
    screen.getByText(
      'Written exactly as you type them. Nura does not reword your questions.'
    )
  ).toBeVisible();

  // The suggestions are offers, sitting under the list rather than in it.
  expect(
    screen.getByText('Would you like to ask about your worsening headache?')
  ).toBeVisible();
  expect(
    screen.getByText('Would you like to ask whether you need any follow-up tests?')
  ).toBeVisible();
  // Nothing has been added by them being shown.
  expect(postedQuestions()).toEqual([]);

  // Accepting one adds an ordinary question, in the wording the user would use.
  fireEvent.press(screen.getByLabelText('Add question: Do I need any follow-up tests?'));
  await waitFor(() => {
    expect(postedQuestions()).toEqual(['Do I need any follow-up tests?']);
  });
  await waitFor(() => {
    expect(screen.getByText('Do I need any follow-up tests?')).toBeVisible();
  });

  // Marking one answered is a separate act from writing the answer down (s39).
  fireEvent.press(
    screen.getByLabelText(
      'Answered: Could this medication be contributing to my fatigue?'
    )
  );
  await waitFor(() => {
    const patch = backend.requests.find(
      (request) => request.method === 'PATCH' && request.path.includes('/questions/')
    );
    expect(patch).toBeDefined();
  });
  expect(
    (backend.requests.find(
      (request) => request.method === 'PATCH' && request.path.includes('/questions/')
    )?.body ?? {}) as Record<string, unknown>
  ).toEqual({ is_answered: true });

  // And removing one closes the gap without touching the rest.
  fireEvent.press(
    screen.getByLabelText(
      'Remove question: Could this medication be contributing to my fatigue?'
    )
  );
  await waitFor(() => {
    expect(
      backend.requests.some(
        (request) => request.method === 'DELETE' && request.path.includes('/questions/')
      )
    ).toBe(true);
  });
  await waitFor(() => {
    expect(
      screen.queryByText('Could this medication be contributing to my fatigue?')
    ).toBeNull();
  });
});
