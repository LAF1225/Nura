"""An assistant reply, made short enough for a shelf.

PRD 11, sections 26, 71, 72, 79, 80 and 128.

**The model cannot reach the protocol.** Section 71: the assistant may request
a presentation only through a bounded service, and must not emit firmware
payload JSON. ``build`` takes a string and three booleans. There is no layout
parameter, no actions parameter and no payload parameter -- so the strongest
thing a compromised or confused model could do is supply text, which is
sanitised and shortened like any other text, and two flags that only ever
narrow what happens.

**Concise, whatever the app is set to.** Section 80 fixes the robot's verbosity
regardless of PRD 8's verbosity preference, and section 79 forbids dumping a
full mobile reply onto the display. So the reply is cut to one short paragraph
and the rest becomes "Continue in the Nura app".

**Serious replies use the information layout.** Sections 7 and 26: a serious
moment gets no face and no decoration. PRD 8 already decides what counts as
serious, per message, and that decision is passed in rather than recomputed --
a second opinion about whether a moment is serious is exactly the kind of drift
section 75 warns about.

**An assistant card never competes with safety.** Sections 72 and 128. Two
things make that true, and the second is the one that matters: the priority
table puts ``assistant_response`` below everything to do with safety, *and*
this builder refuses to queue at all while a safety event is live. A reply
waiting politely behind an emergency card would still be a reply Nura was
composing during an emergency.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Device, DevicePresentation
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "assistant"
PRESENTATION_TYPE = "assistant_response"

#: Section 80. Shorter than ``layouts.BODY_MAX`` on purpose: the limit there is
#: what a layout can hold, and this is what a person reads from a desk without
#: stopping what they are doing.
ROBOT_REPLY_MAX = 110

#: The modes in which Nura does not put a reply on the shelf at all.
NO_REPLY_MODES = ("emergency", "safety", "sleep", "privacy", "offline", "error")


def build(
    text: str,
    *,
    source_id: str,
    serious: bool,
    speak: bool,
    has_input: bool,
) -> queue.PresentationRequest:
    """One reply card (section 26).

    The layout is chosen here from ``serious`` rather than being passed in,
    which is section 7 enforced structurally: there is no way to ask for an
    animated presentation of a serious reply.
    """
    body, truncated = layouts.shorten(text, ROBOT_REPLY_MAX)
    payload = layouts.build_payload(
        "TITLE_BODY",
        title=wording.PRESENTATION_TITLES[PRESENTATION_TYPE],
        body=body,
        serious=serious,
        continue_in_app=truncated,
        # Shortened here rather than by ``build_payload``, so the flag
        # has to be set here too (section 77).
        truncated=True if truncated else None,
        actions=["open_app", "dismiss"] if has_input else [],
        respond_in_app=not has_input,
        sensitive=True,
        speak=speak,
    )
    return queue.PresentationRequest(
        presentation_type=PRESENTATION_TYPE,
        layout="TITLE_BODY",
        payload=payload,
        source=SOURCE,
        source_id=source_id,
    )


def queue_reply(
    db: Session,
    device: Device,
    *,
    text: str,
    source_id: str,
    serious: bool,
    now: datetime,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Puts a reply on the robot, if this is a moment for one.

    ``source_id`` is the conversation message's id, so a retried send does not
    produce a second card (section 57).
    """
    resolved_mode = mode or modes.resolve(db, device, now)
    if resolved_mode.mode in NO_REPLY_MODES:
        logger.info("robot.assistant_reply_suppressed mode=%s", resolved_mode.mode)
        return None

    _, resolved_preferences = preferences.resolved_for(db, device, now)
    states = capability_service.capability_map(db, device, now)
    speak = (
        resolved_preferences.read_assistant_aloud
        and capability_service.can_speak(states)
        and not modes.suppresses_audio(resolved_mode.mode)
    )
    request = build(
        text,
        source_id=source_id,
        serious=serious,
        speak=speak,
        has_input=capability_service.has_input(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)
