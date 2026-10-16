"""What was done, kept so it can be answered for (PRD 9, sections 49, 50, 51).

One writer, one shape, and a deliberately short list of things worth recording.

**There is no event for reading anything.** Section 49 says not to notify the
user every time a caregiver views a permitted category, and section 50 says not
to build a user-facing feed of read operations. A care app that records every
glance is the surveillance experience section 2 rules out, and the audit trail
is more useful for being shorter: every row here is somebody *changing*
something.

**Nothing medical reaches ``meta``.** Section 51 asks for minimal metadata and
sections 68 and 69 forbid health or message content in logs. Every payload below
is built from a fixed set of keys -- a permission key, an action type, a count --
and the helpers take no free text at all. A medication name cannot get in here
because no function in this module accepts one.

There is no read API for these rows in PRD 9, and that is on purpose: section 50
asks for backend auditability, not a feed. ``psql`` is the reader.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import CaregiverAuditEvent
from app.models.enums import CAREGIVER_AUDIT_ACTOR_KINDS, CAREGIVER_AUDIT_EVENT_TYPES

logger = logging.getLogger(__name__)


def record(
    db: Session,
    *,
    profile_id: uuid.UUID,
    actor_account_id: uuid.UUID | None,
    actor_kind: str,
    event_type: str,
    now: datetime,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> CaregiverAuditEvent:
    """Adds one event. The caller commits, inside the same transaction.

    Deliberately part of the caller's transaction rather than a separate commit:
    a permission change that saved while its audit row did not would be worse
    than either failing. If the write fails, the change fails.

    ``meta`` is passed through as given, so the keys a caller uses are the keys
    stored. The log lines below name the event type and nothing else -- not the
    profile, not the account, not the target (section 69 allows
    ``caregiver.permission.updated`` and no more).
    """
    assert event_type in CAREGIVER_AUDIT_EVENT_TYPES, event_type
    assert actor_kind in CAREGIVER_AUDIT_ACTOR_KINDS, actor_kind

    event = CaregiverAuditEvent(
        profile_id=profile_id,
        actor_account_id=actor_account_id,
        actor_kind=actor_kind,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        meta=meta,
        created_at=now,
    )
    db.add(event)
    logger.info("caregiver.audit.%s", event_type)
    return event


def permission_change_meta(changed_keys: list[str]) -> dict[str, Any]:
    """Which categories moved. Keys only -- never what they unlocked."""
    return {"changed": sorted(changed_keys)}


def role_change_meta(previous: str, current: str) -> dict[str, Any]:
    """Both labels, because a role change is only legible as a pair.

    Safe to store: a role is one of five fixed words and grants nothing
    (section 10).
    """
    return {"from": previous, "to": current}


def suggestion_meta(action_type: str) -> dict[str, Any]:
    """What kind of change it was. Never the payload.

    The payload holds the proposed time, which is not medical but is also not
    needed to answer "who approved what" -- and keeping it out means this table
    can never become a second copy of somebody's schedule.
    """
    return {"action_type": action_type}


def priority_change_meta(count: int) -> dict[str, Any]:
    """How many contacts were in the chain when it was reordered."""
    return {"contact_count": count}
