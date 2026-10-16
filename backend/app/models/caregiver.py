"""Caregivers, family communication and emergency contacts.

PRD 9, sections 5, 7, 22, 31, 43 and 51.

Seven tables, and the shape of the first one is the whole security design:

    caregiver_relationships       one account's standing with one profile
        |                         (the invitation lives here too, section 79)
        +-- caregiver_permissions     one row per category, one answer each
        +-- family_threads            the care conversation for this pairing
        |       |
        |       +-- family_messages
        +-- caregiver_suggestions     changes proposed, awaiting a person

    emergency_contacts            the priority chain PRD 10 will escalate through
    caregiver_audit_events        what was done, not what was read

**A caregiver is not an ``account_profile_roles`` row.** That table is what
``deps.get_owned_profile`` walks, and every profile-scoped route written in PRD
0-8 authorizes through it. Putting caregivers there would have handed every
caregiver the complete health record, every symptom photo and every doctor
report the moment PRD 9 shipped -- no route change, no review, no way to
notice. Caregiver access is a second, narrower path with its own permission
check (``deps.CaregiverScope``) and its own endpoints that return less
(sections 9, 18 and 67).

**A role grants nothing.** ``role`` is a label for a list: section 10 says
roles are descriptive and permissions determine access, and section 54 says
changing a role must not widen anything. No authorization code in this codebase
reads ``role`` -- the test that proves it changes a relationship to
``primary_caregiver`` and checks the permission set is byte-identical.

**The invitation is the relationship.** Section 79 allows it, and it removes a
whole class of bug: there is no second row to keep in step, accepting is a
status change, and "accept twice" is idempotent because the second attempt
finds the token already consumed (section 74). The token is stored only as a
hash (section 13), so the database cannot leak a working invitation.

**Nothing here points at a health record.** No medication id, no condition id,
no symptom id, no report id. A suggestion names its target by
``target_resource_type`` plus ``target_resource_id`` and the service resolves
it inside the profile at approval time, which is what makes section 24's
"verify target still exists" a real check rather than a trusted foreign key.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    CAREGIVER_AUDIT_ACTOR_KINDS,
    CAREGIVER_AUDIT_EVENT_TYPES,
    CAREGIVER_PERMISSION_KEYS,
    CAREGIVER_RELATIONSHIP_STATUSES,
    CAREGIVER_ROLES,
    CAREGIVER_SUGGESTION_ACTION_TYPES,
    CAREGIVER_SUGGESTION_CATEGORIES,
    CAREGIVER_SUGGESTION_STATUSES,
    CAREGIVER_SUGGESTION_TARGET_TYPES,
    FAMILY_CHECK_IN_CODES,
    FAMILY_MESSAGE_TYPES,
    sql_in_list,
)

if TYPE_CHECKING:
    from app.models.profile import Profile

#: Longest name an invitation may carry. It is a label for a list, not a legal
#: name (PRD 9, section 11).
INVITED_NAME_MAX_LENGTH = 80

#: How a caregiver is described in the chain. Free text on purpose: section 44's
#: examples are "Spouse", "Child", "Primary caregiver" and the right answer for
#: somebody's household is not on any list Nura could write.
CONTACT_RELATIONSHIP_MAX_LENGTH = 64

#: A family message. Long enough for a paragraph, short enough that a care
#: thread never becomes a document store (section 32).
FAMILY_MESSAGE_MAX_LENGTH = 2000

#: An optional note on a decline (section 25). Short, and never shared back
#: unless the primary user chooses to.
DECLINE_NOTE_MAX_LENGTH = 300

#: Emergency contact fields (section 43).
CONTACT_NAME_MAX_LENGTH = 120
CONTACT_PHONE_MAX_LENGTH = 32


class CaregiverRelationship(Base, TimestampMixin):
    """One account's standing with one profile, from invitation to revocation.

    ``caregiver_account_id`` is null while an invitation is pending: section 14
    says a caregiver may not have an account yet, and requiring one before the
    invitation could be created would mean the primary user needs to know which
    email their daughter signed up with.
    """

    __tablename__ = "caregiver_relationships"
    __table_args__ = (
        CheckConstraint(
            f"role IN {sql_in_list(CAREGIVER_ROLES)}",
            name="ck_caregiver_relationships_role",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(CAREGIVER_RELATIONSHIP_STATUSES)}",
            name="ck_caregiver_relationships_status",
        ),
        # An active relationship has an account behind it; a pending one need
        # not. Stated as a constraint because the alternative is trusting every
        # future writer to remember.
        CheckConstraint(
            "status <> 'active' OR caregiver_account_id IS NOT NULL",
            name="ck_caregiver_relationships_active_has_account",
        ),
        # One active relationship per (profile, account). Partial, so revoking
        # and re-inviting the same person works -- the old row keeps its history
        # (section 52) and the new one is the only active pairing.
        Index(
            "uq_caregiver_relationships_active",
            "profile_id",
            "caregiver_account_id",
            unique=True,
            postgresql_where="status = 'active' AND caregiver_account_id IS NOT NULL",
        ),
        Index("ix_caregiver_relationships_profile_status", "profile_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Null until the invitation is accepted.
    caregiver_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    #: Descriptive only. Nothing in the authorization path reads this.
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    #: Who sent the invitation. ``SET NULL`` rather than cascade: a caregiver
    #: relationship outlives the account that arranged it.
    invited_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    # --- the invitation (sections 11, 12 and 13) ---
    #: What the primary user called this person when inviting them.
    invited_name: Mapped[str] = mapped_column(
        String(INVITED_NAME_MAX_LENGTH), nullable=False
    )
    #: Who the invitation was addressed to, for the inviter's own reference.
    #: Nura does not send it -- there is no mail or SMS infrastructure in this
    #: system -- so this is a note, not a delivery address. See
    #: ``services.caregivers.invitations``.
    invite_email: Mapped[str | None] = mapped_column(String(320))
    invite_phone: Mapped[str | None] = mapped_column(String(32))
    #: SHA-256 of the token. The token itself is returned once, at creation, and
    #: never stored (section 13) -- so a database dump contains no usable
    #: invitation and neither does a log line.
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set the moment the token is spent, accepted or declined. This is what
    #: makes it single-use (sections 13 and 75).
    invite_consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- what this caregiver wants to hear about (section 48) ---
    # Set by the caregiver, for this person only: somebody supporting two
    # parents may want messages about one and everything about the other.
    # ``safety_alerts`` defaults off and stays off -- section 48 says not to
    # activate safety alerts until PRD 10 exists, and section 94 says not to
    # fabricate the events that would feed them.
    notify_messages: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    notify_appointment_updates: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    notify_suggestion_outcomes: Mapped[bool] = mapped_column(
        nullable=False, server_default="true"
    )
    notify_safety_alerts: Mapped[bool] = mapped_column(
        nullable=False, server_default="false"
    )

    profile: Mapped["Profile"] = relationship()
    permissions: Mapped[list["CaregiverPermission"]] = relationship(
        back_populates="relationship_row",
        cascade="all, delete-orphan",
        order_by="CaregiverPermission.permission_key",
    )


class CaregiverPermission(Base, TimestampMixin):
    """One category, one answer, for one relationship (PRD 9, section 7).

    A row per key rather than a column per key, and certainly not one boolean
    for the lot (section 7). The cost is a join; what it buys is that adding a
    category in PRD 10 is a tuple entry rather than a migration, and that a
    permission set is a thing the audit trail can describe row by row.

    A missing row means *not allowed*. The service writes every key explicitly
    at invitation time anyway, so the two never differ in practice -- but the
    default has to be deny, because the one thing worse than a missing
    permission row is a missing permission row that grants something.
    """

    __tablename__ = "caregiver_permissions"
    __table_args__ = (
        UniqueConstraint(
            "relationship_id", "permission_key", name="uq_caregiver_permission_key"
        ),
        CheckConstraint(
            f"permission_key IN {sql_in_list(CAREGIVER_PERMISSION_KEYS)}",
            name="ck_caregiver_permissions_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caregiver_relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_key: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed: Mapped[bool] = mapped_column(nullable=False, server_default="false")

    relationship_row: Mapped[CaregiverRelationship] = relationship(
        back_populates="permissions"
    )


class CaregiverSuggestion(Base, TimestampMixin):
    """A change a caregiver proposed, waiting for the person it affects.

    PRD 9, sections 21, 22, 23 and 24.

    ``payload`` is JSONB, which is the risky part, so two things bound it. The
    ``action_type`` CHECK constraint comes from
    ``CAREGIVER_SUGGESTION_ACTION_TYPES``, so a row can only ever claim to be
    one of the five changes PRD 9 allows -- ``change_medication_dose`` cannot be
    stored at all. And every payload is parsed through that action's pydantic
    model before it is written and *again* before it is applied (section 23), so
    what approval reads has been validated twice, with the second pass after any
    amount of time has passed.

    ``applied_resource_id`` is what makes approval idempotent (section 74): a
    second Approve on a row that is already approved returns the same result
    rather than creating a second appointment.
    """

    __tablename__ = "caregiver_suggestions"
    __table_args__ = (
        CheckConstraint(
            f"category IN {sql_in_list(CAREGIVER_SUGGESTION_CATEGORIES)}",
            name="ck_caregiver_suggestions_category",
        ),
        CheckConstraint(
            f"action_type IN {sql_in_list(CAREGIVER_SUGGESTION_ACTION_TYPES)}",
            name="ck_caregiver_suggestions_action_type",
        ),
        CheckConstraint(
            f"status IN {sql_in_list(CAREGIVER_SUGGESTION_STATUSES)}",
            name="ck_caregiver_suggestions_status",
        ),
        CheckConstraint(
            "target_resource_type IS NULL OR target_resource_type IN "
            f"{sql_in_list(CAREGIVER_SUGGESTION_TARGET_TYPES)}",
            name="ck_caregiver_suggestions_target_type",
        ),
        UniqueConstraint(
            "relationship_id",
            "client_suggestion_id",
            name="uq_caregiver_suggestion_client_id",
        ),
        Index("ix_caregiver_suggestions_profile_status", "profile_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: Carried on the row as well as reachable through the relationship, the
    #: same way a symptom entry carries its profile: every query here is
    #: "what is waiting for this person", and that should not need a join.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Which relationship it was made under. Approval re-reads this row to check
    #: the caregiver is still active and still permitted (section 24) -- a
    #: suggestion made last week by somebody revoked yesterday cannot be
    #: approved.
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caregiver_relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_resource_type: Mapped[str | None] = mapped_column(String(32))
    #: Null on an action that proposes something new, such as an appointment
    #: that does not exist yet.
    target_resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    #: Set by the caregiver's client so a retried POST does not create a second
    #: care request (section 74).
    client_suggestion_id: Mapped[str | None] = mapped_column(String(64))

    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Optional, private, and never returned to the caregiver (section 25).
    decline_note: Mapped[str | None] = mapped_column(String(DECLINE_NOTE_MAX_LENGTH))
    #: What approval actually produced or changed, so approving twice is the
    #: same as approving once.
    applied_resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    relationship_row: Mapped[CaregiverRelationship] = relationship()


class FamilyThread(Base, TimestampMixin):
    """The care conversation between one profile and one caregiver.

    One thread per relationship, which is a decision rather than a shortcut.
    Section 66 rules out unnecessary caregiver-to-caregiver exposure and section
    32 rules out chat rooms and communities: a thread that belongs to a pairing
    gives both for free, with no participant table and no way for caregiver A to
    read what caregiver B wrote.
    """

    __tablename__ = "family_threads"
    __table_args__ = (
        UniqueConstraint("relationship_id", name="uq_family_thread_relationship"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("caregiver_relationships.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Doubles as the next message's position, the way a conversation's does.
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    relationship_row: Mapped[CaregiverRelationship] = relationship()
    messages: Mapped[list["FamilyMessage"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="FamilyMessage.position",
    )


class FamilyMessage(Base):
    """One line in a care conversation (PRD 9, section 31).

    No ``updated_at``, and no ``TimestampMixin``: a sent message is not edited,
    for the same reason an assistant message is not. ``read_at`` is the only
    thing that changes after it is written, and section 37 is careful about what
    that means -- it records that somebody opened the thread, and nothing here
    claims real-time delivery.

    ``sender_side`` is stored rather than derived from ``sender_account_id``
    because the account may be gone: a deleted account must not turn half a
    conversation into messages from nobody, aligned to the wrong side of the
    screen.
    """

    __tablename__ = "family_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "position", name="uq_family_message_position"),
        UniqueConstraint(
            "thread_id", "client_message_id", name="uq_family_message_client_id"
        ),
        CheckConstraint(
            f"message_type IN {sql_in_list(FAMILY_MESSAGE_TYPES)}",
            name="ck_family_messages_type",
        ),
        CheckConstraint(
            "check_in_code IS NULL OR check_in_code IN "
            f"{sql_in_list(FAMILY_CHECK_IN_CODES)}",
            name="ck_family_messages_check_in_code",
        ),
        CheckConstraint(
            "sender_side IN ('primary_user', 'caregiver', 'system')",
            name="ck_family_messages_sender_side",
        ),
        # Each type carries its own content and only its own. A `check_in` with
        # free text, or a `text` with none, would be a message the renderer has
        # to guess at.
        CheckConstraint(
            "(message_type = 'text' AND text IS NOT NULL AND check_in_code IS NULL) "
            "OR (message_type = 'check_in' AND check_in_code IS NOT NULL "
            "AND text IS NULL) "
            "OR (message_type = 'photo' AND attachment_key IS NOT NULL) "
            "OR (message_type = 'system' AND text IS NOT NULL)",
            name="ck_family_messages_content",
        ),
        CheckConstraint("position >= 0", name="ck_family_messages_position"),
        Index("ix_family_messages_thread_position", "thread_id", "position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("family_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    #: ``SET NULL``: the message stays in the thread when an account goes.
    sender_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    #: Which side of the care relationship sent it. Survives the account.
    sender_side: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: What they typed. Null on a check-in, which carries a code instead.
    text: Mapped[str | None] = mapped_column(Text)
    #: One of ``FAMILY_CHECK_IN_CODES``. The sentence is rendered from this, so
    #: the wording lives in one module and a row never freezes a translation.
    check_in_code: Mapped[str | None] = mapped_column(String(32))
    #: Reserved for section 33's optional photo messages. Nothing writes it:
    #: ``FAMILY_MESSAGE_TYPES_ALLOWED`` excludes ``photo``.
    attachment_key: Mapped[str | None] = mapped_column(String(200))
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: When the *other* side opened the thread. Section 37: sent and read, and
    #: no stronger promise than that.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    thread: Mapped[FamilyThread] = relationship(back_populates="messages")


class EmergencyContact(Base, TimestampMixin):
    """Somebody to reach, and how soon to reach them (PRD 9, sections 43-47).

    PRD 9 **manages** this chain and never walks it. Nothing in this codebase
    reads ``priority`` to decide who to contact, because nothing contacts
    anybody: section 47 puts escalation in PRD 10, and a half-built escalation
    that fires once is worse than none at all.

    ``priority`` is 1-based and contiguous, renumbered by the server on every
    change, which is why it carries no unique constraint -- the same approach
    appointment questions take to their order, and for the same reason: a
    reorder that has to be transactionally unique at every intermediate step is
    a reorder that fails for no good reason.

    There is no ``is_verified``. Section 46 recommends verification *if the
    infrastructure exists* and says not to block the prototype on it; there is
    no way to send a code to a phone anywhere in this system, so a column that
    could only ever read "unverified" would be a worse answer than its absence.
    """

    __tablename__ = "emergency_contacts"
    __table_args__ = (
        CheckConstraint("priority >= 1", name="ck_emergency_contacts_priority"),
        Index("ix_emergency_contacts_profile_priority", "profile_id", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Set when this contact also uses Nura. Null is normal and expected
    #: (section 43): a neighbour with a phone is a perfectly good first contact.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(String(CONTACT_NAME_MAX_LENGTH), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(CONTACT_PHONE_MAX_LENGTH))
    relationship_label: Mapped[str | None] = mapped_column(
        String(CONTACT_RELATIONSHIP_MAX_LENGTH)
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")


class CaregiverAuditEvent(Base):
    """What somebody did, kept so it can be answered for (PRD 9, sections 50, 51).

    No ``updated_at`` and no delete path: an audit row that can be edited is not
    an audit row. Revoking a caregiver removes their access and leaves every
    event they generated in place (section 52).

    **Nothing medical goes in ``meta``.** Section 51 asks for minimal metadata
    and section 69 forbids logging health or message contents, so what lands
    here is the shape of what happened -- which permission key changed, which
    action type was approved -- and never a medication name, a message, or a
    decline note. ``services.caregivers.audit`` is the only writer and it builds
    every payload from a fixed set of keys.
    """

    __tablename__ = "caregiver_audit_events"
    __table_args__ = (
        CheckConstraint(
            f"event_type IN {sql_in_list(CAREGIVER_AUDIT_EVENT_TYPES)}",
            name="ck_caregiver_audit_events_type",
        ),
        CheckConstraint(
            f"actor_kind IN {sql_in_list(CAREGIVER_AUDIT_ACTOR_KINDS)}",
            name="ck_caregiver_audit_events_actor_kind",
        ),
        Index("ix_caregiver_audit_events_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: ``SET NULL`` so the event survives the account that caused it.
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
