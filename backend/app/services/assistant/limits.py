"""How often one person may ask Nura something (PRD 8, sections 77 and 97).

Counted from the messages already stored rather than from a counter table: a
rate limit that needs its own schema, its own expiry and its own reconciliation
is three more things to get wrong, and the rows this counts are written by the
same transaction that would have incremented the counter.

Per profile rather than per account. An account with two profiles is two
people being helped, and rationing one because the other had a busy morning
would be the wrong shape of limit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, ConversationMessage
from app.services.errors import DomainError

#: The window the limit is measured over.
WINDOW = timedelta(hours=1)


class RateLimitedError(DomainError):
    """This profile has sent as many messages as the hour allows."""

    status_code = 429
    code = "rate_limited"


def messages_in_window(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """User messages this profile has sent in the last hour.

    Only ``user`` rows are counted. A conversation where Nura ran four tools
    is not four times as expensive to the person who sent one message, and
    counting the machinery would make a thorough answer cost the user their
    next question.
    """
    return int(
        db.execute(
            select(func.count(ConversationMessage.id))
            .join(Conversation, Conversation.id == ConversationMessage.conversation_id)
            .where(
                Conversation.profile_id == profile_id,
                ConversationMessage.role == "user",
                ConversationMessage.created_at >= now - WINDOW,
            )
        ).scalar_one()
    )


def check(db: Session, profile_id: uuid.UUID, now: datetime, limit: int) -> None:
    """Refuses the request if the hour's allowance is used up."""
    if limit <= 0:
        return
    if messages_in_window(db, profile_id, now) >= limit:
        raise RateLimitedError(
            "You have sent Nura a lot of messages in the last hour. "
            "Please try again shortly."
        )
