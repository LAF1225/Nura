/* eslint-disable @typescript-eslint/no-require-imports -- jest.mock factories are hoisted above imports, so they must use require() */
/**
 * Accessibility of the symptom controls (PRD 6, sections 66, 67 and 68).
 *
 * PRD 6 section 66 asks for specific things -- an accessible severity control,
 * change state not conveyed by colour alone, 48dp targets, clear labels, dynamic
 * type -- and each is checked here as a thing rather than assumed from a code
 * review.
 *
 * Driven through the real screen rather than by rendering the components on their
 * own: React Native Testing Library's bare `render` does not return usable queries
 * under this project's React 19 pairing, and a control's accessibility is worth
 * proving where a person actually meets it anyway. The conversation's own
 * screen-reader order is covered in `symptomGuidedFlow.test.tsx`, which asserts
 * that each bubble is announced with its speaker.
 *
 * One `renderRouter` per file (see navigation.test.tsx).
 */
import { renderRouter, screen, waitFor } from 'expo-router/testing-library';

import { CHANGE_MARKER } from '../src/features/symptoms/copy';
import { useSymptomDraftStore } from '../src/features/symptoms/draftStore';
import { minTouchTarget } from '../src/theme/tokens';
import { mockBackend, signInAt } from './helpers';

jest.mock('../src/services/auth/supabaseClient', () =>
  require('./supabaseMock').createSupabaseMock()
);

jest.setTimeout(60_000);

let backend: ReturnType<typeof mockBackend>;

/** A node's flattened style, so a minimum size can be read off it. */
function styleOf(element: { props: { style?: unknown } }): Record<string, unknown> {
  const style = element.props.style;
  const parts = Array.isArray(style) ? style : [style];
  return Object.assign({}, ...parts.filter(Boolean)) as Record<string, unknown>;
}

beforeEach(() => {
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

it('gives every control a label, a 48dp target and a cue that is not colour', async () => {
  renderRouter('app', { initialUrl: '/symptoms/log' });

  await waitFor(
    () => {
      expect(screen.getByLabelText(/How bad is it right now\?/)).toBeTruthy();
    },
    { timeout: 30_000 }
  );

  // --- the severity scale (PRD 6, sections 22 and 66) ----------------------
  // Eleven labelled radios rather than a slider: a slider is hard to land on a
  // value with a tremor and reads inconsistently aloud.
  expect(screen.getByLabelText('0, no symptom')).toBeTruthy();
  expect(screen.getByLabelText('5 out of 10')).toBeTruthy();
  expect(screen.getByLabelText('10, the worst you can imagine')).toBeTruthy();
  // Both ends are anchored in words, and the middle is deliberately not named.
  expect(screen.getByText('0 — no symptom')).toBeTruthy();
  expect(screen.getByText('10 — the worst you can imagine')).toBeTruthy();

  // Eleven severity values plus the four change states.
  const radios = screen.getAllByRole('radio');
  expect(radios).toHaveLength(15);

  for (const radio of radios) {
    expect(styleOf(radio).minHeight).toBeGreaterThanOrEqual(minTouchTarget);
  }
  // Severity buttons are square-ish, so their width matters too.
  for (const label of [
    '0, no symptom',
    '3 out of 10',
    '7 out of 10',
    '10, the worst you can imagine',
  ]) {
    expect(styleOf(screen.getByLabelText(label))).toMatchObject({
      minWidth: minTouchTarget,
    });
  }

  // --- change state (PRD 6, sections 23 and 66) ---------------------------
  expect(screen.getByLabelText('Getting better')).toBeTruthy();
  expect(screen.getByLabelText('About the same')).toBeTruthy();
  expect(screen.getByLabelText('Getting worse')).toBeTruthy();
  // "Not sure" is an equal option, not tucked away (PRD 6, section 23).
  expect(screen.getByLabelText('Not sure')).toBeTruthy();

  // Each carries a marker as well as a word, so direction survives for somebody
  // who cannot tell the colours apart -- and the marker is hidden from a screen
  // reader, which reads the word instead.
  for (const state of ['improving', 'same', 'worsening', 'unsure'] as const) {
    // Absent from the accessibility tree, which is the point: a screen reader
    // reads "Getting worse", not "up arrow, getting worse".
    expect(screen.queryByText(CHANGE_MARKER[state])).toBeNull();

    const marker = screen.getByText(CHANGE_MARKER[state], {
      includeHiddenElements: true,
    });
    expect(marker.props.accessibilityElementsHidden).toBe(true);
    expect(marker.props.importantForAccessibility).toBe('no');
  }
  // Four distinct markers, so the direction never depends on colour.
  expect(new Set(Object.values(CHANGE_MARKER)).size).toBe(4);

  // --- a chosen value is announced, not only shown ------------------------
  // Every option carries `selected`, so a screen reader says which one is set
  // rather than leaving it to the border colour.
  for (const radio of radios) {
    expect(radio.props.accessibilityState).toHaveProperty('selected');
  }
  expect(screen.getByLabelText('6 out of 10').props.accessibilityState.selected).toBe(
    false
  );

  // --- every optional field says so (PRD 6, section 11) -------------------
  for (const field of [
    /When did it start\? \(optional\)/,
    /Where do you feel it\? \(optional\)/,
    /What does it feel like\? \(optional\)/,
    /Anything else along with it\? \(optional\)/,
  ]) {
    expect(screen.getByLabelText(field)).toBeTruthy();
  }
  // The one required field carries no "(optional)".
  expect(screen.getByLabelText('What are you experiencing?')).toBeTruthy();

  // --- dynamic type (PRD 0 section 24; PRD 6 section 66) ------------------
  // Nothing caps the reader's own text size.
  for (const node of screen.getAllByText(/optional/)) {
    expect(node.props.allowFontScaling).not.toBe(false);
  }

  // --- the photo controls are reachable and explained ---------------------
  expect(screen.getByRole('button', { name: 'Take a photo' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Choose a photo' })).toBeTruthy();
  expect(screen.getByText(/does not look at them/)).toBeTruthy();
});
