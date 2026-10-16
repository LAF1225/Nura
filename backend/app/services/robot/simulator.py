"""A robot that is not there.

PRD 11, sections 62, 63, 64, 85, 87, 98, 129, 131, 132 and 140.

Section 63 is unusually direct about why this exists: the robot is unfinished,
so the simulator is a **core verification surface, not optional polish**. Every
workflow PRD 11 requires has to be exercisable without hardware, and this is
what exercises it.

**It is a device, not a mock.** The simulated robot holds a capability set and
a render outcome, and then goes through the same services a real robot's HTTP
requests go through: report capabilities, fetch the next presentation,
acknowledge it. Nothing is stubbed out underneath it. A test that drives this
has driven the queue, the priority table, the preemption rule, the expiry
comparison and the acknowledgement state machine.

**It renders.** ``render`` turns an envelope into the lines a person would read
off the screen, dispatching on layout exactly as the firmware's
``card_renderer`` does. That mirror is the honest answer to section 131: the
firmware's own dispatch cannot be executed on a development machine, so the
same dispatch is implemented here, the layout vocabulary is checked against the
firmware header by ``tests/test_robot_protocol.py``, and the completion report
says plainly that simulator proof is not hardware proof (section 135).

**Offline means offline.** With ``online`` false, ``poll`` does not reach the
backend at all and the screen falls back to the local offline card -- which is
section 98's "safe local behaviour when the backend is unreachable", and the
reason section 20's "do not claim the robot displayed it" is easy to honour:
nothing is acknowledged, so nothing is marked displayed.

**It is never in production.** Section 62: no simulator controls in production
UI. This module is imported by tests, by ``scripts/robot_simulator.py`` and by
nothing in ``app.api``. ``tests/test_robot_simulator.py`` asserts that.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Device, DevicePresentation
from app.models.enums import ROBOT_ACK_STATES, ROBOT_CAPABILITY_STATES
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, presenter, queue, wording

logger = logging.getLogger(__name__)

#: A robot with a screen and nothing else, which is the most optimistic thing
#: this project has any right to simulate. Section 64's list starts here.
DISPLAY_ONLY: dict[str, str] = {
    "display": "available",
    "display_text": "available",
    "display_animation": "available",
    "speaker": "not_connected",
    "tts": "not_connected",
    "audio_playback": "not_connected",
    "microphone": "not_connected",
    "wake_word": "unavailable",
    "camera": "not_connected",
    "camera_detection": "unavailable",
    "buttons": "not_connected",
    "touch": "not_connected",
}

#: Section 12's case: the firmware has the driver and nothing has been proven.
#: What a real first build would honestly report.
UNVERIFIED_DISPLAY: dict[str, str] = {**DISPLAY_ONLY, "display": "not_verified"}

#: A robot with a screen and a working speaker. Nothing in this project has
#: ever produced this report; it exists so the audio settings and the
#: read-aloud preferences can be exercised (section 64).
WITH_SPEAKER: dict[str, str] = {
    **DISPLAY_ONLY,
    "speaker": "available",
    "audio_playback": "available",
    "tts": "available",
}

#: A robot with buttons, so section 85's action routing can be exercised.
WITH_BUTTONS: dict[str, str] = {**DISPLAY_ONLY, "buttons": "available"}

#: No screen at all. Section 123's "unsupported capability -> not_supported".
HEADLESS: dict[str, str] = dict.fromkeys(DISPLAY_ONLY, "unavailable")


@dataclass(frozen=True)
class Screen:
    """What a person standing in front of the robot would see.

    ``lines`` is the whole point: the test that matters is not "a row reached
    status displayed", it is "the screen said *Reminder due* and not the name
    of the tablet".
    """

    mode: str
    layout: str | None
    lines: tuple[str, ...]
    face: str | None = None
    presentation_id: str | None = None
    presentation_type: str | None = None
    #: Section 86: the card asked for an answer the robot cannot take.
    respond_in_app: bool = False
    #: Section 78/79: there is more in the app.
    continue_in_app: bool = False
    #: Section 7: drawn without a face and without decoration.
    serious: bool = False
    #: What the robot would have said aloud, if it could. Always empty in this
    #: project: no envelope has ever had ``speak`` set, because no capability
    #: report has ever included a speaker.
    spoken: tuple[str, ...] = ()
    brightness: int = 0
    reduced_motion: bool = False

    def text(self) -> str:
        return " / ".join(self.lines)


def render(envelope: dict[str, Any]) -> Screen:
    """An envelope, as a screen (sections 37 and 131).

    Dispatches on layout and on nothing else, which is section 111: there is no
    branch here that reads a text field and behaves differently, so a family
    message cannot change how it is drawn. An unknown layout is a refusal
    rather than a guess, and the firmware does the same thing -- reporting
    ``unsupported`` back to the backend.
    """
    version = envelope.get("protocol_version")
    if version != layouts.PROTOCOL_VERSION:
        # Section 116: fail safely rather than guessing at an envelope from a
        # newer backend.
        raise UnsupportedEnvelope(f"protocol version {version!r}")

    layout = envelope["layout"]
    payload = envelope["payload"]
    settings = envelope.get("settings", {})
    if layout not in layouts.LAYOUT_FIELDS:
        raise UnsupportedEnvelope(f"layout {layout!r}")

    lines = _lines_for(layout, payload)
    if payload.get("respond_in_app"):
        lines.append(wording.USE_THE_APP)
    if payload.get("continue_in_app"):
        lines.append(
            wording.MESSAGE_CONTINUE
            if layout == "MESSAGE"
            else wording.ASSISTANT_CONTINUE
        )

    return Screen(
        mode=str(envelope.get("mode", "companion")),
        layout=layout,
        lines=tuple(lines),
        face=payload.get("face_state"),
        presentation_id=str(envelope.get("presentation_id")),
        presentation_type=str(envelope.get("type")),
        respond_in_app=bool(payload.get("respond_in_app")),
        continue_in_app=bool(payload.get("continue_in_app")),
        serious=bool(payload.get("serious")),
        spoken=tuple(lines) if payload.get("speak") else (),
        brightness=int(settings.get("brightness", 0)),
        reduced_motion=bool(settings.get("reduced_motion")),
    )


class UnsupportedEnvelope(Exception):
    """The device cannot draw this. Reported as ``unsupported`` (section 19)."""


def _lines_for(layout: str, payload: dict[str, Any]) -> list[str]:
    """The firmware's dispatch table, in Python.

    Every layout in ``ROBOT_PRESENTATION_LAYOUTS`` has a branch, and
    ``tests/test_robot_simulator.py`` asserts that by rendering one of each.
    """
    if layout == "FACE":
        return [f"[{payload['face_state']}]"]
    if layout == "TITLE_BODY":
        return [payload["title"], payload["body"]]
    if layout == "TITLE_VALUE":
        return [payload["title"], payload["value"]]
    if layout == "REMINDER":
        lines = [payload["title"], payload["primary"]]
        if payload.get("secondary"):
            lines.append(payload["secondary"])
        if payload.get("prompt"):
            lines.append(payload["prompt"])
        return lines
    if layout == "MESSAGE":
        lines = [payload["title"]]
        if payload.get("sender"):
            lines.append(payload["sender"])
        lines.append(payload["body"])
        return lines
    if layout in {"STATUS", "EMERGENCY"}:
        return [payload["title"], *payload["lines"]]
    if layout == "PAIRING_CODE":
        return [payload["title"], wording.pairing_code_body(payload["code"])]
    raise UnsupportedEnvelope(f"layout {layout!r}")


@dataclass
class SimulatedRobot:
    """A Nura with whatever hardware the test says it has.

    ``render_outcome`` is section 64's render success / failure / unsupported
    switch: set it to ``failed`` and the backend records a failure, which is
    section 132's "simulate render failure, verify backend failed state".
    """

    db: Session
    device: Device
    online: bool = True
    #: What this robot reports after drawing. ``render_started`` is what a real
    #: device reports for a card it keeps on the screen, and it is the default
    #: for that reason; the backend finishes a displayed card when a later one
    #: replaces it. ``render_completed`` models a device that showed something
    #: and is done with it, and ``failed``/``unsupported`` are section 64's
    #: render-failure switches.
    render_outcome: str = "render_started"
    capability_states: dict[str, str] = field(default_factory=lambda: dict(DISPLAY_ONLY))
    #: Everything the screen has shown, most recent last. The simulator's own
    #: record, which is what a queue/preemption test reads.
    shown: list[Screen] = field(default_factory=list)
    _current: Screen | None = None

    def __post_init__(self) -> None:
        assert self.render_outcome in ROBOT_ACK_STATES, self.render_outcome
        for state in self.capability_states.values():
            assert state in ROBOT_CAPABILITY_STATES, state

    # --- what the robot is --------------------------------------------------

    def connect(self, now: datetime) -> None:
        """A heartbeat and a capability report, which is a robot booting."""
        self.online = True
        self.device.last_seen_at = now
        self.report_capabilities(now)
        self.db.flush()

    def go_offline(self) -> None:
        """Section 64. The robot stops answering; nothing is acknowledged."""
        self.online = False

    def report_capabilities(self, now: datetime) -> None:
        """Section 61, through the same service the endpoint uses."""
        capability_service.report(
            self.db,
            self.device,
            dict(self.capability_states),
            now,
            firmware_version=self.device.firmware_version,
        )
        self.db.flush()

    def set_capability(self, key: str, state: str, now: datetime) -> None:
        self.capability_states[key] = state
        capability_service.report(self.db, self.device, {key: state}, now)
        self.db.flush()

    def use(self, states: dict[str, str], now: datetime) -> None:
        """Swaps the whole hardware set, e.g. ``simulator.HEADLESS``."""
        self.capability_states = dict(states)
        self.report_capabilities(now)

    # --- what the robot does ------------------------------------------------

    def poll(self, now: datetime) -> Screen | None:
        """One fetch-render-acknowledge cycle (sections 19 and 58).

        Returns the screen it drew, or ``None`` when there was nothing to
        draw. An offline robot does not reach the backend at all: it keeps
        showing its own local offline card, and nothing in
        ``device_presentations`` moves -- which is exactly why section 20's
        rule is easy to keep.
        """
        if not self.online:
            self._current = Screen(
                mode="offline",
                layout="TITLE_BODY",
                lines=(wording.OFFLINE_TITLE, wording.OFFLINE_BODY),
            )
            return self._current

        self.device.last_seen_at = now
        presenter.refresh(self.db, self.device, now, assume_online=True)
        row = queue.next_for_device(self.db, self.device, now)
        if row is None:
            return None

        envelope = queue.envelope_for(self.db, self.device, row, now)
        queue.acknowledge(self.db, row, "received", now)
        try:
            screen = render(envelope)
        except UnsupportedEnvelope as error:
            queue.acknowledge(
                self.db, row, "unsupported", now, failure_code="unsupported_layout"
            )
            self.db.flush()
            logger.info("simulator: refused an envelope (%s)", error)
            return None

        if self.render_outcome == "failed":
            queue.acknowledge(self.db, row, "failed", now, failure_code="render_failed")
            self.db.flush()
            return None
        if self.render_outcome == "unsupported":
            queue.acknowledge(
                self.db, row, "unsupported", now, failure_code="unsupported_layout"
            )
            self.db.flush()
            return None

        queue.acknowledge(self.db, row, self.render_outcome, now)
        self.db.flush()
        self._current = screen
        self.shown.append(screen)
        return screen

    def drain(self, now: datetime, limit: int = 10) -> list[Screen]:
        """Polls until the queue is empty, which is what a robot does.

        Returns the screens in the order they were drawn, so a preemption test
        reads as "the message, then the emergency" rather than as a sequence of
        row statuses.
        """
        drawn = []
        for _ in range(limit):
            screen = self.poll(now)
            if screen is None:
                break
            drawn.append(screen)
        return drawn

    def screen(self) -> Screen | None:
        """What is on the screen now, as far as the robot is concerned."""
        return self._current

    def pending(self, now: datetime) -> list[DevicePresentation]:
        return queue.open_presentations(self.db, self.device.id)
