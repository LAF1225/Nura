"""The caregiver list the primary user controls (PRD 9, sections 45, 52, 53, 54).

Reading, relabelling, re-permissioning and removing. Creating one is an
invitation and lives in ``invitations``; what a caregiver may *see* is decided
in ``permissions``, and nothing in this module makes that decision.

Three rules shape it.

**Revocation is immediate and total** (section 52). ``revoke`` flips the status
and that is the whole mechanism: ``permissions.granted_keys`` returns nothing
for a relationship that is not active, so the next request from that caregiver
-- including one already in flight behind a cached token -- is refused. There is
no session to expire and no cache to invalidate, because the check reads the row
every time.

**Revoking keeps the history.** The row stays, with its permissions, its
``accepted_at`` and its ``revoked_at``, and every audit event it generated stays
too. Section 52 asks for exactly that: the caregiver disappears from the active
list, and what happened remains answerable.

**A role is a label.** ``set_role`` writes one column and touches no
permission (section 54). The test for it changes ``family`` to
``primary_caregiver`` and asserts the granted set is identical.
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaregiverRelationship, Profile, User
from app.models.enums import CAREGIVER_NOTIFICATION_KEYS, CAREGIVER_ROLES
from app.services.caregivers import audit, permissions
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: The statuses the primary user's caregiver list shows. A declined or expired
#: invitation is kept for the audit trail but is not a caregiver, and a list
#: that showed four rows for one person nobody ever added would be noise.
LISTED_STATUSES = ("pending", "active")

#: Column name for each notification key, so the mapping lives in one place.
NOTIFICATION_COLUMNS = {
    "messages": "notify_messages",
    "appointment_updates": "notify_appointment_updates",
    "suggestion_outcomes": "notify_suggestion_outcomes",
    "safety_alerts": "notify_safety_alerts",
}
assert set(NOTIFICATION_COLUMNS) == set(CAREGIVER_NOTIFICATION_KEYS)


class RelationshipNotFoundError(NotFoundError):
    """No such caregiver on this profile."""

    code = "caregiver_not_found"


class RelationshipNotActiveError(DomainError):
    """The relationship exists but is pending, declined, expired or revoked."""

    status_code = 409
    code = "caregiver_not_active"


def list_relationships(
    db: Session, profile_id: uuid.UUID, *, include_inactive: bool = False
) -> list[CaregiverRelationship]:
    """The caregivers and open invitations for this profile (section 55).

    Several per profile, always: section 55 forbids hard-coding a single
    caregiver and there is no column anywhere that could hold "the" caregiver.
    """
    query = (
        select(CaregiverRelationship)
        .options(selectinload(CaregiverRelationship.permissions))
        .where(CaregiverRelationship.profile_id == profile_id)
        .order_by(CaregiverRelationship.created_at.asc())
    )
    if not include_inactive:
        query = query.where(CaregiverRelationship.status.in_(LISTED_STATUSES))
    return list(db.execute(query).scalars().all())


def get_relationship(
    db: Session, profile_id: uuid.UUID, relationship_id: uuid.UUID
) -> CaregiverRelationship:
    """One caregiver of this profile's, or 404.

    Scoped by ``profile_id`` so a relationship id belonging to somebody else's
    profile is not found rather than refused -- the same answer the whole
    codebase gives, for the same reason.
    """
    relationship = db.execute(
        select(CaregiverRelationship)
        .options(selectinload(CaregiverRelationship.permissions))
        .where(
            CaregiverRelationship.id == relationship_id,
            CaregiverRelationship.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if relationship is None:
        raise RelationshipNotFoundError("Not found.")
    return relationship


def set_role(
    db: Session,
    relationship: CaregiverRelationship,
    role: str,
    actor: User,
    *,
    now: datetime,
) -> CaregiverRelationship:
    """Relabels the relationship. Grants nothing (section 54)."""
    assert role in CAREGIVER_ROLES, role
    previous = relationship.role
    if previous == role:
        return relationship
    relationship.role = role
    relationship.updated_at = now
    audit.record(
        db,
        profile_id=relationship.profile_id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="role_changed",
        target_type="caregiver_relationship",
        target_id=relationship.id,
        now=now,
        meta=audit.role_change_meta(previous, role),
    )
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.role.updated")
    return relationship


def update_permissions(
    db: Session,
    relationship: CaregiverRelationship,
    requested: dict[str, bool],
    actor: User,
    *,
    now: datetime,
) -> CaregiverRelationship:
    """Writes the permission set and records which keys moved (section 53).

    Allowed on a pending invitation as well as an active relationship: a primary
    user who thinks better of granting symptoms before their son has accepted
    should be able to change it, and the acceptance screen then shows what is
    actually granted.
    """
    changed = permissions.set_permissions(db, relationship, requested, now=now)
    if changed:
        audit.record(
            db,
            profile_id=relationship.profile_id,
            actor_account_id=actor.id,
            actor_kind="primary_user",
            event_type="permission_changed",
            target_type="caregiver_relationship",
            target_id=relationship.id,
            now=now,
            meta=audit.permission_change_meta(changed),
        )
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.permission.updated")
    return relationship


def revoke(
    db: Session,
    relationship: CaregiverRelationship,
    actor: User,
    *,
    now: datetime,
) -> CaregiverRelationship:
    """Ends the relationship now (section 52).

    Works on a pending invitation too, which is how an invitation is withdrawn:
    the token is consumed in the same breath, so a link already sent stops
    working. Revoking twice is accepted and changes nothing -- the primary user
    pressing Remove again should not see an error about a caregiver who is
    already gone.
    """
    if relationship.status == "revoked":
        return relationship
    relationship.status = "revoked"
    relationship.revoked_at = now
    relationship.invite_consumed_at = relationship.invite_consumed_at or now
    audit.record(
        db,
        profile_id=relationship.profile_id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="relationship_revoked",
        target_type="caregiver_relationship",
        target_id=relationship.id,
        now=now,
    )
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.relationship.revoked")
    return relationship


def set_notification_preferences(
    db: Session,
    relationship: CaregiverRelationship,
    requested: dict[str, bool],
    *,
    now: datetime,
) -> CaregiverRelationship:
    """The caregiver's own choices about this person (section 48).

    Set by the caregiver, not by the primary user: these decide what reaches
    *their* phone. Somebody supporting two parents may want everything about one
    and only messages about the other, which is why they live on the
    relationship rather than on the account.

    ``safety_alerts`` can be turned on and is stored faithfully. Nothing will
    ever fire it in PRD 9 -- section 94 says the key may exist before its event
    source does, and section 48 says not to activate safety alerts until PRD 10.
    """
    for key, value in requested.items():
        column = NOTIFICATION_COLUMNS[key]
        if getattr(relationship, column) != value:
            setattr(relationship, column, value)
    relationship.updated_at = now
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.notifications.updated")
    return relationship


def notification_preferences(relationship: CaregiverRelationship) -> dict[str, bool]:
    return {
        key: bool(getattr(relationship, column))
        for key, column in NOTIFICATION_COLUMNS.items()
    }


def require_active(relationship: CaregiverRelationship) -> CaregiverRelationship:
    """Guards the actions that only make sense on a live relationship."""
    if relationship.status != "active":
        raise RelationshipNotActiveError("This caregiver is not active.")
    return relationship


def caregiver_count(db: Session, profile_id: uuid.UUID) -> int:
    """How many active caregivers this profile has. For the Care screen."""
    return len(
        db.execute(
            select(CaregiverRelationship.id).where(
                CaregiverRelationship.profile_id == profile_id,
                CaregiverRelationship.status == "active",
            )
        )
        .scalars()
        .all()
    )


def profile_for_relationship(db: Session, relationship: CaregiverRelationship) -> Profile:
    """The person a relationship is about."""
    return db.get(Profile, relationship.profile_id)  # type: ignore[return-value]
