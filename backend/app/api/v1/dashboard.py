"""Which cards a profile wants on Today (PRD 3, sections 19 and 20).

The whole layout is read and written at once. A partial update would mean the
client and server negotiating positions card by card; sending the list in
display order means the order *is* the answer.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, http_error
from app.models import Profile, User
from app.schemas.today import (
    DashboardCardRead,
    DashboardPreferencesRead,
    DashboardPreferencesUpdate,
)
from app.services import dashboard as dashboard_service
from app.services import profiles as profile_service
from app.services.errors import DomainError

router = APIRouter(prefix="/dashboard-preferences", tags=["today"])

ProfileQuery = Annotated[
    uuid.UUID | None,
    Query(description="Defaults to the person this account's Nura is for."),
]


def _profile(user: User, profile_id: uuid.UUID | None) -> Profile | None:
    """The profile whose layout this is, or None for an account without one.

    A missing profile is not an error here: Today still renders during setup,
    so the defaults are a perfectly good answer.
    """
    try:
        return profile_service.resolve_profile(user, profile_id)
    except profile_service.NoProfileError:
        return None
    except DomainError as error:
        raise http_error(error) from error


def _read(
    profile: Profile | None, cards: list[dashboard_service.ResolvedCard]
) -> DashboardPreferencesRead:
    return DashboardPreferencesRead(
        profile_id=None if profile is None else profile.id,
        cards=[DashboardCardRead(**vars(card)) for card in cards],
    )


@router.get("", response_model=DashboardPreferencesRead)
def read_dashboard_preferences(
    user: CurrentUser, db: DbSession, profile_id: ProfileQuery = None
) -> DashboardPreferencesRead:
    """Every card the server knows about, with this profile's choices applied."""
    profile = _profile(user, profile_id)
    cards = (
        dashboard_service.default_cards()
        if profile is None
        else dashboard_service.resolve_cards(db, profile.id)
    )
    return _read(profile, cards)


@router.put("", response_model=DashboardPreferencesRead)
def save_dashboard_preferences(
    payload: DashboardPreferencesUpdate, user: CurrentUser, db: DbSession
) -> DashboardPreferencesRead:
    """Replaces the layout. Cards left out keep their current setting."""
    try:
        profile = profile_service.resolve_profile(user, payload.profile_id)
        cards = dashboard_service.save_cards(
            db,
            profile.id,
            [
                dashboard_service.CardPreferenceInput(
                    key=card.card_key, visible=card.visible
                )
                for card in payload.cards
            ],
        )
    except DomainError as error:
        raise http_error(error) from error
    return _read(profile, cards)
