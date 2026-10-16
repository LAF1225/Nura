"""Inviting somebody to help, and the token that lets them say yes.

PRD 9, sections 11, 12, 13, 14, 15, 74, 75 and 81.

**Nura does not deliver the invitation, and does not pretend to.** Section 12
allows email, SMS or a deep link; this backend has no mail sender, no SMS
gateway and no push infrastructure, so there is nothing here that could send
one. What ``invite`` returns is the token itself, once, to the primary user who
created it -- for them to pass on however they already talk to their daughter.
That is the same handoff PRD 2 uses for a provisioning token, and it is honest:
a function called ``send_invitation_email`` that logged a line and returned
success would be worse than its absence.

The consequence is written down rather than hidden: **the link is the
credential.** It should be shared over a channel the primary user trusts.
What bounds the damage is everything section 13 and 75 ask for --

- the token is 256 bits of randomness,
- it is stored only as a SHA-256, so a database dump holds no usable invitation,
- it expires (``INVITE_TTL``),
- it is single-use: accepted, declined or expired, ``invite_consumed_at`` is set
  and the same link never works again,
- and the relationship it creates can be revoked at any moment (section 52).

**The contact is a note, not a check.** An invitation may name an email or a
phone, and acceptance does *not* require the signed-in account to match it. That
is a deliberate trade: matching would lock out somebody who signed up by phone
after being invited by email, or whose Apple relay address differs from the one
their mother knows -- and the token, not the address, is what authorizes.

**A lookup reveals almost nothing** (section 81). ``preview`` returns the
inviter's name for the person, the role, and the category list -- the three
things section 15 requires be shown before accepting -- and no health
information of any kind. It does not say whether the profile has medications,
symptoms or anything else.
"""

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaregiverPermission, CaregiverRelationship, Profile, User
from app.models.enums import CAREGIVER_PERMISSION_KEYS
from app.services.caregivers import audit, permissions
from app.services.devices import hash_secret
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: Prefix so a token found somewhere is recognisable for what it is, the way
#: ``npt_`` and ``ndt_`` are for robots.
INVITE_TOKEN_PREFIX = "nci_"

#: How long an invitation is good for (section 13). Long enough that somebody
#: can accept after a weekend, short enough that a link forwarded a month ago
#: is dead. Not permanent, which is what section 13 actually forbids.
INVITE_TTL = timedelta(days=7)

#: More caregivers than any household needs, and few enough that an invitation
#: endpoint cannot be used to fill a table.
MAX_CAREGIVERS_PER_PROFILE = 10


class InvitationError(DomainError):
    """A rule about inviting refused the request."""

    code = "invitation_error"


class InvitationNotFoundError(NotFoundError):
    """No invitation for this token, or it is no longer usable.

    One answer for "never existed", "already used" and "expired", so a caller
    cannot probe for tokens that were once real.
    """

    code = "invitation_not_found"


class TooManyCaregiversError(InvitationError):
    status_code = 409
    code = "too_many_caregivers"


class AlreadyCaregiverError(InvitationError):
    status_code = 409
    code = "already_caregiver"


class CannotCareForSelfError(InvitationError):
    """The signed-in account already owns this profile.

    Accepting would give somebody a second, weaker path to their own record and
    make "is this a caregiver?" ambiguous for every later check.
    """

    status_code = 409
    code = "cannot_care_for_self"


@dataclass(frozen=True)
class MintedInvitation:
    """A fresh invitation, with the only copy of its token."""

    relationship: CaregiverRelationship
    #: Returned to the inviter once and never stored. Nothing logs it.
    token: str


@dataclass(frozen=True)
class InvitationPreview:
    """What somebody holding a token is told before they decide (section 81)."""

    relationship_id: uuid.UUID
    #: The name of the person they would be supporting.
    profile_name: str
    #: What the primary user called them when inviting.
    invited_name: str
    role: str
    #: Every category with its answer, so the screen can show both lists
    #: section 15 asks for -- what they will be able to see, and what they
    #: will not.
    permissions: dict[str, bool]
    expires_at: datetime


def _new_token() -> tuple[str, str]:
    token = INVITE_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, hash_secret(token)


def _count_for_profile(db: Session, profile_id: uuid.UUID) -> int:
    """Active and pending together: an invitation holds a place."""
    return len(
        db.execute(
            select(CaregiverRelationship.id).where(
                CaregiverRelationship.profile_id == profile_id,
                CaregiverRelationship.status.in_(("pending", "active")),
            )
        )
        .scalars()
        .all()
    )


def invite(
    db: Session,
    profile: Profile,
    inviter: User,
    *,
    invited_name: str,
    role: str,
    permission_keys: dict[str, bool] | None = None,
    email: str | None = None,
    phone: str | None = None,
    now: datetime,
) -> MintedInvitation:
    """Creates a pending relationship and mints its token (sections 11 and 13).

    Every category gets a row, including the denied ones, so the caregiver's
    acceptance screen can show both lists section 15 requires without guessing
    which keys were simply never mentioned.
    """
    if _count_for_profile(db, profile.id) >= MAX_CAREGIVERS_PER_PROFILE:
        raise TooManyCaregiversError("There are already too many caregivers.")

    requested = permission_keys or {}
    token, token_hash = _new_token()
    relationship = CaregiverRelationship(
        profile_id=profile.id,
        caregiver_account_id=None,
        role=role,
        status="pending",
        invited_by_account_id=inviter.id,
        invited_name=invited_name,
        invite_email=email,
        invite_phone=phone,
        invite_token_hash=token_hash,
        invite_expires_at=now + INVITE_TTL,
    )
    relationship.permissions = [
        CaregiverPermission(permission_key=key, allowed=bool(requested.get(key, False)))
        for key in CAREGIVER_PERMISSION_KEYS
    ]
    db.add(relationship)
    db.flush()
    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=inviter.id,
        actor_kind="primary_user",
        event_type="invited",
        target_type="caregiver_relationship",
        target_id=relationship.id,
        now=now,
        meta=audit.permission_change_meta(
            [key for key, allowed in requested.items() if allowed]
        ),
    )
    db.commit()
    db.refresh(relationship)
    # The token is never logged, here or anywhere.
    logger.info("caregiver.invite.created")
    return MintedInvitation(relationship=relationship, token=token)


def _usable(relationship: CaregiverRelationship, now: datetime) -> bool:
    """Whether this pending row can still be acted on."""
    return (
        relationship.status == "pending"
        and relationship.invite_consumed_at is None
        and relationship.invite_expires_at is not None
        and relationship.invite_expires_at > now
    )


def find_by_token(db: Session, token: str, now: datetime) -> CaregiverRelationship:
    """The pending relationship this token opens, or 404.

    An expired invitation is marked ``expired`` as it is found, so the status a
    caregiver sees and the status the primary user sees are the same -- rather
    than the row quietly reading ``pending`` for ever because nothing ran.
    """
    relationship = db.execute(
        select(CaregiverRelationship)
        .options(
            selectinload(CaregiverRelationship.permissions),
            selectinload(CaregiverRelationship.profile),
        )
        .where(CaregiverRelationship.invite_token_hash == hash_secret(token))
    ).scalar_one_or_none()

    if relationship is None:
        logger.info("caregiver.invite.rejected")
        raise InvitationNotFoundError("Not found.")

    if (
        relationship.status == "pending"
        and relationship.invite_expires_at is not None
        and relationship.invite_expires_at <= now
    ):
        relationship.status = "expired"
        relationship.invite_consumed_at = now
        db.commit()
        db.refresh(relationship)

    if not _usable(relationship, now):
        logger.info("caregiver.invite.rejected")
        raise InvitationNotFoundError("Not found.")
    return relationship


def preview(relationship: CaregiverRelationship) -> InvitationPreview:
    """The acceptance screen's content, and nothing beyond it (section 81)."""
    assert relationship.invite_expires_at is not None
    return InvitationPreview(
        relationship_id=relationship.id,
        profile_name=relationship.profile.preferred_name,
        invited_name=relationship.invited_name,
        role=relationship.role,
        permissions=permissions.permission_map(relationship),
        expires_at=relationship.invite_expires_at,
    )


def _owns_profile(account: User, profile_id: uuid.UUID) -> bool:
    return any(link.profile_id == profile_id for link in account.profile_roles)


def accept(
    db: Session, token: str, account: User, now: datetime
) -> CaregiverRelationship:
    """Turns a pending invitation into an active relationship (section 14).

    Idempotent in the way that matters (section 74): the token is consumed in
    the same transaction that activates the relationship, so a retried request
    finds it spent. A caller who genuinely retried gets
    ``invitation_not_found``; the relationship they created still exists and is
    active, and their supported-profile list shows it -- which is the state they
    were asking for.

    Section 14's other half is honoured by omission: nothing here creates a
    profile for the caregiver. Supporting somebody does not make you a Nura
    user, and an account with no profile of its own works.
    """
    relationship = find_by_token(db, token, now)

    if _owns_profile(account, relationship.profile_id):
        raise CannotCareForSelfError("This is already your own profile.")

    existing = db.execute(
        select(CaregiverRelationship.id).where(
            CaregiverRelationship.profile_id == relationship.profile_id,
            CaregiverRelationship.caregiver_account_id == account.id,
            CaregiverRelationship.status == "active",
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadyCaregiverError("You already support this person.")

    relationship.caregiver_account_id = account.id
    relationship.status = "active"
    relationship.accepted_at = now
    relationship.invite_consumed_at = now
    audit.record(
        db,
        profile_id=relationship.profile_id,
        actor_account_id=account.id,
        actor_kind="caregiver",
        event_type="accepted",
        target_type="caregiver_relationship",
        target_id=relationship.id,
        now=now,
    )
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.invite.accepted")
    return relationship


def decline(
    db: Session, token: str, account: User | None, now: datetime
) -> CaregiverRelationship:
    """Refuses an invitation, consuming the token.

    The account is optional because declining needs no relationship -- somebody
    who was invited by mistake can say no, and nothing about their identity is
    recorded against the profile if they are not signed in.
    """
    relationship = find_by_token(db, token, now)
    relationship.status = "declined"
    relationship.declined_at = now
    relationship.invite_consumed_at = now
    audit.record(
        db,
        profile_id=relationship.profile_id,
        actor_account_id=account.id if account is not None else None,
        actor_kind="caregiver",
        event_type="declined",
        target_type="caregiver_relationship",
        target_id=relationship.id,
        now=now,
    )
    db.commit()
    db.refresh(relationship)
    logger.info("caregiver.invite.declined")
    return relationship
