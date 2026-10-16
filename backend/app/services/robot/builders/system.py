"""The face, and the two cards that are about the robot itself.

PRD 11, sections 5, 29, 30, 31, 34, 35, 36, 83, 84 and 109.

**The idle face is a presentation like any other.** That is the design decision
worth noticing. Section 83 says the robot shows the companion face when the
queue is empty, and section 84 says a temporary card returns to the previous
valid mode afterwards. Both of those are free if the face is itself the
lowest-priority item in the queue: a reminder outranks it, the reminder's
render marks the face card completed, and the next reconciliation queues the
face again. Nothing has to remember to go back.

**No avatar assets.** Section 109: the face is code-driven, so what travels is
a face name from a nine-value vocabulary and nothing else. Section 108's
"state ID + text + minimal parameters" is the whole payload.

**``setup_code`` has no builder here, deliberately.** Section 35 says to reuse
PRD 2's pairing flow and not to create a second pairing mechanism. PRD 2's
pairing code is generated on the robot and drawn by the robot, over BLE, before
any device record exists -- so routing it through a backend queue would *be*
the second mechanism. The type and the ``PAIRING_CODE`` layout exist in the
protocol so the firmware's dispatch and the simulator cover them, and
``tests/test_robot_builders.py`` asserts that nothing in this package queues
one. It is the same kind of deliberate absence as PRD 10's ``delivered``.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Device, DevicePresentation
from app.services.robot import layouts, modes, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "system"
FACE_TYPE = "face_state"
STATUS_TYPE = "system_status"


def ensure_face(
    db: Session,
    device: Device,
    now: datetime,
    mode: modes.RobotMode,
) -> DevicePresentation | None:
    """Keeps the right face queued, and only the right one (section 83).

    Returns ``None`` when this mode shows information instead of a face --
    which is sections 7 and 28: a safety prompt, an emergency and a serious
    reply are never accompanied by an expression.
    """
    face = mode.face
    open_faces = [
        row
        for row in queue.open_presentations(db, device.id)
        if row.presentation_type == FACE_TYPE
    ]

    if face is None:
        for row in open_faces:
            queue.cancel(db, row, reason="superseded", now=now)
        return None

    for row in open_faces:
        if row.payload.get("face_state") != face:
            queue.cancel(db, row, reason="superseded", now=now)

    payload = layouts.build_payload(
        "FACE",
        face_state=face,
        # The face carries nothing private, which is what lets the app's
        # presentation history show it in full (section 96).
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=FACE_TYPE,
        layout="FACE",
        payload=payload,
        source=SOURCE,
        source_id=face,
        # A face needs a screen but not text: a robot that can light pixels
        # and not render a font can still show two eyes.
        requires=("display",),
        # The one repeatable presentation. A face is a state the robot returns
        # to, not an occasion that happened once -- see ``queue``.
        repeatable=True,
    )
    return queue.queue(db, device, request, now, mode=mode)


def queue_setup_prompt(
    db: Session, device: Device, now: datetime, mode: modes.RobotMode
) -> DevicePresentation | None:
    """ "Finish setting up in the Nura app", for a robot that is half linked.

    The case this covers is real and PRD 2 left it visible: a robot can be
    claimed, online and heartbeating before anybody has pressed Continue in
    the app, and until they do it has nothing to say. No pairing code is
    involved, which is what keeps section 35 satisfied.
    """
    if mode.mode != "setup":
        return None
    payload = layouts.build_payload(
        "TITLE_BODY",
        title=wording.SETUP_TITLE,
        body=wording.SETUP_BODY,
        sensitive=False,
    )
    request = queue.PresentationRequest(
        presentation_type=STATUS_TYPE,
        layout="TITLE_BODY",
        payload=payload,
        source=SOURCE,
        source_id="setup",
        repeatable=True,
    )
    return queue.queue(db, device, request, now, mode=mode)
