"""An authorized family message, shown on a shelf.

PRD 11, sections 24, 25, 53, 78, 101 and 126.

**A presentation can only come from a message that already exists.** Section
126's first test. ``build`` takes a stored ``FamilyMessage``; there is no
parameter through which text could be supplied, so there is no path by which
something that was never an authorized message becomes a card on a robot.

**The permission is re-checked when the card is built, not when the message
was sent.** PRD 10 section 86 learned this the hard way about safety alerts and
it applies here for the same reason: a caregiver whose ``communication``
permission was withdrawn this morning should not have their message appear on
the shelf this afternoon. The message itself stays -- section 101 is explicit
that nothing here may invalidate a message -- it simply stops being queued.

**Only messages addressed to the person are shown.** A message the person sent
themselves is theirs already; replaying it on their own robot would be odd and
would put their words on a screen in a room they may have left.

**Long messages stop.** Section 78: ninety characters, cut at a word boundary,
then "Open the Nura app to read more." Section 112's sanitisation happens in
``layouts``, so a message containing control characters or something that looks
like a payload is a string in a field and nothing else.

**Reading aloud is off unless three things are true** (sections 25, 43 and 82):
the capability exists, the person turned it on, and the mode is not one that
suppresses audio. No deployment satisfies the first, which is why ``speak`` has
never been true.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CaregiverRelationship,
    Device,
    DevicePresentation,
    FamilyMessage,
    FamilyThread,
)
from app.models.enums import CAREGIVER_ACTIVE_STATUSES
from app.services.caregivers import permissions as permission_service
from app.services.caregivers import wording as family_wording
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "family_message"
PRESENTATION_TYPE = "family_message"

#: The permission that allowed the message to exist, re-checked here.
MESSAGE_PERMISSION = "communication"

#: How recent a message has to be to be worth putting on a screen. A message
#: from three days ago is not news, and section 55 gives the card 24 hours.
RECENT = timedelta(hours=24)

ACTIONS = ("open_app", "dismiss")


def source_id(message: FamilyMessage) -> str:
    return str(message.id)


def preview_text(message: FamilyMessage) -> str | None:
    """What the message says, as one line.

    A check-in is rendered with PRD 9's own sentence rather than a second
    phrasing invented here, so "Thinking of you." reads the same on the robot
    as it does in the app.
    """
    if message.message_type == "check_in" and message.check_in_code:
        return family_wording.check_in_sentence(message.check_in_code)
    if message.message_type == "text":
        return message.text
    # A photo or a system message has nothing a 240-pixel screen can show.
    return None


def relationship_for(db: Session, message: FamilyMessage) -> CaregiverRelationship | None:
    thread = db.get(FamilyThread, message.thread_id)
    if thread is None:
        return None
    return db.get(CaregiverRelationship, thread.relationship_id)


def is_presentable(
    db: Session,
    device: Device,
    message: FamilyMessage,
    now: datetime,
) -> bool:
    """The four conditions in section 24, checked now rather than remembered.

    An authorized message exists; the permission that authorized it is still
    granted; it was sent to this person rather than by them; and it is recent
    and unread. Whether the *robot* may show it -- the preference and the
    display capability -- is section 24's other two conditions, and they are
    checked by the caller because they are about the device, not the message.
    """
    if message.sender_side != "caregiver":
        return False
    if message.read_at is not None:
        return False
    if now - message.created_at > RECENT:
        return False
    if preview_text(message) is None:
        return False
    thread = db.get(FamilyThread, message.thread_id)
    if thread is None or thread.profile_id != device.owner_profile_id:
        return False
    relationship = db.get(CaregiverRelationship, thread.relationship_id)
    if relationship is None or relationship.status not in CAREGIVER_ACTIVE_STATUSES:
        return False
    return MESSAGE_PERMISSION in permission_service.granted_keys(relationship)


def build(
    message: FamilyMessage,
    *,
    sender_label: str,
    has_input: bool,
    speak: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One message card (sections 24 and 78)."""
    text = preview_text(message)
    assert text is not None  # callers check ``is_presentable`` first
    body, truncated = layouts.shorten(text, layouts.MESSAGE_MAX)
    payload = layouts.build_payload(
        "MESSAGE",
        title=wording.PRESENTATION_TITLES[PRESENTATION_TYPE],
        sender=sender_label,
        body=body,
        continue_in_app=truncated,
        # Shortened here rather than by ``build_payload``, so the flag
        # has to be set here too (section 77).
        truncated=True if truncated else None,
        actions=list(ACTIONS) if has_input else [],
        respond_in_app=not has_input,
        sensitive=True,
        speak=speak,
        chime="message" if chime else None,
    )
    return queue.PresentationRequest(
        presentation_type=PRESENTATION_TYPE,
        layout="MESSAGE",
        payload=payload,
        source=SOURCE,
        source_id=source_id(message),
    )


def queue_for_message(
    db: Session,
    device: Device,
    message: FamilyMessage,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Queues a message card if every condition in section 24 holds."""
    if not is_presentable(db, device, message, now):
        return None
    _, resolved_preferences = preferences.resolved_for(db, device, now)
    if not resolved_preferences.family_message_display_enabled:
        return None

    resolved_mode = mode or modes.resolve(db, device, now)
    states = capability_service.capability_map(db, device, now)
    relationship = relationship_for(db, message)
    speak = (
        resolved_preferences.read_messages_aloud
        and capability_service.can_speak(states)
        and not modes.suppresses_audio(resolved_mode.mode)
    )
    request = build(
        message,
        sender_label=relationship.invited_name if relationship else "Family",
        has_input=capability_service.has_input(states),
        speak=speak,
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def recent_for_profile(
    db: Session, profile_id: object, now: datetime
) -> list[FamilyMessage]:
    """Unread messages to this person from the last day, oldest first."""
    return list(
        db.execute(
            select(FamilyMessage)
            .join(FamilyThread, FamilyThread.id == FamilyMessage.thread_id)
            .where(
                FamilyThread.profile_id == profile_id,
                FamilyMessage.sender_side == "caregiver",
                FamilyMessage.read_at.is_(None),
                FamilyMessage.created_at >= now - RECENT,
            )
            .order_by(FamilyMessage.created_at.asc())
        )
        .scalars()
        .all()
    )


def cancel_for_message(
    db: Session,
    device: Device,
    message: FamilyMessage,
    now: datetime,
    *,
    reason: str = "source_resolved",
) -> int:
    """Withdraws a card for a message that has been read in the app."""
    return queue.cancel_for_source(
        db,
        device.id,
        source=SOURCE,
        source_id=source_id(message),
        reason=reason,
        now=now,
        presentation_type=PRESENTATION_TYPE,
    )
