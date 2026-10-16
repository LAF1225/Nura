"""Profiles -- the people Nura is set up for (PRD 1, sections 18, 28 and 35).

Authorization rule for every route here: a profile is reachable only through a
join row belonging to the signed-in account. A profile id that exists but
belongs to someone else is answered with 404, not 403, so the endpoint does not
confirm that the id exists (PRD 1, section 54).
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, OwnedProfile
from app.models import AccountProfileRole, Profile, User
from app.schemas.profile import ProfileCreate, ProfileRead, ProfileUpdate, profile_to_read

router = APIRouter(prefix="/profiles", tags=["profiles"])

PROFILE_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found."
)


def _link_for(user: User, profile_id: uuid.UUID) -> AccountProfileRole:
    """The caller's link to this profile, or 404 if there isn't one."""
    for link in user.profile_roles:
        if link.profile_id == profile_id:
            return link
    raise PROFILE_NOT_FOUND


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate, user: CurrentUser, db: DbSession
) -> ProfileRead:
    """Creates a profile and links it to the signed-in account."""
    if payload.role == "self" and any(link.role == "self" for link in user.profile_roles):
        # One "this is me" profile per account. Assisted setup adds a second
        # profile with role `setup_helper`, which is allowed.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This account already has a profile. Update it instead.",
        )

    fields = payload.model_dump(exclude={"role"})
    profile = Profile(**fields)
    link = AccountProfileRole(account=user, profile=profile, role=payload.role)
    db.add(link)
    db.commit()
    db.refresh(profile)
    return profile_to_read(profile, payload.role)


@router.get("/{profile_id}", response_model=ProfileRead)
def read_profile(
    profile_id: uuid.UUID, profile: OwnedProfile, user: CurrentUser
) -> ProfileRead:
    """This profile, if it is one the caller's account is linked to.

    ``OwnedProfile`` does the authorizing, even though ``_link_for`` below
    would reach the same answer from the same table. Two implementations of one
    rule is what PRD 13 section 13 is about: the shared dependency is the one
    the security suite can *see*, so a route using it is covered by the
    cross-boundary walk automatically. ``_link_for`` stays for the role, which
    is a property of the link rather than of the profile.
    """
    return profile_to_read(profile, _link_for(user, profile_id).role)


@router.patch("/{profile_id}", response_model=ProfileRead)
def update_profile(
    profile_id: uuid.UUID,
    payload: ProfileUpdate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
) -> ProfileRead:
    link = _link_for(user, profile_id)

    # exclude_unset so omitted fields keep their current value; an explicit
    # null still clears an optional field, which is how pronouns get removed.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(link.profile, field, value)

    db.commit()
    db.refresh(link.profile)
    return profile_to_read(link.profile, link.role)
