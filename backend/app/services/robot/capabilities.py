"""What the robot says it can do, and what follows from that.

PRD 11, sections 10, 11, 12, 47, 61, 86, 87, 90, 91, 92 and 124.

**Twelve keys, not one boolean.** Section 10 rules out a generic
``robot_ready``, and the reason shows up immediately in the settings screen: a
display that works and a speaker nobody has wired are different facts, and one
flag is how a screen comes to offer volume controls for a speaker that does
not exist.

**Only a device can say ``not_verified``.** Section 12's point is that a
compiled driver is not a working one. The backend cannot tell the difference --
it has never seen the build -- so it never writes that state. What the backend
knows is whether a robot has told it anything, and when the answer is no the
honest state is ``not_connected``: *nothing has been reported*. Sections 91 and
92 then put ``not_verified`` where it belongs, in the device's own self-test
result.

**A report goes stale when the firmware changes.** Section 124 asks for stale
reports to be handled, and the useful definition is not "old": it is "proven by
a build that is no longer running". A display that passed its self-test two
versions ago has not been proven by the version running now, so an
``available`` from an older firmware reads as ``not_verified`` until the robot
says so again. The stored row is never rewritten -- what the device said is
kept, and the downgrade is derived, which is the same arrangement every other
derived value in this codebase uses.

**Capability never widens by inference.** ``effective_state`` can only move a
state towards less certainty. There is no path that turns ``not_verified`` into
``available`` because something else looked fine.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, DeviceCapability
from app.models.enums import (
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_SOURCES,
    ROBOT_CAPABILITY_STATES,
)
from app.services.errors import DomainError

logger = logging.getLogger(__name__)

#: A report older than this is treated as unproven even if the firmware
#: version has not changed. Hardware is pulled apart on a workbench, and a
#: screen that was working a month ago is not evidence about today.
CAPABILITY_STALE_AFTER = timedelta(days=30)

#: What the app reads when a device has said nothing. Not ``unavailable``,
#: which would claim the part is absent, and not ``not_verified``, which would
#: claim a driver exists. Section 10's fourth state is exactly this case.
UNREPORTED_STATE = "not_connected"

#: The keys that have to be ``available`` before a card with words on it is
#: worth sending (sections 86 and 87).
TEXT_KEYS = ("display", "display_text")

#: Any of these being available means the Audio section has something to do
#: (sections 46 and 47).
AUDIO_KEYS = ("speaker", "audio_playback", "tts")

#: Section 86: with none of these, an action-heavy card becomes a card that
#: says to answer in the app.
INPUT_KEYS = ("buttons", "touch")


class UnknownCapabilityError(DomainError):
    """A device reported a key or state this build does not define."""

    status_code = 422
    code = "unknown_capability"


@dataclass(frozen=True)
class CapabilityView:
    """One capability as the app reads it.

    Both states are returned on purpose. ``reported_state`` is what the device
    said, which a developer needs; ``state`` is what this build is willing to
    act on, which is what a screen must use. When they differ, ``stale`` says
    why.
    """

    key: str
    state: str
    reported_state: str
    reported_at: datetime | None
    firmware_version: str | None
    source: str
    stale: bool

    def __post_init__(self) -> None:
        assert self.key in ROBOT_CAPABILITY_KEYS, self.key
        assert self.state in ROBOT_CAPABILITY_STATES, self.state
        assert self.reported_state in ROBOT_CAPABILITY_STATES, self.reported_state
        assert self.source in ROBOT_CAPABILITY_SOURCES, self.source


def effective_state(
    *,
    reported_state: str,
    reported_at: datetime,
    reported_firmware: str | None,
    device_firmware: str | None,
    now: datetime,
) -> tuple[str, bool]:
    """The state to act on, and whether the report is stale.

    Only ``available`` is ever downgraded, and only to ``not_verified``: the
    part is still there, and what has lapsed is the proof. Anything already
    short of ``available`` is left exactly as the device said it -- there is
    nothing to be more careful about.
    """
    firmware_moved = (
        reported_firmware is not None
        and device_firmware is not None
        and reported_firmware != device_firmware
    )
    aged = now - reported_at > CAPABILITY_STALE_AFTER
    stale = firmware_moved or aged
    if stale and reported_state == "available":
        return "not_verified", True
    return reported_state, stale


def report(
    db: Session,
    device: Device,
    states: dict[str, str],
    now: datetime,
    *,
    source: str = "device_report",
    firmware_version: str | None = None,
) -> tuple[CapabilityView, ...]:
    """Records what a device says about itself (section 61).

    A partial report is normal and does not erase the keys it leaves out: a
    robot that has just finished a display self-test reports the display, and
    saying nothing about its microphone is not a claim about the microphone.

    An unknown key or state is refused rather than ignored. A device inventing
    a capability is either a protocol mismatch or something worse, and both are
    worth a 422 the firmware author will see.
    """
    if not states:
        raise UnknownCapabilityError("No capabilities were reported.")
    for key, state in states.items():
        if key not in ROBOT_CAPABILITY_KEYS:
            raise UnknownCapabilityError("That capability is not recognised.")
        if state not in ROBOT_CAPABILITY_STATES:
            raise UnknownCapabilityError("That capability state is not recognised.")
    if source not in ROBOT_CAPABILITY_SOURCES:
        raise UnknownCapabilityError("That capability source is not recognised.")

    existing = {
        row.capability_key: row
        for row in db.execute(
            select(DeviceCapability).where(DeviceCapability.device_id == device.id)
        )
        .scalars()
        .all()
    }
    reported = firmware_version or device.firmware_version
    for key, state in states.items():
        row = existing.get(key)
        if row is None:
            row = DeviceCapability(
                device_id=device.id,
                capability_key=key,
                state=state,
                source=source,
                reported_at=now,
                firmware_version=reported,
            )
            db.add(row)
            existing[key] = row
            continue
        row.state = state
        row.source = source
        row.reported_at = now
        row.firmware_version = reported

    db.flush()
    # The capability keys are logged; the values are operational and not
    # sensitive, but the device id is not logged with them (section 68).
    logger.info("robot.capabilities reported keys=%d", len(states))
    return views(db, device, now)


def rows_for(db: Session, device_id: uuid.UUID) -> dict[str, DeviceCapability]:
    return {
        row.capability_key: row
        for row in db.execute(
            select(DeviceCapability).where(DeviceCapability.device_id == device_id)
        )
        .scalars()
        .all()
    }


def views(
    db: Session, device: Device | None, now: datetime
) -> tuple[CapabilityView, ...]:
    """All twelve capabilities, in their fixed order (section 10).

    Every key is returned even when nothing has been reported, for the reason
    PRD 10's capability map returns all seven: a client that only sees the keys
    that happen to be present is a client that silently stops asking about one
    somebody added.
    """
    stored = {} if device is None else rows_for(db, device.id)
    out = []
    for key in ROBOT_CAPABILITY_KEYS:
        row = stored.get(key)
        if row is None:
            out.append(
                CapabilityView(
                    key=key,
                    state=UNREPORTED_STATE,
                    reported_state=UNREPORTED_STATE,
                    reported_at=None,
                    firmware_version=None,
                    source="default",
                    stale=False,
                )
            )
            continue
        state, stale = effective_state(
            reported_state=row.state,
            reported_at=row.reported_at,
            reported_firmware=row.firmware_version,
            device_firmware=device.firmware_version if device else None,
            now=now,
        )
        out.append(
            CapabilityView(
                key=key,
                state=state,
                reported_state=row.state,
                reported_at=row.reported_at,
                firmware_version=row.firmware_version,
                source=row.source,
                stale=stale,
            )
        )
    return tuple(out)


def capability_map(db: Session, device: Device | None, now: datetime) -> dict[str, str]:
    """Key to effective state, which is what every decision below reads."""
    return {view.key: view.state for view in views(db, device, now)}


def _any_available(states: dict[str, str], keys: tuple[str, ...]) -> bool:
    return any(states.get(key) == "available" for key in keys)


def _all_available(states: dict[str, str], keys: tuple[str, ...]) -> bool:
    return all(states.get(key) == "available" for key in keys)


def can_show_text(states: dict[str, str]) -> bool:
    """Whether a card with words on it is worth queueing (section 87)."""
    return _all_available(states, TEXT_KEYS)


def can_animate(states: dict[str, str]) -> bool:
    return states.get("display_animation") == "available"


def has_audio(states: dict[str, str]) -> bool:
    """Whether the Audio settings section has anything behind it (section 47)."""
    return _any_available(states, AUDIO_KEYS)


def can_speak(states: dict[str, str]) -> bool:
    """Whether a payload may ask to be read aloud (sections 25, 42 and 43).

    Needs both a speaker and something able to turn words into sound. No
    deployment has either, which is why ``speak`` is false on every envelope
    this project has ever built.
    """
    return states.get("speaker") == "available" and states.get("tts") == "available"


def can_play_chime(states: dict[str, str]) -> bool:
    return _any_available(states, ("speaker", "audio_playback"))


def has_input(states: dict[str, str]) -> bool:
    """Section 86. False everywhere today, so cards say to answer in the app."""
    return _any_available(states, INPUT_KEYS)
