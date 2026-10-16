"""The presentation envelope, the eight layouts, and the limits.

PRD 11, sections 37, 38, 77, 78, 85, 86, 87, 108, 111, 112 and 116.

This module is the wire contract. ``docs/device/presentation-protocol.md``
writes it up for a firmware author; the firmware mirrors the same vocabulary in
``presentation_protocol.h``; and ``tests/test_robot_protocol.py`` reads that
header to prove the three have not drifted.

**A layout is a name from a closed set, not a description of a screen.**
Section 111 rules out rendering markup, and section 37 rules out "arbitrary
HTML-like layouts". So a payload says ``REMINDER`` and fills in four short
fields; the firmware decides what a reminder looks like. A backend that wanted
a new arrangement has to add a layout here *and* in the firmware, which is the
intended cost.

**Text is data and can never become structure.** Section 112: a family message
that happens to contain ``{"layout": "EMERGENCY"}`` is a string in a field, and
stays one -- the envelope is built from typed fields and serialised once, so
there is no place for message text to be interpreted. Control characters are
stripped on the way in, because a terminal-style display driver is exactly the
kind of thing that would act on them.

**Nothing is clipped by accident.** Section 77 asks for safe shortening rather
than relying on a screen running out of pixels. ``shorten`` cuts at a word
boundary and marks the payload ``truncated``, which is what lets section 78's
"Open the Nura app to read more." appear only when there is more to read.

**The envelope carries the device's own settings.** Brightness, volume,
reduced motion and the face-animation preference travel with each
presentation, so a robot that has just woken up draws the current preferences
without a second request -- and so a preference change takes effect on the
next thing shown. Sections 44, 45 and 30.
"""

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.enums import (
    ROBOT_CHIME_KINDS,
    ROBOT_FACE_STATES,
    ROBOT_PRESENTATION_ACTIONS,
    ROBOT_PRESENTATION_LAYOUTS,
    ROBOT_PRESENTATION_PROTOCOL_VERSION,
)

#: Section 116. A device that does not recognise this refuses the envelope.
PROTOCOL_VERSION = ROBOT_PRESENTATION_PROTOCOL_VERSION

#: Section 77's limits, in characters, chosen for a 240x320 screen at the text
#: sizes ``display.cpp`` already uses. They are generous enough that ordinary
#: content is never shortened and small enough that nothing can push a layout
#: off the panel.
TITLE_MAX = 24
PRIMARY_MAX = 32
SECONDARY_MAX = 48
BODY_MAX = 140
#: A message preview. Section 78: a long message shows its beginning and sends
#: the reader to the app, rather than scrolling for a minute on a desk.
MESSAGE_MAX = 90
#: One line of a STATUS or EMERGENCY card.
LINE_MAX = 48
#: At most this many lines. Section 8's emergency example has four.
MAX_LINES = 5
CODE_MAX = 8

#: The fields each layout uses. Required first, then optional -- and a payload
#: carrying anything not listed here is refused rather than passed on, so a
#: future field cannot reach a device that has no idea what to do with it.
LAYOUT_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # the canonical face (sections 5, 27)
    "FACE": (("face_state",), ()),
    # a heading and a sentence (section 6)
    "TITLE_BODY": (("title", "body"), ()),
    # a heading and one short value, e.g. a time
    "TITLE_VALUE": (("title", "value"), ()),
    # medication and appointment reminders (sections 21, 23)
    "REMINDER": (("title", "primary"), ("secondary", "prompt")),
    # a family message (section 24)
    "MESSAGE": (("title", "body"), ("sender",)),
    # safety status, system status (sections 9, 36)
    "STATUS": (("title", "lines"), ()),
    # emergency (section 8)
    "EMERGENCY": (("title", "lines"), ()),
    # PRD 2's pairing code (section 35)
    "PAIRING_CODE": (("title", "code"), ()),
}
assert set(LAYOUT_FIELDS) == set(ROBOT_PRESENTATION_LAYOUTS)

#: Fields any layout may carry, because they are about *how* to show it rather
#: than what it says.
COMMON_FIELDS: tuple[str, ...] = (
    # Section 7: no face, no animation, high contrast.
    "serious",
    # Section 67: this payload should not be quoted into a log or a preview.
    "sensitive",
    # Section 77: there was more text than fitted.
    "truncated",
    # Sections 78 and 79: the rest is in the app.
    "continue_in_app",
    # Section 85: what the card offers, if the device has any input.
    "actions",
    # Sections 25, 43 and 82: may this be read aloud, if a speaker exists?
    "speak",
    # Section 81: which chime, if any audio exists.
    "chime",
    # Section 86: the device has no input, so the card says where to answer.
    "respond_in_app",
)

#: Which fields hold free text, and how long each may be. Everything not here
#: is a bool, a list of enum values, or a short code.
TEXT_LIMITS: dict[str, int] = {
    "title": TITLE_MAX,
    "primary": PRIMARY_MAX,
    "secondary": SECONDARY_MAX,
    "prompt": PRIMARY_MAX,
    "body": BODY_MAX,
    "value": PRIMARY_MAX,
    "sender": PRIMARY_MAX,
    "code": CODE_MAX,
}


class PayloadError(ValueError):
    """A payload that does not fit the protocol. Never shown to a user."""


# --- text handling -----------------------------------------------------------


def sanitize(text: str) -> str:
    """Plain text, with anything a display driver might act on removed.

    Section 112. Control characters (including the ones a serial display would
    read as commands), zero-width marks and newlines all go; runs of
    whitespace collapse to one space. What comes back is a single line of
    printable text, which is the only thing any layout field holds.
    """
    cleaned = []
    for character in text:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Zl", "Zp"}:
            # Keep the word boundary a newline or a tab represented.
            cleaned.append(" ")
            continue
        cleaned.append(character)
    return " ".join("".join(cleaned).split())


def shorten(text: str, limit: int) -> tuple[str, bool]:
    """Text within ``limit``, cut at a word boundary, and whether it was cut.

    Section 77: *do not rely on accidental clipping*. The ellipsis is part of
    the budget, and the cut happens at the last space so a reminder never ends
    mid-word. Returns the flag as well as the text, because the caller needs it
    to decide whether to add "Open the Nura app to read more."
    """
    clean = sanitize(text)
    if len(clean) <= limit:
        return clean, False
    if limit <= 1:
        return "…", True
    head = clean[: limit - 1]
    spaced = head.rsplit(" ", 1)[0]
    # A single very long word has no boundary to cut at; take the hard cut.
    if len(spaced) < limit // 2:
        spaced = head
    return spaced.rstrip(" ,.;:") + "…", True


# --- payloads ----------------------------------------------------------------


def build_payload(layout: str, **fields: Any) -> dict[str, Any]:
    """A validated payload for one layout.

    Every field is shortened to its limit and sanitised on the way in, so the
    stored payload is already exactly what the device will draw -- there is no
    second, looser path where a longer string could reach a screen. Fields
    passed as ``None`` are dropped rather than stored as null, which keeps the
    envelope small (section 108).
    """
    if layout not in LAYOUT_FIELDS:
        raise PayloadError(f"unknown layout {layout!r}")
    required, optional = LAYOUT_FIELDS[layout]
    allowed = set(required) | set(optional) | set(COMMON_FIELDS)

    payload: dict[str, Any] = {}
    truncated = False
    for key, value in fields.items():
        if key not in allowed:
            raise PayloadError(f"{layout} has no field {key!r}")
        if value is None:
            continue
        if key in TEXT_LIMITS:
            if not isinstance(value, str):
                raise PayloadError(f"{key} must be text")
            shortened, was_cut = shorten(value, TEXT_LIMITS[key])
            if not shortened:
                continue
            payload[key] = shortened
            truncated = truncated or was_cut
        elif key == "lines":
            payload[key] = _lines(value)
        elif key == "actions":
            payload[key] = _actions(value)
        elif key == "face_state":
            if value not in ROBOT_FACE_STATES:
                raise PayloadError(f"unknown face state {value!r}")
            payload[key] = value
        elif key == "chime":
            if value not in ROBOT_CHIME_KINDS:
                raise PayloadError(f"unknown chime {value!r}")
            payload[key] = value
        elif isinstance(value, bool):
            payload[key] = value
        else:
            raise PayloadError(f"{key} must be a boolean")

    missing = [key for key in required if key not in payload]
    if missing:
        raise PayloadError(f"{layout} needs {', '.join(missing)}")

    if truncated:
        payload["truncated"] = True
    return payload


def _lines(value: Any) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise PayloadError("lines must be a list of strings")
    if len(value) > MAX_LINES:
        raise PayloadError(f"at most {MAX_LINES} lines")
    out = []
    for line in value:
        if not isinstance(line, str):
            raise PayloadError("lines must be a list of strings")
        text, _ = shorten(line, LINE_MAX)
        if text:
            out.append(text)
    if not out:
        raise PayloadError("lines must not be empty")
    return out


def _actions(value: Any) -> list[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise PayloadError("actions must be a list")
    out = []
    for action in value:
        if action not in ROBOT_PRESENTATION_ACTIONS:
            raise PayloadError(f"unknown action {action!r}")
        if action not in out:
            out.append(action)
    return out


def validate_payload(layout: str, payload: dict[str, Any]) -> None:
    """Re-checks a stored payload against the protocol.

    Used when an envelope is handed to a device, so a row written by an older
    build cannot be sent as if it were valid. Cheap enough to do on every
    fetch, and it means ``device_presentations`` is not trusted blindly just
    because the rows are ours.
    """
    build_payload(layout, **payload)


def without_sensitive_text(payload: dict[str, Any]) -> dict[str, Any]:
    """The payload with its free text removed, for logs and diagnostics.

    Section 67: medication names, message text, assistant replies and safety
    content may all be sensitive, so what is logged is the shape -- the layout,
    the flags, which fields were present -- and never the words.
    """
    return {
        "layout": payload.get("layout"),
        "fields": sorted(key for key in payload if key not in {"layout"}),
        "sensitive": bool(payload.get("sensitive")),
        "truncated": bool(payload.get("truncated")),
        "actions": payload.get("actions", []),
    }


# --- envelopes ---------------------------------------------------------------


@dataclass(frozen=True)
class DeviceSettings:
    """The preferences that travel with every envelope.

    Here rather than on a separate endpoint so a robot that reconnects after a
    week draws the right brightness on the first card it shows, and so there is
    no window in which the device is rendering with settings somebody changed
    yesterday.
    """

    brightness: int
    volume: int
    reduced_motion: bool
    face_animation: bool
    sleep_screen: str

    def as_json(self) -> dict[str, Any]:
        return {
            "brightness": self.brightness,
            "volume": self.volume,
            "reduced_motion": self.reduced_motion,
            "face_animation": self.face_animation,
            "sleep_screen": self.sleep_screen,
        }


def build_envelope(
    *,
    presentation_id: str,
    presentation_type: str,
    priority: int,
    layout: str,
    payload: dict[str, Any],
    mode: str,
    expires_at: datetime | None,
    settings: DeviceSettings,
    protocol_version: int = PROTOCOL_VERSION,
) -> dict[str, Any]:
    """What a device is actually sent (sections 38, 108 and 116).

    Small on purpose: an id, what kind of thing it is, how to draw it, when it
    stops being worth drawing, and the settings to draw it with. No media, no
    URLs, no identifiers from the health record -- the id is the presentation's
    own, so a device that logs it has logged nothing about a person.
    """
    validate_payload(layout, payload)
    envelope: dict[str, Any] = {
        "protocol_version": protocol_version,
        "presentation_id": presentation_id,
        "type": presentation_type,
        "priority": priority,
        "mode": mode,
        "layout": layout,
        "payload": payload,
        "settings": settings.as_json(),
    }
    if expires_at is not None:
        envelope["expires_at"] = expires_at.isoformat()
    return envelope
