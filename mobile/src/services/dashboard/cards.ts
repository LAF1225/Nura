/**
 * Working with a Today layout (PRD 3, sections 17-19 and 59).
 *
 * Pure functions over a card list, kept apart from the screens so the rules --
 * which cards may be shown, what reordering means -- can be read and tested
 * without rendering anything.
 */
import type { DashboardCard, DashboardCardKey } from '../../types/today';

/**
 * Cards this build can actually draw.
 *
 * Two gates, both of which must pass: the server says the feature exists
 * (`available`), and the app has a renderer for the key. A card that passes
 * only one is skipped in silence -- an app and a backend on different versions
 * should degrade, not break.
 */
export function renderableCards(
  cards: DashboardCard[],
  renderers: ReadonlySet<DashboardCardKey>
): DashboardCard[] {
  return cards
    .filter((card) => card.available && renderers.has(card.key))
    .sort((a, b) => a.position - b.position);
}

/** Cards Today should draw right now, in order. */
export function visibleCards(
  cards: DashboardCard[],
  renderers: ReadonlySet<DashboardCardKey>
): DashboardCard[] {
  return renderableCards(cards, renderers).filter((card) => card.visible);
}

/** Cards the customization screen should offer. Never the unavailable ones. */
export function customisableCards(
  cards: DashboardCard[],
  renderers: ReadonlySet<DashboardCardKey>
): DashboardCard[] {
  return renderableCards(cards, renderers);
}

export function toggleCard(
  cards: DashboardCard[],
  key: DashboardCardKey
): DashboardCard[] {
  return cards.map((card) =>
    card.key === key ? { ...card, visible: !card.visible } : card
  );
}

/**
 * Moves a card one place up (`-1`) or down (`+1`).
 *
 * Move-up/move-down rather than drag-and-drop: a drag target is hard to hit,
 * impossible to reach with a screen reader, and PRD 3 section 19 explicitly
 * allows this instead. Positions are renumbered so the list stays canonical,
 * and a move off either end is a no-op rather than an error.
 */
export function moveCard(
  cards: DashboardCard[],
  key: DashboardCardKey,
  offset: -1 | 1
): DashboardCard[] {
  const ordered = [...cards].sort((a, b) => a.position - b.position);
  const index = ordered.findIndex((card) => card.key === key);
  const subject = ordered[index];
  const target = index + offset;
  if (subject === undefined || target < 0 || target >= ordered.length) return cards;

  const moved = ordered.filter((_, position) => position !== index);
  moved.splice(target, 0, subject);
  return moved.map((card, position) => ({ ...card, position }));
}

/** The payload shape the save endpoint expects: order is the order shown. */
export function layoutPayload(
  cards: DashboardCard[]
): { key: DashboardCardKey; visible: boolean }[] {
  return [...cards]
    .sort((a, b) => a.position - b.position)
    .filter((card) => card.available)
    .map((card) => ({ key: card.key, visible: card.visible }));
}
