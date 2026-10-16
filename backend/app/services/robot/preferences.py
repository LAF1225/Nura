"""How one robot should behave, including before it can behave at all.

PRD 11, sections 22, 30, 43, 44, 45, 46, 48, 49, 103, 104 and 105.

**Preferences exist before the hardware does.** Section 49 is explicit: a
person may say "when the speaker works, do not read my messages out", and the
setting is kept without implying that the speaker works. So this module never
consults the capability map -- a preference is what somebody asked for, and
whether it can be honoured is a separate question asked separately
(``capabilities``). Keeping them apart is what lets the settings screen say
"Not available on this device" next to a switch that still remembers its
position.

**Reduced motion follows the person by default.** Sections 30 and 105 ask the
robot to default to reduced motion when the account's accessibility preference
is set. ``reduced_motion`` is therefore nullable: null means follow, true and
false are deliberate overrides. A plain boolean would have had to pick a value
the first time the screen was opened, and would have stopped following the
accessibility setting from then on without anybody noticing.

**The defaults are the conservative ones.** Section 104: medication previews
start private, all three read-aloud switches start off, the sleep screen dims.
Nothing starts in the state that would say the most out loud in a room.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, DevicePresentationPreferences, UserSettings
from app.models.enums import (
    ROBOT_MEDICATION_PRIVACY_LEVELS,
    ROBOT_PRIVACY_LEVELS,
    ROBOT_SLEEP_SCREEN_MODES,
)
from app.services.errors import DomainError
from app.services.robot import layouts

logger = logging.getLogger(__name__)

#: Section 104, in one place so the migration's server defaults, the model and
#: this module cannot drift. The model carries the same values as server
#: defaults, and ``tests/test_models.py`` asserts the two agree.
DEFAULTS: dict[str, Any] = {
    "brightness": 70,
    "volume": 40,
    "reduced_motion": None,
    "medication_privacy_level": "private",
    "read_medications_aloud": False,
    "read_messages_aloud": False,
    "read_assistant_aloud": False,
    "sleep_screen_mode": "dim",
    "face_animation_enabled": True,
    "family_message_display_enabled": True,
    # PRD 12, section 32. ``full`` rather than ``private``, which is a
    # different answer from the medication default and a deliberate one: "Call
    # the physiotherapist" on a shelf is a note to self, and hiding it by
    # default would make the robot useless for the thing PRD 12 is for.
    # Somebody with a task they would rather not have read over their shoulder
    # sets one of the other two, and the builders apply it exactly as the
    # medication builder does.
    "daily_life_privacy_level": "full",
    # PRD 12, section 31's additive principle as a switch. Off means no task,
    # reminder, alarm or routine card is ever queued -- and every one of them
    # still works, because nothing about a daily-life item depends on the
    # robot.
    "daily_life_display_enabled": True,
}

#: Discrete steps the app offers for brightness and volume (sections 44 and
#: 45). The column stores 0-100 so a future slider needs no migration; the app
#: offers five steps because five is enough to be useful on a device nobody can
#: see yet, and because a slider for a screen that does not exist is a control
#: pretending to do something.
LEVELS = (0, 25, 50, 75, 100)

WRITABLE = tuple(DEFAULTS)


class InvalidPreferenceError(DomainError):
    """A value outside what the column allows. Caught before the database."""

    status_code = 422
    code = "invalid_preference"


@dataclass(frozen=True)
class EffectivePreferences:
    """What the robot should actually do, with the defaults resolved.

    Separate from the row because ``reduced_motion`` is a different thing in
    the two places: on the row it is a three-state answer to "has anybody
    chosen?", and here it is the boolean the firmware needs.
    """

    brightness: int
    volume: int
    reduced_motion: bool
    #: Whether the *account* asked for reduced motion, which is what makes the
    #: settings screen able to say "following your accessibility setting"
    #: rather than silently showing a value nobody set.
    reduced_motion_follows_account: bool
    medication_privacy_level: str
    read_medications_aloud: bool
    read_messages_aloud: bool
    read_assistant_aloud: bool
    sleep_screen_mode: str
    face_animation_enabled: bool
    family_message_display_enabled: bool
    daily_life_privacy_level: str
    daily_life_display_enabled: bool


def account_reduce_motion(db: Session, device: Device) -> bool:
    """The account's own accessibility preference (section 105).

    Read through the claiming account rather than the profile: ``reduce_motion``
    is a property of how somebody uses their phone, and it lives on
    ``user_settings`` where PRD 1 put it.
    """
    if device.claimed_by_account_id is None:
        return False
    settings = db.execute(
        select(UserSettings).where(UserSettings.user_id == device.claimed_by_account_id)
    ).scalar_one_or_none()
    return bool(settings is not None and settings.reduce_motion)


def get_or_create(
    db: Session, device: Device, now: datetime
) -> DevicePresentationPreferences:
    """This robot's preferences, created with the conservative defaults.

    Created on first read rather than at claim time, so a robot claimed by an
    older build still gets a row the first time anybody opens its settings --
    the same read-replenishes-state shape PRD 5 uses for doses and PRD 10 uses
    for monitoring expiry.
    """
    row = db.execute(
        select(DevicePresentationPreferences).where(
            DevicePresentationPreferences.device_id == device.id
        )
    ).scalar_one_or_none()
    if row is not None:
        if row.profile_id is None and device.owner_profile_id is not None:
            # The robot was claimed before it was linked to anybody.
            row.profile_id = device.owner_profile_id
            db.flush()
        return row

    row = DevicePresentationPreferences(
        device_id=device.id,
        profile_id=device.owner_profile_id,
        **{key: value for key, value in DEFAULTS.items()},
    )
    db.add(row)
    db.flush()
    logger.info("robot.preferences created for a device")
    return row


def update(
    db: Session,
    preferences: DevicePresentationPreferences,
    changes: dict[str, Any],
    now: datetime,
) -> DevicePresentationPreferences:
    """Applies a partial change, validating every value first.

    Validated here as well as in the schema because the seed script, the
    simulator and any future job all come through this function, and a range
    that is only enforced by pydantic is a range the database has to catch.
    """
    for key, value in changes.items():
        if key not in WRITABLE:
            raise InvalidPreferenceError("That preference is not recognised.")
        _check(key, value)
    for key, value in changes.items():
        setattr(preferences, key, value)
    db.flush()
    # Section 68: the event is generic and names no value.
    logger.info("robot.preference_changed count=%d", len(changes))
    return preferences


def _check(key: str, value: Any) -> None:
    if key in {"brightness", "volume"}:
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidPreferenceError("That value must be a whole number.")
        if not 0 <= value <= 100:
            raise InvalidPreferenceError("That value must be between 0 and 100.")
        return
    if key == "reduced_motion":
        if value is not None and not isinstance(value, bool):
            raise InvalidPreferenceError("That value must be on, off or unset.")
        return
    if key == "medication_privacy_level":
        if value not in ROBOT_MEDICATION_PRIVACY_LEVELS:
            raise InvalidPreferenceError("That privacy level is not recognised.")
        return
    if key == "daily_life_privacy_level":
        if value not in ROBOT_PRIVACY_LEVELS:
            raise InvalidPreferenceError("That privacy level is not recognised.")
        return
    if key == "sleep_screen_mode":
        if value not in ROBOT_SLEEP_SCREEN_MODES:
            raise InvalidPreferenceError("That sleep setting is not recognised.")
        return
    if not isinstance(value, bool):
        raise InvalidPreferenceError("That value must be on or off.")


def effective(
    db: Session, device: Device, preferences: DevicePresentationPreferences
) -> EffectivePreferences:
    """The preferences with ``reduced_motion`` resolved (sections 30 and 105)."""
    follows = preferences.reduced_motion is None
    reduced = (
        account_reduce_motion(db, device) if follows else bool(preferences.reduced_motion)
    )
    return EffectivePreferences(
        brightness=preferences.brightness,
        volume=preferences.volume,
        reduced_motion=reduced,
        reduced_motion_follows_account=follows,
        medication_privacy_level=preferences.medication_privacy_level,
        read_medications_aloud=preferences.read_medications_aloud,
        read_messages_aloud=preferences.read_messages_aloud,
        read_assistant_aloud=preferences.read_assistant_aloud,
        sleep_screen_mode=preferences.sleep_screen_mode,
        face_animation_enabled=preferences.face_animation_enabled,
        family_message_display_enabled=preferences.family_message_display_enabled,
        daily_life_privacy_level=preferences.daily_life_privacy_level,
        daily_life_display_enabled=preferences.daily_life_display_enabled,
    )


def device_settings(resolved: EffectivePreferences) -> layouts.DeviceSettings:
    """The block that travels with every envelope.

    Face animation is reported as off whenever reduced motion is on, so the
    firmware has one field to read rather than a rule to remember -- section
    29's "no important information may be conveyed only through animation"
    is easier to keep when the device is simply told not to animate.
    """
    return layouts.DeviceSettings(
        brightness=resolved.brightness,
        volume=resolved.volume,
        reduced_motion=resolved.reduced_motion,
        face_animation=resolved.face_animation_enabled and not resolved.reduced_motion,
        sleep_screen=resolved.sleep_screen_mode,
    )


def resolved_for(
    db: Session, device: Device, now: datetime
) -> tuple[DevicePresentationPreferences, EffectivePreferences]:
    """Both forms at once, which is what every caller actually needs."""
    row = get_or_create(db, device, now)
    return row, effective(db, device, row)
