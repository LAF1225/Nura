"""Who may see what, and the one place that decides it.

PRD 9, sections 7, 9, 10, 18, 52, 57 and 61.

Everything in this module exists to make one sentence true: **a caregiver
reaches a category only through an active relationship that was explicitly
granted it.** Section 9 says permissions are enforced server-side and that
hiding UI is not authorization, and section 61 asks for a reusable helper
rather than the same checks copied across routes. This is that helper.

**The caregiver path is separate from the owner path, deliberately.**
``deps.get_owned_profile`` walks ``account_profile_roles`` and is what every
PRD 0-8 route authorizes through. Nothing here touches that table, so a
caregiver remains unable to reach a single route written before PRD 9 -- the
complete health record, symptom photos, doctor reports, the assistant's own
conversations. They reach the narrower caregiver routes, which return less
(sections 18, 19 and 67).

**A missing permission and a missing relationship give the same answer.**
Both are 404, for the reason the whole codebase answers 404 rather than 403:
a 403 confirms that something exists. Section 18 goes further and says the
*absence* of a permission must not leak information, so a caregiver without
``symptoms`` cannot tell from the API whether this person has ever recorded
one.

**A role grants nothing.** ``relationship.role`` is never read here. Section 10
says roles are descriptive and section 54 that changing one must not expand
access; the way to be sure is for the authorization code not to know the
column exists.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaregiverPermission, CaregiverRelationship, Profile, User
from app.models.enums import (
    CAREGIVER_ACTIVE_STATUSES,
    CAREGIVER_PERMISSION_KEYS,
    CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE,
)
from app.services.errors import NotFoundError
from app.services.profiles import resolve_profile

logger = logging.getLogger(__name__)

#: What a new invitation grants when the inviter names nothing. Empty: section
#: 66 forbids a broad default permission, and section 15 requires the caregiver
#: to be shown what they will be able to see -- a list that fills itself in is
#: not a thing anybody consented to.
DEFAULT_PERMISSIONS: frozenset[str] = frozenset()


class CareAccessError(NotFoundError):
    """No such profile for this account, or no such permission on it.

    One error for both, so the API cannot accidentally distinguish them.
    """

    code = "not_found"


@dataclass(frozen=True)
class CareScope:
    """Who is asking, about whom, and what they are allowed to see.

    Built once per request by ``resolve_scope`` and passed down. Routes and
    services read ``allows(...)``; nothing recomputes the answer, so there is
    one place a permission decision can be wrong.
    """

    profile: Profile
    #: True when the caller is the person themselves (or their setup helper).
    #: An owner has every category, because the owner's own routes already
    #: return everything -- there is nothing for a permission to protect them
    #: from.
    is_owner: bool
    #: Null for an owner. The active relationship, for a caregiver.
    relationship: CaregiverRelationship | None
    #: The categories granted. Every key for an owner.
    granted: frozenset[str]

    @property
    def account_kind(self) -> str:
        """``primary_user`` or ``caregiver``, for the audit trail."""
        return "primary_user" if self.is_owner else "caregiver"

    def allows(self, permission_key: str) -> bool:
        return permission_key in self.granted

    def require(self, permission_key: str) -> None:
        """Raises unless this scope was granted ``permission_key``.

        The log line names the category and never the profile or the account:
        a line saying which person a caregiver was refused symptom access to is
        itself a disclosure (section 69).
        """
        assert permission_key in CAREGIVER_PERMISSION_KEYS, permission_key
        if permission_key not in self.granted:
            logger.info("caregivers: refused access to %s", permission_key)
            raise CareAccessError("Not found.")

    def usable(self, permission_key: str) -> bool:
        """Granted *and* backed by something that exists.

        ``safety_alerts`` and ``routines`` can be granted and stored faithfully
        but unlock no data yet -- section 94 for the first, and the absence of
        any routine record anywhere in PRD 0-9 for the second. The caregiver
        screens use this to say so plainly rather than showing an empty section
        that looks like "nothing recorded".
        """
        return self.allows(permission_key) and (
            permission_key not in CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE
        )


def permission_map(relationship: CaregiverRelationship) -> dict[str, bool]:
    """Every category with its answer, including the ones with no row.

    Always returns all of ``CAREGIVER_PERMISSION_KEYS``: a screen that only
    lists the keys that happen to have rows is a screen that silently stops
    offering a category somebody added.
    """
    stored = {row.permission_key: row.allowed for row in relationship.permissions}
    return {key: stored.get(key, False) for key in CAREGIVER_PERMISSION_KEYS}


def granted_keys(relationship: CaregiverRelationship) -> frozenset[str]:
    """The categories this relationship may use, or nothing if it is not active.

    The status check is here rather than at the call sites, which is what makes
    section 52's "permissions stop immediately" true by construction: a revoked
    relationship has its permission rows intact and is granted nothing.
    """
    if relationship.status not in CAREGIVER_ACTIVE_STATUSES:
        return frozenset()
    return frozenset(
        key for key, allowed in permission_map(relationship).items() if allowed
    )


def set_permissions(
    db: Session,
    relationship: CaregiverRelationship,
    requested: dict[str, bool],
    *,
    now: datetime,
) -> list[str]:
    """Writes the categories, returning the keys that changed.

    Keys absent from ``requested`` are left alone, so a client sending one
    toggle does not silently deny the rest. An unknown key is refused by the
    schema before it reaches here; the assertion is the second line of defence.

    The caller commits. Section 53 asks for the server-side effect to be
    immediate after a successful save, and it is: the next request builds a
    fresh ``CareScope`` from these rows.
    """
    existing = {row.permission_key: row for row in relationship.permissions}
    changed: list[str] = []
    for key, allowed in requested.items():
        assert key in CAREGIVER_PERMISSION_KEYS, key
        row = existing.get(key)
        if row is None:
            relationship.permissions.append(
                CaregiverPermission(
                    relationship_id=relationship.id, permission_key=key, allowed=allowed
                )
            )
            if allowed:
                changed.append(key)
            continue
        if row.allowed != allowed:
            row.allowed = allowed
            changed.append(key)
    relationship.updated_at = now
    return sorted(changed)


def _active_relationship(
    db: Session, account_id: uuid.UUID, profile_id: uuid.UUID
) -> CaregiverRelationship | None:
    return db.execute(
        select(CaregiverRelationship)
        .options(selectinload(CaregiverRelationship.permissions))
        .where(
            CaregiverRelationship.profile_id == profile_id,
            CaregiverRelationship.caregiver_account_id == account_id,
            CaregiverRelationship.status.in_(CAREGIVER_ACTIVE_STATUSES),
        )
    ).scalar_one_or_none()


def supported_profiles(db: Session, account_id: uuid.UUID) -> list[CaregiverRelationship]:
    """The people this account currently supports (PRD 9, sections 56 and 57).

    Active only. A revoked relationship disappears from this list the moment it
    is revoked, which is what makes the caregiver's own profile switcher stop
    offering somebody (section 52).
    """
    return list(
        db.execute(
            select(CaregiverRelationship)
            .options(
                selectinload(CaregiverRelationship.permissions),
                selectinload(CaregiverRelationship.profile),
            )
            .where(
                CaregiverRelationship.caregiver_account_id == account_id,
                CaregiverRelationship.status.in_(CAREGIVER_ACTIVE_STATUSES),
            )
            .order_by(CaregiverRelationship.accepted_at.asc())
        )
        .scalars()
        .all()
    )


def resolve_scope(db: Session, account: User, profile_id: uuid.UUID) -> CareScope:
    """How this account may see this profile, or 404.

    Tries the owner path first and the caregiver path second. The order matters
    only for an account that is somehow both; the owner answer is the right one
    because it is strictly wider.

    Nothing about the request body influences this. The account comes from a
    verified token and the profile id from the path, which is what section 75
    means by account and profile ids never being trusted alone -- the id is
    checked against this account's own rows, every time, on every request.
    """
    try:
        profile = resolve_profile(account, profile_id)
    except NotFoundError:
        pass
    else:
        return CareScope(
            profile=profile,
            is_owner=True,
            relationship=None,
            granted=frozenset(CAREGIVER_PERMISSION_KEYS),
        )

    relationship = _active_relationship(db, account.id, profile_id)
    if relationship is None:
        raise CareAccessError("Not found.")
    return CareScope(
        profile=relationship.profile,
        is_owner=False,
        relationship=relationship,
        granted=granted_keys(relationship),
    )


def require_profile_permission(
    db: Session, account: User, profile_id: uuid.UUID, permission_key: str
) -> CareScope:
    """``resolve_scope`` plus one category check (PRD 9, section 61).

    The helper the PRD names. Routes that need exactly one category call this;
    routes that need several resolve the scope once and call ``scope.require``
    per category, which costs one query instead of several.
    """
    scope = resolve_scope(db, account, profile_id)
    scope.require(permission_key)
    return scope


def require_caregiver_scope(
    db: Session, account: User, profile_id: uuid.UUID
) -> CareScope:
    """A scope that must be a caregiver's, not the owner's.

    For the routes that only make sense from the caregiver side -- proposing a
    change, listing the people you support. The owner has their own endpoints
    for all of it, and refusing here keeps "who is the caregiver on this
    suggestion" a question with one answer.
    """
    scope = resolve_scope(db, account, profile_id)
    if scope.is_owner or scope.relationship is None:
        raise CareAccessError("Not found.")
    return scope
