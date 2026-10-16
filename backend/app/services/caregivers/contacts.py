"""The emergency-contact chain: managed here, walked nowhere.

PRD 9, sections 43, 44, 45, 46, 47 and 93.

**Nothing in this codebase contacts anybody.** Section 47 is explicit: PRD 9
builds the records, the order and the permissions, and escalation belongs to PRD
10. So no function here sends, rings, notifies or escalates, and nothing reads
``priority`` to decide who to reach -- it is read only to put a list in order on
a screen. A half-built escalation that fires once is worse than none.

What PRD 10 will find waiting (section 93): contacts with a contiguous priority,
an ``is_active`` flag it can skip over, an optional ``account_id`` for the
contacts who also use Nura, and the ``safety_alerts`` permission key already in
the vocabulary.

**Only the primary user may touch the chain** (section 45). Every function here
takes the owner's profile, and there is no caregiver route that reaches them --
not even a read. Section 45 says caregivers must not silently reorder the chain;
the way to be certain is that no caregiver-scoped endpoint mentions emergency
contacts at all.

**Priority is contiguous and the server owns it.** 1..n, renumbered on every
change, which is why the column has no unique constraint -- the same decision
appointment questions make about their order, and for the same reason: a reorder
that must be unique at every intermediate step fails for no good reason.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmergencyContact, Profile, User
from app.services.caregivers import audit
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: More than any chain needs. Section 44's example has four.
MAX_CONTACTS = 10


class ContactNotFoundError(NotFoundError):
    code = "emergency_contact_not_found"


class TooManyContactsError(DomainError):
    status_code = 409
    code = "too_many_emergency_contacts"


@dataclass(frozen=True)
class ContactInput:
    """What a client may say about a contact.

    A dataclass rather than a dict, so the fields the API accepts are written
    down once and a server-owned field cannot arrive by accident. ``priority`` is
    not here: the server decides it.
    """

    name: str
    phone: str | None = None
    relationship_label: str | None = None
    is_active: bool = True


def list_contacts(
    db: Session, profile_id: uuid.UUID, *, active_only: bool = False
) -> list[EmergencyContact]:
    """The chain in priority order.

    Inactive contacts are included by default, because the management screen
    needs to show them: section 45 asks for activate/deactivate rather than
    delete-to-disable, and a deactivated contact nobody can see again is a
    deleted one with extra steps.
    """
    query = (
        select(EmergencyContact)
        .where(EmergencyContact.profile_id == profile_id)
        .order_by(EmergencyContact.priority.asc(), EmergencyContact.created_at.asc())
    )
    if active_only:
        query = query.where(EmergencyContact.is_active.is_(True))
    return list(db.execute(query).scalars().all())


def get_contact(
    db: Session, profile_id: uuid.UUID, contact_id: uuid.UUID
) -> EmergencyContact:
    contact = db.execute(
        select(EmergencyContact).where(
            EmergencyContact.id == contact_id,
            EmergencyContact.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if contact is None:
        raise ContactNotFoundError("Not found.")
    return contact


def _renumber(db: Session, profile_id: uuid.UUID) -> None:
    """Rewrites priorities as 1..n in current order. The caller commits."""
    for index, contact in enumerate(list_contacts(db, profile_id), start=1):
        if contact.priority != index:
            contact.priority = index


def create_contact(
    db: Session,
    profile: Profile,
    data: ContactInput,
    actor: User,
    *,
    now: datetime,
) -> EmergencyContact:
    """Adds a contact at the end of the chain.

    At the end rather than anywhere clever: somebody adding their neighbour
    fourth meant fourth, and a service that reorders on their behalf is a
    service that has an opinion about who matters most.

    ``account_id`` is deliberately not settable from a request. Linking a
    contact to a Nura account would mean accepting an account id from a client,
    which section 75 rules out, and the only trustworthy way to establish the
    link is the caregiver invitation flow -- which already exists.
    """
    existing = list_contacts(db, profile.id)
    if len(existing) >= MAX_CONTACTS:
        raise TooManyContactsError("There are already enough emergency contacts.")

    contact = EmergencyContact(
        profile_id=profile.id,
        account_id=None,
        name=data.name,
        phone=data.phone,
        relationship_label=data.relationship_label,
        priority=len(existing) + 1,
        is_active=data.is_active,
    )
    db.add(contact)
    db.flush()
    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="emergency_contact_added",
        target_type="emergency_contact",
        target_id=contact.id,
        now=now,
    )
    db.commit()
    db.refresh(contact)
    logger.info("emergency_contact.added")
    return contact


def update_contact(
    db: Session,
    contact: EmergencyContact,
    fields: dict[str, object],
    actor: User,
    *,
    now: datetime,
) -> EmergencyContact:
    """Applies a PATCH. Only the fields a client owns, and only those sent."""
    for key in ("name", "phone", "relationship_label", "is_active"):
        if key in fields:
            setattr(contact, key, fields[key])
    contact.updated_at = now
    audit.record(
        db,
        profile_id=contact.profile_id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="emergency_contact_updated",
        target_type="emergency_contact",
        target_id=contact.id,
        now=now,
    )
    db.commit()
    db.refresh(contact)
    logger.info("emergency_contact.updated")
    return contact


def delete_contact(
    db: Session, contact: EmergencyContact, actor: User, *, now: datetime
) -> None:
    """Removes a contact and closes the gap it left."""
    profile_id = contact.profile_id
    contact_id = contact.id
    db.delete(contact)
    db.flush()
    _renumber(db, profile_id)
    audit.record(
        db,
        profile_id=profile_id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="emergency_contact_removed",
        target_type="emergency_contact",
        target_id=contact_id,
        now=now,
    )
    db.commit()
    logger.info("emergency_contact.removed")


def reorder(
    db: Session,
    profile: Profile,
    order: list[uuid.UUID],
    actor: User,
    *,
    now: datetime,
) -> list[EmergencyContact]:
    """Puts the chain in the order given (sections 44, 45 and 89).

    The client sends the list it is displaying and priority is taken from that
    order, rather than from numbers the client has to keep consistent -- the same
    decision the Today layout and appointment questions make.

    Ids that are not this profile's are ignored and anything left out keeps its
    relative order at the end. This is the one place in PRD 9 where that
    leniency is worth stating: an escalation chain that refused to save because
    one contact was deleted on another device would leave the old order in place,
    which is the opposite of what somebody reordering it wanted.
    """
    contacts = list_contacts(db, profile.id)
    by_id = {contact.id: contact for contact in contacts}
    ordered = [by_id[contact_id] for contact_id in order if contact_id in by_id]
    ordered += [contact for contact in contacts if contact not in ordered]

    for index, contact in enumerate(ordered, start=1):
        contact.priority = index
    audit.record(
        db,
        profile_id=profile.id,
        actor_account_id=actor.id,
        actor_kind="primary_user",
        event_type="emergency_contact_priority_changed",
        target_type="emergency_contact_chain",
        now=now,
        meta=audit.priority_change_meta(len(ordered)),
    )
    db.commit()
    logger.info("emergency_contact.reordered")
    return list_contacts(db, profile.id)
