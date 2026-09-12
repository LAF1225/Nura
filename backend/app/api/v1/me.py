"""The signed-in account (PRD 1, section 35).

``/me`` is deliberately the only way to read your own account: there is no
``/users/{id}`` that takes an identifier from the client, so there is nothing
to tamper with (PRD 1, section 36).
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.account import AccountRead, SettingsRead, SettingsUpdate
from app.schemas.profile import profile_to_read

router = APIRouter(prefix="/me", tags=["account"])


def account_response(user: User) -> AccountRead:
    """Builds the `/me` body, attaching each profile with the caller's role."""
    return AccountRead(
        id=user.id,
        email=user.email,
        phone=user.phone,
        settings=SettingsRead.model_validate(user.settings),
        profiles=[
            profile_to_read(link.profile, link.role) for link in user.profile_roles
        ],
    )


@router.get("", response_model=AccountRead)
def read_me(user: CurrentUser) -> AccountRead:
    return account_response(user)


@router.patch("", response_model=AccountRead)
def update_me(payload: SettingsUpdate, user: CurrentUser, db: DbSession) -> AccountRead:
    """Updates account preferences: theme, language and accessibility settings.

    Onboarding progress is not changed here -- that is `/onboarding` -- and
    profile details are not either. Keeping them apart means a preferences
    save cannot accidentally move the user through the flow.
    """
    settings = user.settings
    assert settings is not None  # created alongside the account

    # exclude_unset so a PATCH that omits a field leaves it alone, rather than
    # overwriting it with the schema default.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(user)
    return account_response(user)
