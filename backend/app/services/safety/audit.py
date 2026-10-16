"""What the safety system did, kept so it can be answered for.

PRD 10, sections 89, 90, 91 and 121.

One writer, one shape, and the shortest useful list of things worth recording.
Section 89 names eighteen transitions and this module writes all of them;
section 90 names what must not go in and this module has no way to put it
there.

**Nothing medical, and nothing identifying.** Section 90 rules out the health
record, unrelated symptom history and private caregiver messages; section 121
adds raw audio and video, which do not exist. Every ``meta`` payload below is
built by a helper in this file from a fixed set of keys -- a status, a channel,
an outcome, a count, a number of seconds. **No helper takes free text, a name,
or a phone number**, so none can reach the table. A test asserts exactly that
by reading this module's helper signatures.

**Nor does an audit row say who was reached.** A recipient's name lives on the
escalation attempt, where it is needed to render section 42's list, and a
``recipient_count`` is all the trail keeps. The question an audit answers is
"what did the system do", and "it created three alerts" answers it.

**Retention** (section 91) is documented in
``docs/architecture/safety-monitoring.md`` and enforced nowhere yet: there is
no deletion job in this project for any table, and inventing one only for
safety rows would delete the evidence first. The rows are small -- a few per
event -- and the documented policy is what a later PRD implements.

There is no read API for these rows. Section 89 asks for a trail, not a feed,
and the safety *history* the user and caregivers see is built from
``safety_events`` -- the thing that happened -- rather than from the trail of
how the system handled it. ``psql`` is the reader.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import SafetyAuditEvent
from app.models.enums import SAFETY_AUDIT_ACTOR_KINDS, SAFETY_AUDIT_EVENT_TYPES

logger = logging.getLogger(__name__)


def record(
    db: Session,
    *,
    profile_id: uuid.UUID,
    actor_account_id: uuid.UUID | None,
    actor_kind: str,
    event_type: str,
    now: datetime,
    safety_event_id: uuid.UUID | None = None,
    monitoring_session_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> SafetyAuditEvent:
    """Adds one row, inside the caller's transaction.

    Part of the caller's transaction on purpose, as the caregiver trail is: an
    escalation that started while its audit row did not would be worse than
    either failing.

    The log line names the event type and nothing else -- not the profile, not
    the account, not the recipient. Section 122 allows generic events and this
    is the generic form of one.
    """
    assert event_type in SAFETY_AUDIT_EVENT_TYPES, event_type
    assert actor_kind in SAFETY_AUDIT_ACTOR_KINDS, actor_kind

    event = SafetyAuditEvent(
        profile_id=profile_id,
        safety_event_id=safety_event_id,
        monitoring_session_id=monitoring_session_id,
        actor_account_id=actor_account_id,
        actor_kind=actor_kind,
        event_type=event_type,
        meta=meta,
        created_at=now,
    )
    db.add(event)
    logger.info("safety.audit.%s", event_type)
    return event


def monitoring_meta(duration_mode: str, response_timeout_seconds: int) -> dict[str, Any]:
    """What kind of session it was. Two fixed vocabularies and a number."""
    return {
        "duration_mode": duration_mode,
        "response_timeout_seconds": response_timeout_seconds,
    }


def end_meta(end_reason: str) -> dict[str, Any]:
    """Why monitoring stopped. One of four words."""
    return {"end_reason": end_reason}


def trigger_meta(event_type: str, trigger_source: str) -> dict[str, Any]:
    """What arrived, and from where. Both from fixed tuples."""
    return {"event_type": event_type, "trigger_source": trigger_source}


def timeout_meta(seconds: int, *, second_prompt: bool) -> dict[str, Any]:
    """How long the wait was, and which of the two it was."""
    return {"seconds": seconds, "second_prompt": second_prompt}


def escalation_meta(*, recipient_count: int, reason: str) -> dict[str, Any]:
    """How many recipients the plan had, and what started it.

    A count, not a list. Who was attempted is on the attempt rows, where it is
    needed; the trail does not need it twice and section 90 prefers it did not
    have it at all.
    """
    return {"recipient_count": recipient_count, "reason": reason}


def attempt_meta(
    *, channel: str, status: str, failure_code: str | None
) -> dict[str, Any]:
    """One attempt's shape. Three values, all from fixed vocabularies."""
    return {"channel": channel, "status": status, "failure_code": failure_code}


def outcome_meta(outcome: str) -> dict[str, Any]:
    """How the escalation finished. One of six words."""
    return {"outcome": outcome}


def resolution_meta(resolution: str, *, late: bool = False) -> dict[str, Any]:
    """How the event finished, and whether the answer came after escalation.

    ``late`` is section 126: a user saying "I'm okay" once alerts already
    exist is a different fact from saying it in time, and the trail keeps both
    rather than overwriting the first with the second.
    """
    return {"resolution": resolution, "late": late}


def false_alarm_meta(*, false_positive: bool, reason: str | None) -> dict[str, Any]:
    """The label and its optional coded reason (sections 47 and 48)."""
    return {"false_positive": false_positive, "reason": reason}
