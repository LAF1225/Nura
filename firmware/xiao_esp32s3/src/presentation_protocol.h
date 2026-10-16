// Nura presentation protocol, version 1 -- firmware side (PRD 11).
//
// The contract is docs/device/presentation-protocol.md. The same vocabulary is
// defined for the backend in app/models/enums.py and for the app in
// mobile/src/features/robot/protocol.ts, and
// mobile/tests/robotPresentationProtocol.test.ts parses THIS file to make sure
// the three never drift. Keep the `enum class ... : uint8_t` / `constexpr`
// shapes below so that test can still read them.
//
// Two rules this header exists to make structural:
//
//   - A layout is a name from a closed set, never markup (PRD 11, section
//     111). The firmware draws LAYOUT_REMINDER; it never interprets a string
//     as a drawing instruction.
//   - A capability is what this device has *proven*, not what it compiled
//     (sections 12, 90 and 91). CAPABILITY_NOT_VERIFIED exists for the case
//     where the driver is present and nothing has been shown to work, and the
//     firmware reports it rather than claiming CAPABILITY_AVAILABLE.
#pragma once

#include <cstddef>
#include <cstdint>

namespace nura::presentation {

constexpr uint8_t PRESENTATION_PROTOCOL_VERSION = 1;

// --- endpoints (sections 59, 60 and 61) ------------------------------------
constexpr const char* PATH_NEXT = "/api/v1/device-actions/presentations/next";
constexpr const char* PATH_ACK_PREFIX = "/api/v1/device-actions/presentations/";
constexpr const char* PATH_ACK_SUFFIX = "/ack";
constexpr const char* PATH_CAPABILITIES = "/api/v1/device-actions/capabilities";

// --- layouts (section 37) --------------------------------------------------
// Eight, and the firmware has one branch per layout in card_renderer.cpp. An
// unrecognised layout is answered with ACK_UNSUPPORTED, never guessed at.
enum class Layout : uint8_t {
  UNKNOWN = 0x00,
  FACE = 0x01,
  TITLE_BODY = 0x02,
  TITLE_VALUE = 0x03,
  REMINDER = 0x04,
  MESSAGE = 0x05,
  STATUS = 0x06,
  EMERGENCY = 0x07,
  PAIRING_CODE = 0x08,
};

constexpr const char* LAYOUT_NAME_FACE = "FACE";
constexpr const char* LAYOUT_NAME_TITLE_BODY = "TITLE_BODY";
constexpr const char* LAYOUT_NAME_TITLE_VALUE = "TITLE_VALUE";
constexpr const char* LAYOUT_NAME_REMINDER = "REMINDER";
constexpr const char* LAYOUT_NAME_MESSAGE = "MESSAGE";
constexpr const char* LAYOUT_NAME_STATUS = "STATUS";
constexpr const char* LAYOUT_NAME_EMERGENCY = "EMERGENCY";
constexpr const char* LAYOUT_NAME_PAIRING_CODE = "PAIRING_CODE";

// --- presentation types (PRD 11 section 15; PRD 12 section 30) -------------
// Fifteen, and the firmware does not dispatch on any of them: a card is drawn
// from its LAYOUT, which is what keeps the renderer's branch count equal to
// the number of shapes a screen can take rather than the number of reasons a
// card exists. They are here for two things -- a log line that says what kind
// of card was handled without quoting its content (PRD 11, section 67), and
// the drift test that reads this file.
//
// PRD 12's four are the last four, and they needed no new branch anywhere in
// this firmware: a task, a reminder and an alarm are LAYOUT_REMINDER, and a
// routine's progress is LAYOUT_STATUS. That is the point of dispatching on
// layout.
constexpr const char* TYPE_FACE_STATE = "face_state";
constexpr const char* TYPE_INFO_CARD = "info_card";
constexpr const char* TYPE_MEDICATION_REMINDER = "medication_reminder";
constexpr const char* TYPE_APPOINTMENT_REMINDER = "appointment_reminder";
constexpr const char* TYPE_FAMILY_MESSAGE = "family_message";
constexpr const char* TYPE_ASSISTANT_RESPONSE = "assistant_response";
constexpr const char* TYPE_SAFETY_CHECK = "safety_check";
constexpr const char* TYPE_SAFETY_STATUS = "safety_status";
constexpr const char* TYPE_EMERGENCY_STATUS = "emergency_status";
constexpr const char* TYPE_SYSTEM_STATUS = "system_status";
constexpr const char* TYPE_SETUP_CODE = "setup_code";
constexpr const char* TYPE_TASK_REMINDER = "task_reminder";
constexpr const char* TYPE_GENERAL_REMINDER = "general_reminder";
constexpr const char* TYPE_ALARM = "alarm";
constexpr const char* TYPE_ROUTINE = "routine";

// --- face states (section 27) ----------------------------------------------
// Nine, and deliberately not more: section 28 forbids expression that implies
// a medical judgement, so there is no state here a renderer could reach for
// because a symptom was severe.
enum class Face : uint8_t {
  IDLE = 0x01,
  LISTENING = 0x02,
  THINKING = 0x03,
  SPEAKING = 0x04,
  HAPPY = 0x05,
  CONCERNED = 0x06,
  SLEEPING = 0x07,
  PRIVACY = 0x08,
  OFFLINE = 0x09,
};

constexpr const char* FACE_NAME_IDLE = "idle";
constexpr const char* FACE_NAME_LISTENING = "listening";
constexpr const char* FACE_NAME_THINKING = "thinking";
constexpr const char* FACE_NAME_SPEAKING = "speaking";
constexpr const char* FACE_NAME_HAPPY = "happy";
constexpr const char* FACE_NAME_CONCERNED = "concerned";
constexpr const char* FACE_NAME_SLEEPING = "sleeping";
constexpr const char* FACE_NAME_PRIVACY = "privacy";
constexpr const char* FACE_NAME_OFFLINE = "offline";

// --- acknowledgement states (section 19) -----------------------------------
// What this device may say about a presentation. Five words, and the two
// render states say different things about the *screen* rather than about the
// drawing: RENDER_STARTED is "it is on the screen and staying there", which is
// what a card gets; RENDER_COMPLETED is "I am finished with it".
enum class Ack : uint8_t {
  RECEIVED = 0x01,
  RENDER_STARTED = 0x02,
  RENDER_COMPLETED = 0x03,
  FAILED = 0x04,
  UNSUPPORTED = 0x05,
};

constexpr const char* ACK_NAME_RECEIVED = "received";
constexpr const char* ACK_NAME_RENDER_STARTED = "render_started";
constexpr const char* ACK_NAME_RENDER_COMPLETED = "render_completed";
constexpr const char* ACK_NAME_FAILED = "failed";
constexpr const char* ACK_NAME_UNSUPPORTED = "unsupported";

// --- failure codes (section 67) --------------------------------------------
// Stable codes, never this device's own error text: a payload must not be able
// to travel back to the backend inside a reason string.
constexpr const char* FAILURE_RENDER_FAILED = "render_failed";
constexpr const char* FAILURE_UNSUPPORTED_LAYOUT = "unsupported_layout";
constexpr const char* FAILURE_UNSUPPORTED_CAPABILITY = "unsupported_capability";
constexpr const char* FAILURE_UNSUPPORTED_PROTOCOL = "unsupported_protocol_version";
constexpr const char* FAILURE_NO_DISPLAY = "no_display";
constexpr const char* FAILURE_DEVICE_ERROR = "device_error";

// --- capabilities (sections 10, 11 and 12) ---------------------------------
constexpr const char* CAPABILITY_DISPLAY = "display";
constexpr const char* CAPABILITY_DISPLAY_TEXT = "display_text";
constexpr const char* CAPABILITY_DISPLAY_ANIMATION = "display_animation";
constexpr const char* CAPABILITY_SPEAKER = "speaker";
constexpr const char* CAPABILITY_TTS = "tts";
constexpr const char* CAPABILITY_AUDIO_PLAYBACK = "audio_playback";
constexpr const char* CAPABILITY_MICROPHONE = "microphone";
constexpr const char* CAPABILITY_WAKE_WORD = "wake_word";
constexpr const char* CAPABILITY_CAMERA = "camera";
constexpr const char* CAPABILITY_CAMERA_DETECTION = "camera_detection";
constexpr const char* CAPABILITY_BUTTONS = "buttons";
constexpr const char* CAPABILITY_TOUCH = "touch";

// Four states, and the third is mandatory (section 91). A compiled driver is
// not a working one: a build flag justifies NOT_VERIFIED and never AVAILABLE.
constexpr const char* CAPABILITY_AVAILABLE = "available";
constexpr const char* CAPABILITY_UNAVAILABLE = "unavailable";
constexpr const char* CAPABILITY_NOT_VERIFIED = "not_verified";
constexpr const char* CAPABILITY_NOT_CONNECTED = "not_connected";

// Where a report came from. SELF_TEST is a startup check's result (section
// 92); the backend's own `default` is not something a device may claim.
constexpr const char* CAPABILITY_SOURCE_SELF_TEST = "self_test";
constexpr const char* CAPABILITY_SOURCE_DEVICE_REPORT = "device_report";

// --- presentation state machine (section 88) -------------------------------
// Kept separate from the connectivity state machine in main.cpp and from
// anything to do with safety, which section 88 asks for explicitly.
enum class ManagerState : uint8_t {
  IDLE = 0x00,
  FETCHING = 0x01,
  RENDERING = 0x02,
  WAITING = 0x03,
  ACKING = 0x04,
  ERROR = 0x05,
};

// --- limits (section 77) ---------------------------------------------------
// The backend shortens to these before sending, so the firmware's buffers are
// sized from the same numbers rather than from a guess.
constexpr size_t TITLE_MAX = 24;
constexpr size_t PRIMARY_MAX = 32;
constexpr size_t SECONDARY_MAX = 48;
constexpr size_t BODY_MAX = 140;
//: Named STATUS_LINE_MAX rather than LINE_MAX: the latter is a POSIX
//: macro that <limits.h> defines, and Arduino.h pulls that in.
constexpr size_t STATUS_LINE_MAX = 48;
constexpr size_t MAX_LINES = 5;
constexpr size_t CODE_MAX = 8;
constexpr size_t ID_MAX = 40;

//: An envelope is small (section 108). This is the JSON buffer the client
//: parses one into; nothing media-sized ever arrives.
constexpr size_t ENVELOPE_MAX_BYTES = 1024;

//: How long after a render the device waits before asking for the next thing.
//: Not a timeout on the card: the backend decides when a card stops being
//: shown (sections 55 and 113), and this is only how often the device looks.
constexpr uint32_t PRESENTATION_POLL_INTERVAL_MS = 5000;

//: A failed fetch backs off to this rather than retrying in a tight loop.
constexpr uint32_t PRESENTATION_RETRY_INTERVAL_MS = 30000;

// --- helpers ---------------------------------------------------------------

//: Maps a layout name to the enum. UNKNOWN for anything this build does not
//: draw, which the manager turns into ACK_UNSUPPORTED.
Layout layoutFromName(const char* name);

//: The name a layout is sent as, for logging and for the ack body.
const char* layoutName(Layout layout);

//: Maps a face name to the enum. IDLE for anything unrecognised: a robot that
//: cannot tell which face to show is better off looking calm than blank.
Face faceFromName(const char* name);

const char* faceName(Face face);

const char* ackName(Ack ack);

}  // namespace nura::presentation
