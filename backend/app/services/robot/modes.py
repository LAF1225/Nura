"""Which mode the robot is in, worked out rather than stored.

PRD 11, sections 4, 7, 27, 28, 31, 32, 33, 34, 36, 83, 84 and 98.

**One mode system, not two.** Section 4 says to map onto the mode system Nura
already has and not to build a competing framework. Four of the ten modes are
PRD 8's ``assistant_preferences.mode`` seen from the robot's side -- ``normal``
becomes ``companion``, and ``focus``, ``sleep`` and ``privacy`` keep their
names. The other six are not settings at all: they are facts about the moment,
and they are read off PRD 2's heartbeats and PRD 10's live safety state.

**Nothing stores a robot mode.** Exactly as PRD 10 does not store emergency
mode: a column meaning "right now" is wrong the moment it is written. The mode
is computed on every read, which is also why a mode cannot be left stale by a
crash -- there is nothing to leave behind.

**Safety outranks everything a person chose.** Sleep, focus and privacy are
settings; an emergency is not. Section 31 says emergency overrides sleep,
section 32 that safety still overrides focus, and section 72 that nothing from
the assistant may outrank safety state. All three are the same comparison here,
made once.

**``error`` is the robot's own word and the backend never says it.** Section 36
lists what it is for -- Wi-Fi unavailable, something needing attention -- and
every one of those is something only the robot can know; section 98 then says
the robot should fall back to safe local behaviour when the backend is
unreachable, which is precisely the case where the backend hears nothing. So
``error`` is in the vocabulary, the firmware uses it, and ``resolve`` cannot
return it. ``tests/test_robot_modes.py`` asserts that, the way PRD 10 asserts
that nothing writes ``delivered``.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AssistantPreferences, Device
from app.models.enums import (
    ROBOT_FACE_STATES,
    ROBOT_PRESENTATION_MODES,
    SAFETY_EVENT_AWAITING_RESPONSE_STATUSES,
    SAFETY_EVENT_EMERGENCY_STATUSES,
)
from app.services import devices as device_service
from app.services.safety import events as safety_events

logger = logging.getLogger(__name__)

#: PRD 8's four modes, as the robot's names for them (section 4).
ASSISTANT_MODE_TO_ROBOT: dict[str, str] = {
    "normal": "companion",
    "focus": "focus",
    "sleep": "sleep",
    "privacy": "privacy",
}

#: Which face belongs to a mode (sections 27 and 83). ``None`` means *no face*:
#: the mode shows information instead, which is section 7's serious mode and
#: section 28's rule that expression must never carry a health judgement.
MODE_FACES: dict[str, str | None] = {
    "companion": "idle",
    # A card is on the screen; the face is not what is being shown.
    "information": None,
    # Section 32: minimal motion, no casual prompts, but still Nura.
    "focus": "idle",
    "sleep": "sleeping",
    "privacy": "privacy",
    # Sections 7 and 9: a safety prompt is information, never a face.
    "safety": None,
    "emergency": None,
    "offline": "offline",
    "setup": None,
    "error": None,
}
assert set(MODE_FACES) == set(ROBOT_PRESENTATION_MODES)
assert all(face is None or face in ROBOT_FACE_STATES for face in MODE_FACES.values())


@dataclass(frozen=True)
class RobotMode:
    """The mode, and the facts it was worked out from.

    The inputs are returned alongside the answer because the settings screen
    shows them: "Offline" with nothing to explain it is the kind of status that
    makes somebody restart a working robot.
    """

    mode: str
    face: str | None
    connection_status: str
    setup_complete: bool
    #: PRD 10: escalation is live. Section 8's display state.
    emergency: bool
    #: PRD 10: a check-in is waiting for an answer. Section 9.
    safety_check: bool
    #: PRD 8's stored mode, before anything overrode it.
    assistant_mode: str

    def __post_init__(self) -> None:
        assert self.mode in ROBOT_PRESENTATION_MODES, self.mode


def assistant_mode_for(db: Session, profile_id: uuid.UUID | None) -> str:
    """PRD 8's stored mode, defaulting to ``normal`` for a profile with none."""
    if profile_id is None:
        return "normal"
    row = db.execute(
        select(AssistantPreferences).where(AssistantPreferences.profile_id == profile_id)
    ).scalar_one_or_none()
    return row.mode if row is not None else "normal"


def resolve(
    db: Session,
    device: Device,
    now: datetime,
    *,
    assume_online: bool = False,
    showing_card: bool = False,
) -> RobotMode:
    """The mode this robot is in (section 4).

    ``assume_online`` is set on the device's own requests. A robot that is
    asking for its next presentation is, by definition, reachable -- answering
    it with ``offline`` because its last heartbeat was ninety seconds ago would
    be the backend disagreeing with the request in its hands.

    ``showing_card`` is set when something other than a face is queued, which
    is what makes section 6's ``information`` mode a consequence of the queue
    rather than a separate state somebody has to remember to leave.

    The order is the whole rule, and it is the one the PRD states in four
    separate sections: emergency, then a safety prompt, then setup, then
    connectivity, then whatever the person chose.
    """
    connection = (
        "online" if assume_online else device_service.connection_status(device, now)
    )
    setup_complete = device.setup_completed_at is not None
    profile_id = device.owner_profile_id

    event = None if profile_id is None else safety_events.active_event(db, profile_id)
    emergency = event is not None and event.status in SAFETY_EVENT_EMERGENCY_STATUSES
    checking = (
        event is not None and event.status in SAFETY_EVENT_AWAITING_RESPONSE_STATUSES
    )
    assistant_mode = assistant_mode_for(db, profile_id)

    if emergency:
        mode = "emergency"
    elif checking:
        mode = "safety"
    elif not setup_complete:
        mode = "setup"
    elif connection != "online":
        mode = "offline"
    elif assistant_mode in {"sleep", "privacy", "focus"}:
        mode = ASSISTANT_MODE_TO_ROBOT[assistant_mode]
    elif showing_card:
        mode = "information"
    else:
        mode = "companion"

    return RobotMode(
        mode=mode,
        face=MODE_FACES[mode],
        connection_status=connection,
        setup_complete=setup_complete,
        emergency=emergency,
        safety_check=checking,
        assistant_mode=assistant_mode,
    )


def accepts_ordinary_cards(mode: str) -> bool:
    """Whether a reminder or a message should be put in front of somebody now.

    Sleep and privacy suppress non-critical activity (sections 31 and 33), and
    they are the only two: both are things a person chose, meaning "do not put
    things in front of me now". Focus suppresses casual prompts but not
    relevant information (section 32), so a reminder still goes through.

    ``offline`` and ``error`` are deliberately **not** suppressions. They are
    facts about connectivity, and sections 20 and 99 are explicit that a
    useful unexpired presentation stays queued for a robot that is not there --
    so it is waiting when the robot comes back. Treating offline as a
    suppression would quietly lose every card queued while a robot was
    unplugged.

    Which of those two a presentation counts as depends on its type, so this
    answers the mode half and ``queue.queue`` takes the type into account.
    """
    return mode not in {"sleep", "privacy"}


def suppresses_audio(mode: str) -> bool:
    """Section 82, and section 33's "suppress read-aloud" in privacy mode."""
    return mode in {"sleep", "privacy", "focus", "offline", "error"}
