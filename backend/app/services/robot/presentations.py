"""The one door into the robot from the rest of the product.

PRD 11, sections 26, 51, 52, 53, 54, 71, 72, 100, 101 and 102.

Everything PRD 0-10 needs from PRD 11 is in this module, and the module is
small on purpose. Two functions, each of which:

  - finds the robots belonging to a profile, if there are any;
  - does nothing at all when there are none, which is every deployment today;
  - **cannot raise**. A failure here is logged and swallowed, because the
    caller is in the middle of answering somebody and the robot is additive
    (sections 51-54 and 100-102). A robot that is unbuilt, offline, headless
    or broken must not be able to fail a reply, a reminder or an escalation.

**This is the bounded service section 71 asks for.** The assistant hands over a
string, an id and one boolean. It cannot name a layout, cannot supply a
payload, cannot choose a priority and cannot reach any other presentation type
-- so the strongest thing a confused or compromised model could do is put its
own words on the owner's own screen, shortened, with no face.

**Nothing else in PRD 0-10 calls into here.** Medication, appointments, family
messages and safety are reconciled by ``presenter.refresh`` from current state
rather than pushed from the services that own them, which is why none of those
services had to change and why none of their cards can go stale. The assistant
is the exception because a reply is an utterance rather than a state: there is
nothing to reconcile it against.
"""

import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device
from app.services.robot import queue
from app.services.robot.builders import assistant as assistant_builder

logger = logging.getLogger(__name__)


def devices_for(db: Session, profile_id: uuid.UUID) -> list[Device]:
    """The claimed robots linked to this person. Usually none."""
    return list(
        db.execute(
            select(Device).where(
                Device.owner_profile_id == profile_id,
                Device.claimed_by_account_id.is_not(None),
            )
        )
        .scalars()
        .all()
    )


def show_reply(
    db: Session,
    profile_id: uuid.UUID,
    *,
    text: str,
    source_id: str,
    serious: bool,
    now: datetime,
) -> int:
    """Puts an assistant reply on this person's robots (section 26).

    Returns how many robots got a card, which is zero in every deployment
    today. ``serious`` comes from PRD 8's own per-message decision rather than
    being recomputed, so there is one answer to "was this a serious moment"
    (section 7).
    """
    return _safely(
        "assistant_reply",
        lambda device: assistant_builder.queue_reply(
            db,
            device,
            text=text,
            source_id=source_id,
            serious=serious,
            now=now,
        ),
        db,
        profile_id,
    )


def clear_assistant_replies(db: Session, profile_id: uuid.UUID, now: datetime) -> int:
    """Withdraws any reply still on screen, e.g. when a conversation is deleted."""
    return _safely(
        "assistant_clear",
        lambda device: queue.cancel_types(
            db,
            device.id,
            presentation_types=(assistant_builder.PRESENTATION_TYPE,),
            reason="source_cancelled",
            now=now,
        ),
        db,
        profile_id,
    )


def _safely(what: str, action, db: Session, profile_id: uuid.UUID) -> int:  # type: ignore[no-untyped-def]
    """Runs ``action`` for each robot, and never lets it out.

    The broad ``except`` is deliberate and is the point of this module: the
    caller is answering a person. Sections 100-102 say no workflow may depend
    on presentation, and the only way to be sure of that is for the call into
    presentation to be incapable of failing the call that made it.
    """
    done = 0
    for device in devices_for(db, profile_id):
        try:
            if action(device):
                done += 1
        except Exception:  # noqa: BLE001 - see the docstring
            logger.exception("robot.%s failed; the caller is unaffected", what)
    return done
