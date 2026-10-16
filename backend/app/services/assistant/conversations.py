"""Threads and the messages in them (PRD 8, sections 7, 8, 57, 61 and 79).

**A thread, not a log.** Section 8 says not to create one endless permanent
thread, and this module is what makes that true: conversations are created,
titled, archived and deleted one at a time, and deleting one takes its
messages and nothing else with it. No medication, symptom, appointment or
memory is reachable from here by a cascade or otherwise (section 61).

**Order is stored, not inferred.** Every message carries a ``position``,
unique within its thread. Two messages written in the same millisecond -- the
user's and the tool notice that follows it -- still have an unambiguous
order, which a timestamp sort cannot promise.

**System and tool rows are stored and never shown.** They are what makes a
thread replayable and a bug reproducible. ``visible_messages`` is the only
read path the API uses, and it filters on the role, so exposing them would
take a deliberate new function rather than a forgotten flag (section 7).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, ConversationMessage
from app.models.assistant import (
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
)
from app.models.enums import CONVERSATION_VISIBLE_ROLES
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: How many threads one profile may keep. Generous; it exists so a runaway
#: client cannot fill a table, not to ration conversations.
MAX_CONVERSATIONS = 200

#: How many messages one thread may hold before the app is asked to start a
#: new one. Section 8's "do not create one endless thread", enforced rather
#: than suggested.
MAX_MESSAGES = 400

#: How many recent messages are replayed to the model (sections 77 and 78).
#: Everything older is covered by the thread summary.
CONTEXT_MESSAGE_LIMIT = 20

#: A thread longer than this gets summarised, so the replay stays bounded.
SUMMARY_TRIGGER = 24

#: Used until the first user message gives us something better.
DEFAULT_TITLE = "New conversation"


class ConversationNotFoundError(NotFoundError):
    """No such conversation for this profile."""


class TooManyConversationsError(DomainError):
    """This profile has as many threads as it may keep."""

    code = "too_many_conversations"


class ConversationFullError(DomainError):
    """This thread is long enough; start a new one."""

    code = "conversation_full"


def title_from(text: str) -> str:
    """A thread title from its opening message.

    Taken from what the user typed rather than asked of the model: it costs
    nothing, it is available before the reply exists, and a title that is the
    beginning of the question is one the user recognises in a list.
    """
    words = " ".join(text.split())
    if not words:
        return DEFAULT_TITLE
    if len(words) <= 48:
        return words[:CONVERSATION_TITLE_MAX_LENGTH]
    return words[:45].rstrip(" ,.;:") + "…"


# --- threads ----------------------------------------------------------------


def list_conversations(
    db: Session, profile_id: uuid.UUID, *, include_archived: bool = False
) -> list[Conversation]:
    """This profile's threads, most recently spoken in first."""
    query = select(Conversation).where(Conversation.profile_id == profile_id)
    if not include_archived:
        query = query.where(Conversation.archived_at.is_(None))
    return list(
        db.execute(
            query.order_by(
                Conversation.last_message_at.desc().nulls_last(),
                Conversation.created_at.desc(),
            )
        )
        .scalars()
        .all()
    )


def get_conversation(
    db: Session, profile_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    """One thread, by profile *and* id together."""
    conversation = db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.profile_id == profile_id,
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ConversationNotFoundError("That conversation could not be found.")
    return conversation


def _count(db: Session, profile_id: uuid.UUID) -> int:
    return int(
        db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.profile_id == profile_id
            )
        ).scalar_one()
    )


def create_conversation(
    db: Session, profile_id: uuid.UUID, *, title: str | None = None
) -> Conversation:
    """Starts a thread."""
    if _count(db, profile_id) >= MAX_CONVERSATIONS:
        raise TooManyConversationsError(
            "There are too many conversations. Delete one to start another."
        )
    conversation = Conversation(
        profile_id=profile_id,
        title=(title or DEFAULT_TITLE)[:CONVERSATION_TITLE_MAX_LENGTH],
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    logger.info("assistant: started a conversation")
    return conversation


def rename_conversation(
    db: Session, conversation: Conversation, title: str
) -> Conversation:
    conversation.title = (title.strip() or DEFAULT_TITLE)[:CONVERSATION_TITLE_MAX_LENGTH]
    db.commit()
    db.refresh(conversation)
    return conversation


def set_archived(
    db: Session, conversation: Conversation, *, archived: bool, now: datetime
) -> Conversation:
    """Archives or restores a thread (section 8)."""
    conversation.archived_at = now if archived else None
    db.commit()
    db.refresh(conversation)
    logger.info("assistant: %s a conversation", "archived" if archived else "restored")
    return conversation


def delete_conversation(db: Session, conversation: Conversation) -> None:
    """Deletes a thread and its messages. Nothing else (section 61)."""
    db.delete(conversation)
    db.commit()
    logger.info("assistant: deleted a conversation")


# --- messages ---------------------------------------------------------------


def visible_messages(
    db: Session, conversation_id: uuid.UUID
) -> list[ConversationMessage]:
    """The messages a user is shown, oldest first (section 7)."""
    return list(
        db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.role.in_(CONVERSATION_VISIBLE_ROLES),
            )
            .order_by(ConversationMessage.position.asc())
        )
        .scalars()
        .all()
    )


def all_messages(db: Session, conversation_id: uuid.UUID) -> list[ConversationMessage]:
    """Every row, including system and tool. For replay and tests only."""
    return list(
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.position.asc())
        )
        .scalars()
        .all()
    )


def find_by_client_id(
    db: Session, conversation_id: uuid.UUID, client_message_id: str
) -> ConversationMessage | None:
    """The message a client already sent with this id, if any (section 57)."""
    return db.execute(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.client_message_id == client_message_id,
        )
    ).scalar_one_or_none()


def append_message(
    db: Session,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    now: datetime,
    message_type: str = "text",
    source: str = "mobile_text",
    safety_mode: str = "normal",
    meta: dict[str, Any] | None = None,
    client_message_id: str | None = None,
    commit: bool = True,
) -> ConversationMessage:
    """Adds one line to a thread.

    ``message_count`` doubles as the next position, which is why it is on the
    conversation rather than counted per insert: two requests racing to append
    would otherwise both read the same count and collide on the unique
    constraint -- and with it there, the collision is caught by the database
    instead of producing two messages numbered the same.
    """
    if conversation.message_count >= MAX_MESSAGES:
        raise ConversationFullError(
            "This conversation is long enough. Please start a new one."
        )

    message = ConversationMessage(
        conversation_id=conversation.id,
        position=conversation.message_count,
        role=role,
        message_type=message_type,
        content=content[:MESSAGE_MAX_LENGTH] if role == "user" else content,
        source=source,
        safety_mode=safety_mode,
        meta=meta or {},
        client_message_id=client_message_id,
        created_at=now,
    )
    db.add(message)
    conversation.message_count += 1
    conversation.last_message_at = now
    if commit:
        db.commit()
        db.refresh(message)
    return message


def recent_for_context(
    db: Session, conversation: Conversation, *, limit: int = CONTEXT_MESSAGE_LIMIT
) -> list[ConversationMessage]:
    """The tail of a thread, oldest first, for replay to the model.

    Only what a user or Nura actually said. Tool calls and their results are
    not replayed across turns: they were answered at the time, they are the
    bulkiest thing in a thread, and a stale tool result is worse than no tool
    result because the model has no way to tell it is stale (section 77).

    Anything already covered by the stored summary is skipped, so a long
    thread costs a summary plus a tail rather than growing without bound.
    """
    rows = (
        db.execute(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation.id,
                ConversationMessage.role.in_(CONVERSATION_VISIBLE_ROLES),
                ConversationMessage.position >= conversation.summary_through_position,
            )
            .order_by(ConversationMessage.position.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))


def needs_summary(conversation: Conversation) -> bool:
    """Whether the thread has outgrown what is replayed (section 79)."""
    unsummarised = conversation.message_count - conversation.summary_through_position
    return unsummarised > SUMMARY_TRIGGER


def store_summary(
    db: Session, conversation: Conversation, *, summary: str, through: int
) -> None:
    """Records a thread summary and how far it reaches.

    Working state, not user-facing memory (section 79). It lives on the
    conversation and dies with it.
    """
    conversation.summary = summary.strip()[:2000]
    conversation.summary_through_position = through
    db.commit()
