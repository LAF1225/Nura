/**
 * Working with a Today layout (PRD 3, sections 17-19, 59 and 64).
 *
 * The rules that keep a card off the screen matter most here: a card whose
 * feature does not exist must not be rendered, offered, or storable.
 */
import {
  customisableCards,
  layoutPayload,
  moveCard,
  renderableCards,
  visibleCards,
} from '../src/services/dashboard/cards';
import type { DashboardCard, DashboardCardKey } from '../src/types/today';

const RENDERERS: ReadonlySet<DashboardCardKey> = new Set([
  'daily_checkin',
  'device_status',
  'quick_actions',
]);

function card(
  key: DashboardCardKey,
  position: number,
  overrides: Partial<DashboardCard> = {}
): DashboardCard {
  return {
    key,
    title: key,
    available: true,
    visible: true,
    position,
    ...overrides,
  };
}

const LAYOUT: DashboardCard[] = [
  card('daily_checkin', 0),
  card('device_status', 1),
  card('quick_actions', 2, { visible: false }),
  card('medications', 3, { available: false, visible: false }),
];

describe('renderableCards', () => {
  it('drops cards whose feature does not exist yet', () => {
    expect(renderableCards(LAYOUT, RENDERERS).map((entry) => entry.key)).toEqual([
      'daily_checkin',
      'device_status',
      'quick_actions',
    ]);
  });

  it('drops a card this build has no renderer for', () => {
    // An app older than the backend degrades rather than crashing.
    const withFutureCard = [...LAYOUT, card('symptoms', 4)];
    expect(
      renderableCards(withFutureCard, RENDERERS).map((entry) => entry.key)
    ).not.toContain('symptoms');
  });

  it('refuses to render an unavailable card even if it is marked visible', () => {
    const tampered = [card('medications', 0, { available: false, visible: true })];
    expect(renderableCards(tampered, RENDERERS)).toEqual([]);
  });
});

describe('visibleCards', () => {
  it('returns only the shown cards, in order', () => {
    expect(visibleCards(LAYOUT, RENDERERS).map((entry) => entry.key)).toEqual([
      'daily_checkin',
      'device_status',
    ]);
  });
});

describe('customisableCards', () => {
  it('offers hidden cards too, but never unavailable ones', () => {
    const offered = customisableCards(LAYOUT, RENDERERS).map((entry) => entry.key);
    expect(offered).toContain('quick_actions');
    expect(offered).not.toContain('medications');
  });
});

describe('moveCard', () => {
  it('moves a card down and renumbers the layout', () => {
    const moved = moveCard(LAYOUT, 'daily_checkin', 1);
    expect(moved.map((entry) => entry.key)).toEqual([
      'device_status',
      'daily_checkin',
      'quick_actions',
      'medications',
    ]);
    expect(moved.map((entry) => entry.position)).toEqual([0, 1, 2, 3]);
  });

  it('moves a card up', () => {
    const moved = moveCard(LAYOUT, 'quick_actions', -1);
    expect(moved.map((entry) => entry.key)).toEqual([
      'daily_checkin',
      'quick_actions',
      'device_status',
      'medications',
    ]);
  });

  it('does nothing at either end', () => {
    expect(moveCard(LAYOUT, 'daily_checkin', -1)).toBe(LAYOUT);
    expect(moveCard(LAYOUT, 'medications', 1)).toBe(LAYOUT);
  });

  it('does nothing for a card that is not in the layout', () => {
    expect(moveCard(LAYOUT, 'hydration', 1)).toBe(LAYOUT);
  });

  it('keeps visibility while reordering', () => {
    const moved = moveCard(LAYOUT, 'quick_actions', -1);
    expect(moved.find((entry) => entry.key === 'quick_actions')?.visible).toBe(false);
  });
});

describe('layoutPayload', () => {
  it('sends display order, and never an unavailable card', () => {
    expect(layoutPayload(moveCard(LAYOUT, 'device_status', -1))).toEqual([
      { key: 'device_status', visible: true },
      { key: 'daily_checkin', visible: true },
      { key: 'quick_actions', visible: false },
    ]);
  });
});
