"""Family messages and quick check-ins (PRD 9, sections 30-37, 65, 68, 74).

A care conversation, and deliberately nothing more. Section 32 rules out chat
rooms, social feeds, reaction systems and communities, so what is here is: two
people, a list of lines, and whether the other one has read them.

**A thread belongs to a pairing, not to a profile.** One thread per caregiver
relationship. That is what makes section 66's "no unnecessary
caregiver-to-caregiver exposure" structural -- there is no query in this module
that could return caregiver B's messages to caregiver A, because a thread id
resolves through one relationship and the relationship resolves through one
account.

**Communication is a permission like any other.** A caregiver without
``communication`` cannot read or send, and revoking the relationship stops both
immediately -- the thread and its messages stay, because deleting somebody's
conversation because their access ended would be destroying the record of a
conversation that really happened.

**Nothing reads these messages but the people in them.** Section 65 forbids
summarising or analysing family messages with AI, and no assistant tool touches
this table -- there is no tool that names a thread, a message or a check-in.
Section 68 keeps them out of logs: every log line below is an event name.

**"Sent" and "read" mean exactly what they say** (section 37). ``created_at`` is
when the server stored it. ``read_at`` is when the other side opened the thread.
Neither claims delivery, there is no push for these yet, and nothing here
pretends a message arrived on a phone.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import CaregiverRelationship, FamilyMessage, FamilyThread
from app.models.caregiver import FAMILY_MESSAGE_MAX_LENGTH
from app.models.enums import (
    FAMILY_CHECK_IN_CODES_FROM_CAREGIVER,
    FAMILY_CHECK_IN_CODES_FROM_USER,
    FAMILY_MESSAGE_TYPES_ALLOWED,
)
from app.services.caregivers import permissions as permission_service
from app.services.caregivers.permissions import CareScope
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: How many messages one page returns. A care thread is not a chat history to
#: scroll for an hour.
PAGE_SIZE = 50

#: Messages one thread may hold. Beyond this the oldest stay in the database and
#: stop being returned, rather than being deleted: nothing in Nura deletes
#: somebody's words on its own.
MAX_MESSAGES_RETURNED = 500


class MessagingError(DomainError):
    code = "messaging_error"


class ThreadNotFoundError(NotFoundError):
    code = "thread_not_found"


class InvalidMessageError(MessagingError):
    status_code = 422
    code = "invalid_message"


@dataclass(frozen=True)
class ThreadSummary:
    """One row in the message list."""

    thread: FamilyThread
    relationship: CaregiverRelationship
    #: The last line, for the preview. Null on an empty thread.
    last_message: FamilyMessage | None
    #: How many of the *other* side's messages this reader has not read.
    unread: int


def _side_for(scope: CareScope) -> str:
    return "primary_user" if scope.is_owner else "caregiver"


def pairing_allows_messages(relationship: CaregiverRelationship) -> bool:
    """Whether *this pairing* may exchange messages.

    Not the same question as whether the caller may. An owner's scope holds every
    category, so checking only the caller would let the primary user open a
    thread with somebody who was never granted ``communication`` and send into
    it -- messages the other side cannot read, and a "sent" state that means
    nothing (section 37).

    Checked here rather than at the three call sites, so a new reader of a thread
    cannot forget it.
    """
    return "communication" in permission_service.granted_keys(relationship)


def _other_side(side: str) -> str:
    return "caregiver" if side == "primary_user" else "primary_user"


def get_or_create_thread(
    db: Session, relationship: CaregiverRelationship, *, now: datetime
) -> FamilyThread:
    """The thread for this pairing, making it on first use.

    Created lazily rather than at acceptance, so a caregiver who never sends a
    message leaves no empty conversation behind -- and so granting
    ``communication`` later does not need to go back and create one.
    """
    thread = db.execute(
        select(FamilyThread).where(FamilyThread.relationship_id == relationship.id)
    ).scalar_one_or_none()
    if thread is not None:
        return thread
    thread = FamilyThread(
        profile_id=relationship.profile_id,
        relationship_id=relationship.id,
        message_count=0,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    logger.info("family.thread.created")
    return thread


def get_thread(db: Session, scope: CareScope, thread_id: uuid.UUID) -> FamilyThread:
    """A thread this scope may read, or 404.

    The owner reaches every thread on their own profile. A caregiver reaches
    exactly one: the query is narrowed to their relationship id, so another
    caregiver's thread id is not found rather than refused.
    """
    query = (
        select(FamilyThread)
        .options(selectinload(FamilyThread.relationship_row))
        .where(
            FamilyThread.id == thread_id,
            FamilyThread.profile_id == scope.profile.id,
        )
    )
    if not scope.is_owner:
        assert scope.relationship is not None
        query = query.where(FamilyThread.relationship_id == scope.relationship.id)
    thread = db.execute(query).scalar_one_or_none()
    if thread is None:
        raise ThreadNotFoundError("Not found.")
    if not pairing_allows_messages(thread.relationship_row):
        # 404 rather than a refusal, for the reason everything else here is:
        # a caregiver whose communication access was withdrawn should not be
        # able to tell a thread exists from the answer they get.
        raise ThreadNotFoundError("Not found.")
    return thread


def _unread_for(db: Session, thread_id: uuid.UUID, reader_side: str) -> int:
    return len(
        db.execute(
            select(FamilyMessage.id).where(
                FamilyMessage.thread_id == thread_id,
                FamilyMessage.sender_side == _other_side(reader_side),
                FamilyMessage.read_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def _last_message(db: Session, thread_id: uuid.UUID) -> FamilyMessage | None:
    return db.execute(
        select(FamilyMessage)
        .where(FamilyMessage.thread_id == thread_id)
        .order_by(FamilyMessage.position.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_threads(db: Session, scope: CareScope) -> list[ThreadSummary]:
    """The conversations this scope can see, most recent first.

    An owner with three caregivers sees three threads. A caregiver sees one --
    theirs. A relationship that is no longer active contributes nothing, because
    the thread is only listed through a relationship the query still accepts.
    """
    query = (
        select(FamilyThread)
        .options(selectinload(FamilyThread.relationship_row))
        .join(
            CaregiverRelationship,
            CaregiverRelationship.id == FamilyThread.relationship_id,
        )
        .where(
            FamilyThread.profile_id == scope.profile.id,
            CaregiverRelationship.status == "active",
        )
        .order_by(FamilyThread.last_message_at.desc().nullslast())
    )
    if not scope.is_owner:
        assert scope.relationship is not None
        query = query.where(FamilyThread.relationship_id == scope.relationship.id)

    side = _side_for(scope)
    return [
        ThreadSummary(
            thread=thread,
            relationship=thread.relationship_row,
            last_message=_last_message(db, thread.id),
            unread=_unread_for(db, thread.id, side),
        )
        for thread in db.execute(query).scalars().all()
        if pairing_allows_messages(thread.relationship_row)
    ]


def list_messages(
    db: Session, thread: FamilyThread, *, limit: int = PAGE_SIZE
) -> list[FamilyMessage]:
    """The newest page of a thread, returned oldest-first for rendering."""
    newest = list(
        db.execute(
            select(FamilyMessage)
            .where(FamilyMessage.thread_id == thread.id)
            .order_by(FamilyMessage.position.desc())
            .limit(min(limit, MAX_MESSAGES_RETURNED))
        )
        .scalars()
        .all()
    )
    return list(reversed(newest))


def find_by_client_id(
    db: Session, thread_id: uuid.UUID, client_id: str | None
) -> FamilyMessage | None:
    """A message this client already sent, if any.

    What makes a retry idempotent (section 74): the app keeps its
    ``client_message_id`` across attempts, so a send that timed out after the
    server stored it does not become two messages.
    """
    if not client_id:
        return None
    return db.execute(
        select(FamilyMessage).where(
            FamilyMessage.thread_id == thread_id,
            FamilyMessage.client_message_id == client_id,
        )
    ).scalar_one_or_none()


def _check_in_codes_for(side: str) -> tuple[str, ...]:
    """Which check-ins this side may send (sections 35 and 36).

    Two different lists, because they are two different gestures: the person
    says how they are, the caregiver asks. "I'm okay" from a caregiver would be
    an answer to a question nobody asked.
    """
    return (
        FAMILY_CHECK_IN_CODES_FROM_USER
        if side == "primary_user"
        else FAMILY_CHECK_IN_CODES_FROM_CAREGIVER
    )


def send_message(
    db: Session,
    scope: CareScope,
    thread: FamilyThread,
    *,
    sender_account_id: uuid.UUID,
    message_type: str,
    text: str | None = None,
    check_in_code: str | None = None,
    client_message_id: str | None = None,
    now: datetime,
) -> FamilyMessage:
    """Adds one line to a thread.

    ``position`` comes from the thread's own counter rather than from a
    timestamp, so two messages sent in the same moment still have an
    unambiguous order -- the same decision an assistant conversation makes.

    A ``photo`` is refused here as well as absent from the schema's Literal:
    section 33 makes attachments optional, and the upload route they would need
    does not exist (see ``FAMILY_MESSAGE_TYPES_ALLOWED``).
    """
    if message_type not in FAMILY_MESSAGE_TYPES_ALLOWED:
        raise InvalidMessageError("Nura cannot send that kind of message yet.")

    existing = find_by_client_id(db, thread.id, client_message_id)
    if existing is not None:
        return existing

    side = _side_for(scope)
    if message_type == "text":
        cleaned = (text or "").strip()
        if not cleaned:
            raise InvalidMessageError("A message needs something in it.")
        if len(cleaned) > FAMILY_MESSAGE_MAX_LENGTH:
            raise InvalidMessageError("That message is too long.")
        check_in_code = None
    else:
        if check_in_code not in _check_in_codes_for(side):
            raise InvalidMessageError("That is not a check-in you can send.")
        cleaned = None

    message = FamilyMessage(
        thread_id=thread.id,
        position=thread.message_count,
        # The account that signed in, passed by the route rather than inferred:
        # an owner's scope holds no relationship to read it from, and guessing
        # would record the owner's own messages as sent by nobody.
        sender_account_id=sender_account_id,
        sender_side=side,
        message_type=message_type,
        text=cleaned,
        check_in_code=check_in_code,
        client_message_id=client_message_id,
        created_at=now,
    )
    db.add(message)
    thread.message_count += 1
    thread.last_message_at = now
    db.commit()
    db.refresh(message)
    # The event, never the words (sections 68 and 69).
    logger.info("family.message.sent")
    return message


def mark_read(
    db: Session, scope: CareScope, thread: FamilyThread, *, now: datetime
) -> int:
    """Marks the other side's unread messages as read, returning how many.

    Only the other side's: a reader opening their own thread does not mark their
    own messages read, which would make the sender's "read" indicator mean
    nothing.
    """
    side = _side_for(scope)
    unread = list(
        db.execute(
            select(FamilyMessage).where(
                FamilyMessage.thread_id == thread.id,
                FamilyMessage.sender_side == _other_side(side),
                FamilyMessage.read_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for message in unread:
        message.read_at = now
    if unread:
        db.commit()
    return len(unread)


def unread_count(db: Session, scope: CareScope) -> int:
    """Across every thread this scope can see. For the caregiver home."""
    return sum(summary.unread for summary in list_threads(db, scope))
