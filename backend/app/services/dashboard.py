"""The Today card registry and a profile's layout (PRD 3, sections 17-20, 59).

Today is a list of cards, not one screen with everything hard-coded into it.
A card is declared here once; the client has a renderer for each key it knows;
a profile's rows say which are shown and in what order.

``available`` is the important flag. A card is listed as soon as its key is
reserved, but it is only offered to the user -- and only rendered -- once the
feature behind it actually exists. That is how the medication and appointment
cards can be named now without showing anybody an empty medication card
(PRD 3, sections 18 and 59).
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DashboardPreference
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


class UnknownCardError(DomainError):
    """A card key that is not in the registry, or not implemented yet."""

    status_code = 422
    code = "unknown_card"


@dataclass(frozen=True)
class CardDefinition:
    """A card Today knows how to place.

    ``title`` is what the customization screen calls it. The card's own
    heading is the client's business -- a renderer may not have one at all.
    """

    key: str
    title: str
    #: False while the feature behind the card does not exist. Such a card is
    #: never shown and cannot be enabled; it is here so a later PRD adds the
    #: renderer rather than re-deciding the key.
    available: bool
    default_visible: bool


#: Order matters: it is the default layout, and the tie-breaker when two saved
#: cards claim the same position.
CARD_REGISTRY: tuple[CardDefinition, ...] = (
    CardDefinition(
        "daily_checkin", "Daily check-in", available=True, default_visible=True
    ),
    # Real from PRD 5, and on by default: a dose that is due is the single
    # most useful thing Today can show. It sits directly under the check-in
    # because it is the card people act on. A profile with no schedules has
    # nothing to draw, so the card is simply absent rather than empty
    # (PRD 5, sections 28 and 29).
    CardDefinition("medications", "Medications", available=True, default_visible=True),
    CardDefinition("device_status", "Nura status", available=True, default_visible=True),
    # Real, but off by default: Today should open calm rather than full
    # (PRD 3, sections 3 and 19).
    CardDefinition(
        "quick_actions", "Quick actions", available=True, default_visible=False
    ),
    # Real from PRD 4, and off by default: the Health tab is where someone
    # looks for their health profile, and Today stays calm unless asked
    # otherwise (PRD 3 section 3; PRD 4 section 47). It shows a percentage and
    # never a condition or medication name.
    CardDefinition(
        "health_profile", "Health profile", available=True, default_visible=False
    ),
    # Real from PRD 6, and on by default -- but it draws nothing at all for
    # anybody who has never logged a symptom, so it stays invisible until it
    # is relevant. Once somebody has used it, it shows what is active or
    # offers a way to log one (PRD 6, section 39).
    CardDefinition("symptoms", "Symptoms", available=True, default_visible=True),
    # Reserved for later PRDs. No renderer, no data, never shown.
    CardDefinition(
        "appointments", "Appointments", available=False, default_visible=False
    ),
    CardDefinition("routines", "Routines", available=False, default_visible=False),
    CardDefinition("hydration", "Hydration", available=False, default_visible=False),
    CardDefinition(
        "physiotherapy", "Physiotherapy", available=False, default_visible=False
    ),
)

REGISTRY_INDEX: dict[str, int] = {
    card.key: index for index, card in enumerate(CARD_REGISTRY)
}
CARDS_BY_KEY: dict[str, CardDefinition] = {card.key: card for card in CARD_REGISTRY}


@dataclass(frozen=True)
class ResolvedCard:
    """A registry entry with this profile's answer applied."""

    key: str
    title: str
    available: bool
    visible: bool
    position: int


@dataclass(frozen=True)
class CardPreferenceInput:
    key: str
    visible: bool


def _stored_preferences(
    db: Session, profile_id: uuid.UUID
) -> dict[str, DashboardPreference]:
    rows = (
        db.execute(
            select(DashboardPreference).where(
                DashboardPreference.profile_id == profile_id
            )
        )
        .scalars()
        .all()
    )
    return {row.card_key: row for row in rows}


def _apply(stored: dict[str, DashboardPreference]) -> list[ResolvedCard]:
    """Every card in the registry, with these stored choices applied.

    Cards the user has never touched fall back to the registry defaults, so a
    card added by a later PRD appears without a data migration. An unavailable
    card is always returned hidden, whatever an older stored row says.
    """
    resolved = []
    for index, card in enumerate(CARD_REGISTRY):
        row = stored.get(card.key)
        visible = card.default_visible if row is None else row.visible
        resolved.append(
            ResolvedCard(
                key=card.key,
                title=card.title,
                available=card.available,
                visible=visible and card.available,
                position=index if row is None else row.position,
            )
        )

    # Position first, then the registry's own order, so a layout saved before
    # a new card existed still renders in a stable order.
    resolved.sort(key=lambda card: (card.position, REGISTRY_INDEX[card.key]))
    # Hand back a canonical 0..n-1 sequence rather than whatever was stored.
    return [
        ResolvedCard(
            key=card.key,
            title=card.title,
            available=card.available,
            visible=card.visible,
            position=index,
        )
        for index, card in enumerate(resolved)
    ]


def resolve_cards(db: Session, profile_id: uuid.UUID) -> list[ResolvedCard]:
    """The layout for one profile."""
    return _apply(_stored_preferences(db, profile_id))


def default_cards() -> list[ResolvedCard]:
    """The layout for an account with no profile yet -- registry defaults only."""
    return _apply({})


def save_cards(
    db: Session, profile_id: uuid.UUID, items: list[CardPreferenceInput]
) -> list[ResolvedCard]:
    """Replaces the profile's layout with ``items``, in the order given.

    The client sends the list it is displaying; position is taken from that
    order rather than from a number the client has to keep consistent, which
    removes the whole class of duplicate-position bugs.
    """
    seen: set[str] = set()
    for item in items:
        card = CARDS_BY_KEY.get(item.key)
        if card is None:
            raise UnknownCardError(f"There is no {item.key} card.")
        if not card.available:
            # Refusing keeps rows for features that do not exist out of the
            # database entirely.
            raise UnknownCardError(f"The {card.title} card is not available yet.")
        if item.key in seen:
            raise UnknownCardError(f"The {card.title} card was listed twice.")
        seen.add(item.key)

    stored = _stored_preferences(db, profile_id)
    for position, item in enumerate(items):
        row = stored.get(item.key)
        if row is None:
            db.add(
                DashboardPreference(
                    profile_id=profile_id,
                    card_key=item.key,
                    visible=item.visible,
                    position=position,
                )
            )
        else:
            row.visible = item.visible
            row.position = position

    db.commit()
    logger.info("dashboard: saved a Today layout of %d cards", len(items))
    return resolve_cards(db, profile_id)
