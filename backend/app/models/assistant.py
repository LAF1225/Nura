"""The Nura assistant: conversations, memory and how it is asked to behave.

PRD 8, sections 7, 44, 48, 87 and 88.

Five tables, and the line between two of them is the whole design:

    conversations                 a thread, with a title and an end
        |
        +-- conversation_messages     what was actually said, in order

    assistant_preferences         how Nura should sound, one row per person
    assistant_memories            the few durable things it was asked to keep
    assistant_prompt_dismissals   proactive prompts already waved away

**Conversation history and memory are different things** (PRD 8, section 48).
History is what was said; memory is the short list of durable preferences the
user agreed Nura should keep. Deleting a conversation leaves memory alone, and
removing a memory leaves the conversation that produced it alone. They are
separate tables so that separation is structural rather than a rule somebody
has to remember.

**Memory is a preference, never a medical record** (sections 40 and 45). There
is no category here for a condition or a medication, and nothing copies a
health record into ``content``. When Nura needs to know what somebody takes it
asks the medication service, through a tool, at the moment it needs it -- and
what comes back is not written down here afterwards.

**Nothing here stores hidden reasoning** (section 80). ``meta`` on a message
holds the model name, the latency, which tools ran and which safety mode
applied. It does not hold a chain of thought, a system prompt, or anything
else the user would be surprised to find in their own conversation.

**Instructions are data in this schema, not instructions.** ``custom_instructions``
and ``assistant_memories.content`` are things a user typed. They are rendered
into the prompt inside a clearly fenced, explicitly untrusted section, and the
safety policy is assembled after them, so nothing stored in these columns can
move the boundary it sits inside (sections 25, 26 and 50).
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import (
    ASSISTANT_MEMORY_CATEGORIES,
    ASSISTANT_MEMORY_SOURCES,
    ASSISTANT_MODES,
    ASSISTANT_PROMPT_KINDS,
    ASSISTANT_VOICES,
    CONVERSATION_MESSAGE_ROLES,
    CONVERSATION_MESSAGE_SOURCES,
    CONVERSATION_MESSAGE_TYPES,
    PERSONALITY_LEVELS,
    PERSONALITY_PRESETS,
    PROACTIVITY_LEVELS,
    SAFETY_MODES,
    SPEAKING_SPEEDS,
    VERBOSITY_LEVELS,
    sql_in_list,
)
from app.models.symptom import CLIENT_ID_MAX_LENGTH

if TYPE_CHECKING:
    from app.models.profile import Profile

#: "Appointment questions". Short enough to read in a history list, long
#: enough that a title is rarely a truncation.
CONVERSATION_TITLE_MAX_LENGTH = 120

#: The longest single message a user may send (PRD 8, section 77). Generous
#: for somebody describing how their week went, and far short of anything that
#: would blow a context window on its own.
MESSAGE_MAX_LENGTH = 4000

#: What one remembered thing may say (PRD 8, section 42). A memory is a
#: sentence -- "Morning responses should be concise" -- and a limit that only
#: fits a sentence is part of keeping it one.
MEMORY_MAX_LENGTH = 300

#: How much standing instruction a user may give (PRD 8, section 26). Long
#: enough for the handful of real preferences the PRD illustrates, short
#: enough that it cannot become a second system prompt.
CUSTOM_INSTRUCTIONS_MAX_LENGTH = 2000

#: How long a stored thread summary may be (PRD 8, section 79). A summary that
#: grows without bound defeats the point of having one.
CONVERSATION_SUMMARY_MAX_LENGTH = 2000

#: Which appointment, which day, which medication a dismissed prompt was
#: about. Opaque to this table.
PROMPT_SUBJECT_MAX_LENGTH = 64


class Conversation(Base, TimestampMixin):
    """One thread between a person and Nura (PRD 8, sections 7 and 8).

    Threads rather than a single endless log, because section 8 asks for
    exactly that: a conversation about last week's headaches and one about
    which questions to take to a cardiologist are different conversations, and
    being able to delete one without the other is most of why.

    ``summary`` is the compact running description of a long thread (section
    79) and is **not** user-facing memory: it exists so a long conversation can
    be continued without resending every turn, and it is deleted with the
    conversation. ``summary_through_position`` records how far it covers, so
    the messages after that point are the ones still sent verbatim.
    """

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(CONVERSATION_TITLE_MAX_LENGTH), nullable=False
    )
    #: Set when the user archives the thread (section 8). Archived threads stay
    #: readable and are simply out of the way; delete is a separate, real
    #: delete.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: What the history list sorts by. Denormalised from the messages because
    #: the alternative is a correlated subquery on every list read, and this
    #: value is written by exactly one function.
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    #: Highest ``position`` used so far. The next message takes this plus one,
    #: which is what makes ordering a stored fact rather than a tie-break on
    #: timestamps that can collide.
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    summary: Mapped[str | None] = mapped_column(Text)
    summary_through_position: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    profile: Mapped["Profile"] = relationship()
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.position",
    )

    __table_args__ = (
        CheckConstraint("message_count >= 0", name="ck_conversations_message_count"),
        CheckConstraint(
            "summary_through_position >= 0",
            name="ck_conversations_summary_through_position",
        ),
    )


class ConversationMessage(Base):
    """One line in a thread (PRD 8, section 7).

    No ``updated_at``: a message is not edited. Correcting something means
    saying the next thing, which is how a conversation works and how this
    record stays an accurate account of one.

    ``role`` may be ``system`` or ``tool``, and those rows are stored because a
    thread nobody can replay exactly is not a record of anything. They are
    never returned to the app -- section 7 says plainly not to expose raw
    system or tool content -- and the read path filters on
    ``CONVERSATION_VISIBLE_ROLES`` rather than on a flag somebody sets per row.

    ``source`` exists so the future robot is a source of messages rather than a
    parallel system (section 70). Today only ``mobile_text`` is accepted from a
    client; ``system_proactive`` is written by the server itself.
    """

    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(
            f"role IN {sql_in_list(CONVERSATION_MESSAGE_ROLES)}",
            name="ck_conversation_messages_role",
        ),
        CheckConstraint(
            f"message_type IN {sql_in_list(CONVERSATION_MESSAGE_TYPES)}",
            name="ck_conversation_messages_type",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(CONVERSATION_MESSAGE_SOURCES)}",
            name="ck_conversation_messages_source",
        ),
        CheckConstraint(
            f"safety_mode IN {sql_in_list(SAFETY_MODES)}",
            name="ck_conversation_messages_safety_mode",
        ),
        CheckConstraint("position >= 0", name="ck_conversation_messages_position"),
        # Order inside a thread is a stored fact, not a tie-break on
        # timestamps -- two messages written in the same millisecond still
        # have an unambiguous order.
        UniqueConstraint(
            "conversation_id", "position", name="uq_conversation_messages_position"
        ),
        # A retried send never becomes a second message (section 57).
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="uq_conversation_messages_client_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="text"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="mobile_text"
    )
    #: Which safety mode was in force when this reply was written (sections 37
    #: and 80). Recorded per message rather than per conversation because
    #: seriousness is a property of a moment, not of a person.
    safety_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="normal"
    )
    #: Model, latency, tool names, prompt version (section 80). Never a chain
    #: of thought, never a prompt, never a credential.
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    client_message_id: Mapped[str | None] = mapped_column(String(CLIENT_ID_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class AssistantMemory(Base, TimestampMixin):
    """One durable thing the user asked Nura to keep (PRD 8, sections 40-47).

    Every row here was agreed to. ``source`` says how: ``user`` means they
    typed it on the memory screen, ``conversation`` means Nura noticed a
    durable preference, asked, and they pressed Remember (section 46). There is
    no third value, because there is no path that saves one quietly.

    ``is_active`` rather than a delete for the toggle case: turning a memory
    off must stop it reaching the model (section 47), and being able to turn it
    back on without retyping it is worth one column. Removing a memory for good
    is a real delete, and it touches nothing else -- forgetting "call me Baba"
    does not touch the profile that holds the actual name (section 47).
    """

    __tablename__ = "assistant_memories"
    __table_args__ = (
        CheckConstraint(
            f"category IN {sql_in_list(ASSISTANT_MEMORY_CATEGORIES)}",
            name="ck_assistant_memories_category",
        ),
        CheckConstraint(
            f"source IN {sql_in_list(ASSISTANT_MEMORY_SOURCES)}",
            name="ck_assistant_memories_source",
        ),
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
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(String(MEMORY_MAX_LENGTH), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    #: When the user agreed to it. Set for both sources -- adding one by hand
    #: is agreeing to it -- so "has a human ever confirmed this?" is one
    #: column rather than a rule about which source implies what.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    profile: Mapped["Profile"] = relationship()


class AssistantPreferences(Base, TimestampMixin):
    """How Nura should sound, for one person (PRD 8, sections 22-34 and 88).

    One row per profile, created on first read so no screen has to handle
    "you have not configured Nura yet".

    The five dials all use the same three-step scale (section 23). A preset
    sets all five at once and then stops mattering: what is stored is the five
    values, so nudging one dial after choosing Gentle does not silently put the
    person back on a preset they have now departed from.

    ``custom_instructions`` lives here rather than in a table of its own --
    section 87 lists one, but it would hold exactly one text value per profile
    and an extra join. It is still the thing section 26 describes: it is
    length-limited, it is rendered as untrusted data, and it cannot move the
    safety boundary.

    ``mode`` is the app-level mode from section 65: ``normal``, ``focus``,
    ``sleep`` or ``privacy``. Serious mode is deliberately not one of these
    values -- it is derived per message and overrides what is stored here
    without changing it (section 69).
    """

    __tablename__ = "assistant_preferences"
    __table_args__ = (
        CheckConstraint(
            f"personality_preset IN {sql_in_list(PERSONALITY_PRESETS)}",
            name="ck_assistant_preferences_preset",
        ),
        CheckConstraint(
            f"warmth IN {sql_in_list(PERSONALITY_LEVELS)}",
            name="ck_assistant_preferences_warmth",
        ),
        CheckConstraint(
            f"humour IN {sql_in_list(PERSONALITY_LEVELS)}",
            name="ck_assistant_preferences_humour",
        ),
        CheckConstraint(
            f"talkativeness IN {sql_in_list(PERSONALITY_LEVELS)}",
            name="ck_assistant_preferences_talkativeness",
        ),
        CheckConstraint(
            f"reminder_firmness IN {sql_in_list(PERSONALITY_LEVELS)}",
            name="ck_assistant_preferences_reminder_firmness",
        ),
        CheckConstraint(
            f"proactivity IN {sql_in_list(PROACTIVITY_LEVELS)}",
            name="ck_assistant_preferences_proactivity",
        ),
        CheckConstraint(
            f"verbosity IN {sql_in_list(VERBOSITY_LEVELS)}",
            name="ck_assistant_preferences_verbosity",
        ),
        CheckConstraint(
            f"voice_id IN {sql_in_list(ASSISTANT_VOICES)}",
            name="ck_assistant_preferences_voice",
        ),
        CheckConstraint(
            f"speaking_speed IN {sql_in_list(SPEAKING_SPEEDS)}",
            name="ck_assistant_preferences_speaking_speed",
        ),
        CheckConstraint(
            f"mode IN {sql_in_list(ASSISTANT_MODES)}",
            name="ck_assistant_preferences_mode",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # --- personality (sections 22 and 23) ---
    # The defaults are exactly the ``gentle`` preset in ``preferences.py``, so
    # a profile that has never opened the Personality screen is *on* a preset
    # rather than on an unnamed combination no button corresponds to. Gentle
    # because a health companion that arrives warm, quiet and humourless is
    # the right first impression; anybody who wants more can move a dial.
    personality_preset: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="gentle"
    )
    warmth: Mapped[str] = mapped_column(String(8), nullable=False, server_default="high")
    humour: Mapped[str] = mapped_column(String(8), nullable=False, server_default="low")
    talkativeness: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="medium"
    )
    proactivity: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="low"
    )
    reminder_firmness: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="low"
    )

    # --- voice and length (sections 27-31) ---
    verbosity: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="balanced"
    )
    voice_id: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default="calm"
    )
    speaking_speed: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="normal"
    )
    #: Kept beside the other assistant settings rather than read from
    #: ``user_settings.language``, because section 31 asks the architecture to
    #: support a future where Nura converses in a language other than the one
    #: the interface is in. Today the only implemented value is ``en``.
    assistant_language: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="en"
    )

    # --- behaviour (sections 25 and 65) ---
    custom_instructions: Mapped[str | None] = mapped_column(
        String(CUSTOM_INSTRUCTIONS_MAX_LENGTH)
    )
    mode: Mapped[str] = mapped_column(String(12), nullable=False, server_default="normal")

    profile: Mapped["Profile"] = relationship()


class AssistantPromptDismissal(Base):
    """A proactive prompt the user has already waved away (PRD 8, section 36).

    Section 36 says not to keep prompting after a dismissal, which needs
    somewhere to write down that it happened. ``subject_key`` is what the
    prompt was about -- an appointment id, a date -- so dismissing tomorrow's
    preparation nudge does not also silence next month's.

    Kept deliberately thin: no counters, no snooze windows, no scoring. A row
    here means "not this one", and the absence of a row means the prompt is
    still allowed.
    """

    __tablename__ = "assistant_prompt_dismissals"
    __table_args__ = (
        CheckConstraint(
            f"prompt_kind IN {sql_in_list(ASSISTANT_PROMPT_KINDS)}",
            name="ck_assistant_prompt_dismissals_kind",
        ),
        UniqueConstraint(
            "profile_id",
            "prompt_kind",
            "subject_key",
            name="uq_assistant_prompt_dismissals_subject",
        ),
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
    prompt_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_key: Mapped[str] = mapped_column(
        String(PROMPT_SUBJECT_MAX_LENGTH), nullable=False
    )
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    profile: Mapped["Profile"] = relationship()
