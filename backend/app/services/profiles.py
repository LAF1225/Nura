"""Which profile a request is about (PRD 1, section 34; PRD 3, section 15).

Every per-person record -- a check-in, a dashboard layout, later a medication
-- belongs to a *profile*, not to the account that saved it. In assisted setup
those differ, and it is the person Nura is for whose day is being described.

The rule enforced here: an account reaches a profile only through its own join
row. A profile id that exists but belongs to someone else is not found, the
same answer as one that never existed.
"""

import uuid

from app.models import Profile, User
from app.services.errors import DomainError, NotFoundError


class NoProfileError(DomainError):
    """The account has not created a profile yet, so there is nobody to be about."""

    status_code = 409
    code = "profile_required"


class ProfileNotFoundError(NotFoundError):
    code = "profile_not_found"


def primary_profile(user: User) -> Profile | None:
    """The person this account's Nura is for, when the caller does not say.

    In assisted setup that is the person being helped rather than the account
    holder; otherwise it is the account holder's own profile. Falls back to
    whatever single profile exists so an account part-way through setup still
    resolves to something sensible.
    """
    preferred_role = "setup_helper" if user.setup_mode == "assisted" else "self"
    for link in user.profile_roles:
        if link.role == preferred_role:
            return link.profile
    return user.profile_roles[0].profile if user.profile_roles else None


def primary_profile_id(user: User) -> uuid.UUID | None:
    profile = primary_profile(user)
    return profile.id if profile is not None else None


def resolve_profile(user: User, requested_id: uuid.UUID | None) -> Profile:
    """The profile a request is for, or a refusal.

    ``requested_id`` is checked against the caller's own links, so a client
    cannot address someone else's profile by guessing its id.
    """
    if requested_id is not None:
        for link in user.profile_roles:
            if link.profile_id == requested_id:
                return link.profile
        raise ProfileNotFoundError("Profile not found.")

    profile = primary_profile(user)
    if profile is None:
        raise NoProfileError("Add a profile before checking in.")
    return profile
