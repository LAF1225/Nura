"""The backend, the firmware and the protocol document agreeing.

PRD 11, sections 37, 38, 77, 108, 111, 112, 116, 117 and 131.

Section 131 asks for payload parsing, layout dispatch, ack generation,
capability serialisation, unsupported-layout handling and protocol-version
handling to be verified without hardware. The firmware's own unit tests do that
against the C++ (``firmware/xiao_esp32s3/test/test_presentation``), and they
run on the board -- so they have never been executed, because there is no
board.

What *can* be executed on a development machine is the thing a drift would
actually break: whether the three sides use the same vocabulary. This file
reads ``presentation_protocol.h`` and compares it with the backend's value
sets, so adding a layout, a face, an ack state or a capability on one side and
forgetting the other fails here rather than on a bench with a robot. The app
does the same from its side in
``mobile/tests/robotPresentationProtocol.test.ts``.

Parsed by hand rather than with a C++ parser, the way PRD 2's
``provisioningProtocol.test.ts`` reads ``protocol.h``: the shapes involved are
simple and this stays readable next to the header it mirrors.
"""

import re
from pathlib import Path

import pytest

from app.models.enums import (
    ROBOT_ACK_STATES,
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_STATES,
    ROBOT_CHIME_KINDS,
    ROBOT_FACE_STATES,
    ROBOT_PRESENTATION_FAILURE_CODES,
    ROBOT_PRESENTATION_LAYOUTS,
    ROBOT_PRESENTATION_PROTOCOL_VERSION,
    ROBOT_PRESENTATION_TYPES,
)
from app.services.robot import layouts

HEADER = (
    Path(__file__).resolve().parents[2]
    / "firmware"
    / "xiao_esp32s3"
    / "src"
    / "presentation_protocol.h"
)


@pytest.fixture(scope="module")
def header() -> str:
    assert HEADER.exists(), f"the firmware header is missing: {HEADER}"
    return HEADER.read_text(encoding="utf-8")


def string_constants(text: str) -> dict[str, str]:
    """``constexpr const char* NAME = "value";``"""
    pattern = re.compile(r'constexpr\s+const\s+char\*\s+(\w+)\s*=\s*"([^"]*)"\s*;')
    return {name: value for name, value in pattern.findall(text)}


def number_constants(text: str) -> dict[str, int]:
    """``constexpr <type> NAME = 123;``, decimal only."""
    pattern = re.compile(r"constexpr\s+\w+(?:\s+\w+)?\s+(\w+)\s*=\s*(\d+)\s*;")
    return {name: int(value) for name, value in pattern.findall(text)}


def enum_members(text: str, enum_name: str) -> list[str]:
    """The member names of ``enum class <name> : uint8_t { ... }``."""
    match = re.search(
        rf"enum\s+class\s+{enum_name}\s*:\s*uint8_t\s*\{{(.*?)\}};",
        text,
        re.DOTALL,
    )
    assert match is not None, f"no enum class {enum_name} in the header"
    return re.findall(r"^\s*(\w+)\s*=", match.group(1), re.MULTILINE)


# --- the version -------------------------------------------------------------


def test_the_protocol_version_matches(header):
    """Section 116. One version, in three places, and this is one of two
    tests that make the third place impossible to forget."""
    numbers = number_constants(header)
    assert numbers["PRESENTATION_PROTOCOL_VERSION"] == ROBOT_PRESENTATION_PROTOCOL_VERSION
    assert layouts.PROTOCOL_VERSION == ROBOT_PRESENTATION_PROTOCOL_VERSION


# --- the vocabularies --------------------------------------------------------


def test_the_firmware_knows_exactly_the_backends_layouts(header):
    """Section 37's closed set, on both sides.

    ``UNKNOWN`` is the firmware's own extra member: it is what an
    unrecognised layout name becomes, and it is how the device reports
    ``unsupported`` rather than drawing something close enough.
    """
    members = set(enum_members(header, "Layout")) - {"UNKNOWN"}
    assert members == set(ROBOT_PRESENTATION_LAYOUTS)

    names = string_constants(header)
    for layout in ROBOT_PRESENTATION_LAYOUTS:
        assert names[f"LAYOUT_NAME_{layout}"] == layout


def test_the_firmware_knows_exactly_the_backends_presentation_types(header):
    """PRD 11 section 15's types, and PRD 12 section 30's four new ones.

    The firmware does not dispatch on a type -- a card is drawn from its
    layout, which is what keeps the renderer's branch count equal to the number
    of shapes a screen can take. The names are mirrored for a log line that
    says what kind of card was handled without quoting its content, and for
    this test.

    **PRD 12 needed no firmware parser change**, and this is half the evidence:
    the four new types are here, and the layout set above is unchanged. A task,
    a reminder and an alarm are ``REMINDER``; a routine's progress is
    ``STATUS``. The other half is in ``test/test_presentation/test_main.cpp``,
    which parses one of each.
    """
    names = string_constants(header)
    for presentation_type in ROBOT_PRESENTATION_TYPES:
        key = f"TYPE_{presentation_type.upper()}"
        assert key in names, presentation_type
        assert names[key] == presentation_type

    mirrored = {value for key, value in names.items() if key.startswith("TYPE_")}
    assert mirrored == set(ROBOT_PRESENTATION_TYPES)


def test_the_firmware_knows_exactly_the_backends_face_states(header):
    """Section 27's nine, and section 28's reason for not having more."""
    members = {name.lower() for name in enum_members(header, "Face")}
    assert members == set(ROBOT_FACE_STATES)

    names = string_constants(header)
    for face in ROBOT_FACE_STATES:
        assert names[f"FACE_NAME_{face.upper()}"] == face


def test_the_firmware_can_say_exactly_the_five_ack_states(header):
    """Section 19. A device's whole vocabulary for reporting on a card."""
    members = {name.lower() for name in enum_members(header, "Ack")}
    assert members == set(ROBOT_ACK_STATES)

    names = string_constants(header)
    for ack in ROBOT_ACK_STATES:
        assert names[f"ACK_NAME_{ack.upper()}"] == ack


def test_the_firmware_knows_every_capability_key_and_state(header):
    """Sections 10, 11 and 12, as serialisation (section 131's fifth item)."""
    names = string_constants(header)
    for key in ROBOT_CAPABILITY_KEYS:
        assert names[f"CAPABILITY_{key.upper()}"] == key
    for state in ROBOT_CAPABILITY_STATES:
        assert names[f"CAPABILITY_{state.upper()}"] == state


def test_not_verified_exists_on_the_device_side(header):
    """Section 91: mandatory, and it is the device that reports it.

    The backend cannot write this state by itself -- it has never seen a
    build. So the constant has to exist in the firmware or the state is
    unreachable, and this is the test that keeps it reachable.
    """
    names = string_constants(header)
    assert names["CAPABILITY_NOT_VERIFIED"] == "not_verified"
    assert "not_verified" in ROBOT_CAPABILITY_STATES


def test_every_failure_code_the_firmware_can_send_is_one_the_backend_accepts(header):
    """Section 67: stable codes, and the backend refuses anything else.

    A firmware sending a code the backend's ``Literal`` does not list would
    get a 422 at the worst possible moment, so the two lists are compared
    rather than trusted.
    """
    sent = {
        value
        for name, value in string_constants(header).items()
        if name.startswith("FAILURE_")
    }
    assert sent == set(ROBOT_PRESENTATION_FAILURE_CODES)


def test_the_chime_categories_match(header):
    """Section 81. Nothing has ever played one, and they still have to agree."""
    source = (HEADER.parent / "audio_output.cpp").read_text(encoding="utf-8")
    for chime in ROBOT_CHIME_KINDS:
        assert f'"{chime}"' in source, chime


# --- the limits --------------------------------------------------------------


def test_the_text_limits_are_the_same_on_both_sides(header):
    """Section 77.

    The backend shortens to these before sending, so the firmware's buffers
    are sized from the same numbers rather than from a guess -- and a limit
    raised on one side without the other is the kind of mismatch that shows up
    as a truncated reminder on somebody's shelf.
    """
    numbers = number_constants(header)
    assert numbers["TITLE_MAX"] == layouts.TITLE_MAX
    assert numbers["PRIMARY_MAX"] == layouts.PRIMARY_MAX
    assert numbers["SECONDARY_MAX"] == layouts.SECONDARY_MAX
    assert numbers["BODY_MAX"] == layouts.BODY_MAX
    assert numbers["STATUS_LINE_MAX"] == layouts.LINE_MAX
    assert numbers["MAX_LINES"] == layouts.MAX_LINES
    assert numbers["CODE_MAX"] == layouts.CODE_MAX


def test_the_endpoints_in_the_header_are_the_endpoints_that_exist(header):
    """Sections 59, 60 and 61, checked against the live route table."""
    from app.main import app

    paths = set(app.openapi()["paths"])
    names = string_constants(header)
    assert names["PATH_NEXT"] in paths
    assert names["PATH_CAPABILITIES"] in paths
    ack_template = (
        names["PATH_ACK_PREFIX"] + "{presentation_id}" + names["PATH_ACK_SUFFIX"]
    )
    assert ack_template in paths


def test_the_envelope_is_small(header):
    """Section 108: state id, text and minimal parameters, not media.

    The firmware's parse buffer is the ceiling, and an envelope the backend
    can build has to fit in it. Checked against the largest one the backend
    can produce rather than against a typical one.
    """
    import json

    numbers = number_constants(header)
    biggest = layouts.build_envelope(
        presentation_id="7f3a1c20-0000-4000-8000-000000000001",
        presentation_type="emergency_status",
        priority=10,
        layout="EMERGENCY",
        payload=layouts.build_payload(
            "EMERGENCY",
            title="X" * layouts.TITLE_MAX,
            lines=["Y" * layouts.LINE_MAX] * layouts.MAX_LINES,
            serious=True,
            sensitive=True,
            continue_in_app=True,
            respond_in_app=True,
            actions=["open_app", "dismiss", "acknowledge"],
        ),
        mode="emergency",
        expires_at=None,
        settings=layouts.DeviceSettings(
            brightness=100,
            volume=100,
            reduced_motion=True,
            face_animation=False,
            sleep_screen="sleeping_face",
        ),
    )
    assert len(json.dumps(biggest)) < numbers["ENVELOPE_MAX_BYTES"]


# --- what the firmware must not contain --------------------------------------


def test_the_firmware_never_renders_markup(header):
    """Section 111: validated layout enums and fields, and nothing else.

    A grep rather than a proof, and it is worth having: the day somebody
    reaches for an HTML or JS renderer on a 240-pixel screen, this fails.
    """
    sources = list((HEADER.parent).glob("*.cpp")) + list(HEADER.parent.glob("*.h"))
    forbidden = ("innerHTML", "<html", "evaluateJavaScript", "WebView")
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{path.name} mentions {needle}"


def test_the_firmware_never_logs_a_payload(header):
    """Section 67, as far as a grep can check it.

    The two places a payload could reach a log are the silent audio output
    (which logs a character count rather than the text) and the simulated
    display driver (which is a development build with no panel, where the log
    *is* the screen). The physical driver logs nothing.
    """
    audio = (HEADER.parent / "audio_output.cpp").read_text(encoding="utf-8")
    assert "text.c_str()" not in audio
    assert "characters (not spoken)" in audio
