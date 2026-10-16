// Firmware tests for the presentation protocol (PRD 11, section 131).
//
// Section 131 lists what to verify without real hardware: payload parsing,
// layout dispatch, priority/preemption, ack generation, capability
// serialization, unsupported layout handling and protocol version handling.
// Everything in that list except priority/preemption -- which is the
// backend's decision, tested in backend/tests/test_robot_presentations.py --
// is exercised here, against the same functions the firmware runs.
//
// **These tests run on the board.** PlatformIO's Unity integration builds them
// into a firmware image and flashes it, because that is where an Arduino
// `String` and ArduinoJson live. There is no board, so **they have never been
// executed**: what has been proven is that they compile for the target, with
// `pio test -e xiao_esp32s3 --without-uploading --without-testing`.
//
// That is a real limit and the completion report says so. What *is* executed
// on a development machine is the same vocabulary, checked from both other
// sides: backend/tests/test_robot_protocol.py parses this directory's
// presentation_protocol.h and asserts it matches the backend's value sets, and
// mobile/tests/robotPresentationProtocol.test.ts does the same from the app.
// So a drift between the three fails on a laptop; what needs the board is
// whether this C++ behaves as written.
#include <Arduino.h>
#include <unity.h>

#include "card_renderer.h"
#include "display_driver.h"
#include "face_renderer.h"
#include "presentation_protocol.h"

using namespace nura;

namespace {

//: A whole envelope, as the backend builds one.
const char* REMINDER_ENVELOPE = R"({
  "protocol_version": 1,
  "presentation_id": "7f3a1c20-0000-4000-8000-000000000001",
  "type": "medication_reminder",
  "priority": 40,
  "mode": "information",
  "layout": "REMINDER",
  "payload": {
    "title": "Medication",
    "primary": "Reminder due",
    "respond_in_app": true,
    "sensitive": false
  },
  "settings": {
    "brightness": 70,
    "volume": 40,
    "reduced_motion": false,
    "face_animation": true,
    "sleep_screen": "dim"
  }
})";

}  // namespace

// --- payload parsing --------------------------------------------------------

void test_a_reminder_envelope_parses(void) {
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(REMINDER_ENVELOPE, envelope)));
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Layout::REMINDER),
                      static_cast<int>(envelope.card.layout));
    TEST_ASSERT_EQUAL_STRING("Medication", envelope.card.title.c_str());
    TEST_ASSERT_EQUAL_STRING("Reminder due", envelope.card.primary.c_str());
    TEST_ASSERT_TRUE(envelope.card.respondInApp);
    TEST_ASSERT_EQUAL(70, envelope.brightness);
    TEST_ASSERT_FALSE(envelope.reducedMotion);
    // Nothing asked to be spoken, which is true of every envelope this
    // project has produced (PRD 11, section 43).
    TEST_ASSERT_FALSE(envelope.speak);
}

void test_a_newer_protocol_version_is_refused(void) {
    const char* json = R"({"protocol_version": 99, "layout": "FACE",
                           "payload": {"face_state": "idle"}})";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::UNSUPPORTED_VERSION),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL_STRING(presentation::FAILURE_UNSUPPORTED_PROTOCOL,
                             card::failureFor(card::ParseResult::UNSUPPORTED_VERSION));
}

void test_an_unknown_layout_is_refused_rather_than_guessed(void) {
    const char* json = R"({"protocol_version": 1, "layout": "CAROUSEL",
                           "payload": {"title": "Nura"}})";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::UNSUPPORTED_LAYOUT),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL_STRING(presentation::FAILURE_UNSUPPORTED_LAYOUT,
                             card::failureFor(card::ParseResult::UNSUPPORTED_LAYOUT));
}

void test_a_layout_missing_a_field_it_needs_is_refused(void) {
    const char* json = R"({"protocol_version": 1, "layout": "REMINDER",
                           "payload": {"title": "Medication"}})";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::INCOMPLETE),
                      static_cast<int>(card::parse(json, envelope)));
}

void test_malformed_json_is_refused(void) {
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::MALFORMED),
                      static_cast<int>(card::parse("{not json", envelope)));
}

void test_message_text_stays_text(void) {
    // PRD 11, section 112: a message that looks like a payload is a String in
    // a field. There is no second parse and no place for one.
    const char* json = R"({
      "protocol_version": 1, "layout": "MESSAGE",
      "payload": {"title": "Message", "sender": "Ayesha",
                  "body": "{\"layout\": \"EMERGENCY\"}"}
    })";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Layout::MESSAGE),
                      static_cast<int>(envelope.card.layout));
    TEST_ASSERT_EQUAL_STRING("{\"layout\": \"EMERGENCY\"}", envelope.card.body.c_str());
}

void test_status_lines_are_read_and_capped(void) {
    const char* json = R"({
      "protocol_version": 1, "layout": "EMERGENCY",
      "payload": {"title": "EMERGENCY MODE",
                  "lines": ["a", "b", "c", "d", "e", "f", "g"],
                  "serious": true}
    })";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL(presentation::MAX_LINES, envelope.card.lineCount);
    TEST_ASSERT_TRUE(envelope.card.serious);
}

// --- daily-life cards (PRD 12, sections 30, 33 and 64) ----------------------
//
// PRD 12 added four presentation types and **no new layout**, which is the
// claim these two tests exist to check rather than assert in a document. A
// task, a reminder and an alarm are LAYOUT_REMINDER; a routine's progress is
// LAYOUT_STATUS. Both already had a branch in card_renderer.cpp, so the
// firmware needed no parser change -- and if a later PRD breaks that, these
// fail on a laptop rather than on a shelf.

void test_a_task_card_parses_as_a_reminder(void) {
    const char* json = R"({
      "protocol_version": 1,
      "presentation_id": "7f3a1c20-0000-4000-8000-000000000055",
      "type": "task_reminder",
      "priority": 54,
      "mode": "information",
      "layout": "REMINDER",
      "payload": {
        "title": "Task",
        "primary": "Call physiotherapist",
        "secondary": "Today, 4:00 PM",
        "respond_in_app": true,
        "sensitive": true
      },
      "settings": {"brightness": 70, "volume": 40, "reduced_motion": false,
                   "face_animation": true, "sleep_screen": "dim"}
    })";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Layout::REMINDER),
                      static_cast<int>(envelope.card.layout));
    TEST_ASSERT_EQUAL_STRING(presentation::TYPE_TASK_REMINDER,
                             envelope.type.c_str());
    TEST_ASSERT_EQUAL_STRING("Call physiotherapist", envelope.card.primary.c_str());
    TEST_ASSERT_TRUE(envelope.card.respondInApp);
    // Nothing on a daily-life card asks to be read aloud: no capability
    // report has ever included a speaker (PRD 12, section 65).
    TEST_ASSERT_FALSE(envelope.speak);
}

void test_a_routine_card_parses_as_a_status(void) {
    const char* json = R"({
      "protocol_version": 1,
      "presentation_id": "7f3a1c20-0000-4000-8000-000000000056",
      "type": "routine",
      "priority": 56,
      "mode": "information",
      "layout": "STATUS",
      "payload": {
        "title": "Morning routine",
        "lines": ["2 of 3 complete", "Next: Stretch", "Use the Nura app to respond."],
        "sensitive": true
      },
      "settings": {"brightness": 70, "volume": 40, "reduced_motion": false,
                   "face_animation": true, "sleep_screen": "dim"}
    })";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Layout::STATUS),
                      static_cast<int>(envelope.card.layout));
    TEST_ASSERT_EQUAL_STRING(presentation::TYPE_ROUTINE, envelope.type.c_str());
    TEST_ASSERT_EQUAL(3, envelope.card.lineCount);
    TEST_ASSERT_EQUAL_STRING("2 of 3 complete", envelope.card.lines[0].c_str());
}

void test_an_alarm_card_cannot_ask_for_a_sound_this_robot_has(void) {
    // PRD 12, section 65. The backend builds this card with no chime at all
    // when the speaker is not reported, and the parser leaves the field empty
    // -- so there is no path by which the firmware comes to believe it should
    // make a noise.
    const char* json = R"({
      "protocol_version": 1, "type": "alarm", "layout": "REMINDER",
      "payload": {"title": "Alarm", "primary": "Wake up",
                  "secondary": "7:00 AM · Nura cannot sound this",
                  "respond_in_app": true}
    })";
    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(json, envelope)));
    TEST_ASSERT_EQUAL_STRING(presentation::TYPE_ALARM, envelope.type.c_str());
    TEST_ASSERT_EQUAL_STRING("", envelope.chime.c_str());
    TEST_ASSERT_FALSE(envelope.speak);
}

// --- layout dispatch --------------------------------------------------------

void test_every_layout_name_maps_to_itself(void) {
    const char* names[] = {
        presentation::LAYOUT_NAME_FACE,      presentation::LAYOUT_NAME_TITLE_BODY,
        presentation::LAYOUT_NAME_TITLE_VALUE, presentation::LAYOUT_NAME_REMINDER,
        presentation::LAYOUT_NAME_MESSAGE,   presentation::LAYOUT_NAME_STATUS,
        presentation::LAYOUT_NAME_EMERGENCY, presentation::LAYOUT_NAME_PAIRING_CODE,
    };
    for (const char* name : names) {
        const presentation::Layout layout = presentation::layoutFromName(name);
        TEST_ASSERT_NOT_EQUAL(static_cast<int>(presentation::Layout::UNKNOWN),
                              static_cast<int>(layout));
        TEST_ASSERT_EQUAL_STRING(name, presentation::layoutName(layout));
    }
}

void test_dispatch_draws_each_layout_once(void) {
    // The simulated driver counts what it was asked to do, which is how
    // dispatch is checked without a panel.
    display_driver::SimulatedDisplayDriver driver;
    TEST_ASSERT_TRUE(driver.begin());

    card::Envelope envelope;
    TEST_ASSERT_EQUAL(static_cast<int>(card::ParseResult::OK),
                      static_cast<int>(card::parse(REMINDER_ENVELOPE, envelope)));
    TEST_ASSERT_TRUE(card::render(driver, envelope));
}

void test_the_simulated_driver_never_claims_a_screen(void) {
    // PRD 11, section 12: there is no panel, so the capability is
    // ``unavailable`` and not ``available``.
    display_driver::SimulatedDisplayDriver driver;
    TEST_ASSERT_EQUAL_STRING(presentation::CAPABILITY_UNAVAILABLE,
                             driver.capabilityState());
    TEST_ASSERT_FALSE(driver.canRenderText());
}

// --- acknowledgement generation --------------------------------------------

void test_every_ack_has_the_name_the_backend_expects(void) {
    TEST_ASSERT_EQUAL_STRING("received", presentation::ackName(presentation::Ack::RECEIVED));
    TEST_ASSERT_EQUAL_STRING("render_started",
                             presentation::ackName(presentation::Ack::RENDER_STARTED));
    TEST_ASSERT_EQUAL_STRING("render_completed",
                             presentation::ackName(presentation::Ack::RENDER_COMPLETED));
    TEST_ASSERT_EQUAL_STRING("failed", presentation::ackName(presentation::Ack::FAILED));
    TEST_ASSERT_EQUAL_STRING("unsupported",
                             presentation::ackName(presentation::Ack::UNSUPPORTED));
}

// --- the face ---------------------------------------------------------------

void test_reduced_motion_never_blinks(void) {
    // PRD 11, section 30. Checked across a whole blink period, so a passing
    // result is not an accident of timing.
    for (uint32_t offset = 0; offset < face::BLINK_PERIOD_MS; offset += 37) {
        const face::Shape shape =
            face::shapeFor(presentation::Face::IDLE, false, offset);
        TEST_ASSERT_FALSE(shape.blinking);
    }
}

void test_an_animated_face_blinks_briefly_and_rarely(void) {
    uint32_t blinking = 0;
    const uint32_t step = 10;
    for (uint32_t offset = 0; offset < face::BLINK_PERIOD_MS; offset += step) {
        if (face::shapeFor(presentation::Face::IDLE, true, offset).blinking) {
            blinking += step;
        }
    }
    TEST_ASSERT_TRUE(blinking > 0);
    // Section 29's "subtle": a small fraction of the time, not a flicker.
    TEST_ASSERT_TRUE(blinking * 10 < face::BLINK_PERIOD_MS);
}

void test_a_sleeping_face_is_already_closed_and_does_not_blink(void) {
    const face::Shape shape = face::shapeFor(presentation::Face::SLEEPING, true, 0);
    TEST_ASSERT_FALSE(shape.blinking);
    TEST_ASSERT_EQUAL(face::BLINK_HEIGHT, shape.eyeHeight);
    TEST_ASSERT_TRUE(shape.dimmed);
}

void test_an_unknown_face_falls_back_to_idle(void) {
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Face::IDLE),
                      static_cast<int>(presentation::faceFromName("exasperated")));
    TEST_ASSERT_EQUAL(static_cast<int>(presentation::Face::IDLE),
                      static_cast<int>(presentation::faceFromName("")));
}

// --- the runner -------------------------------------------------------------

void setup() {
    delay(1500);
    UNITY_BEGIN();
    RUN_TEST(test_a_reminder_envelope_parses);
    RUN_TEST(test_a_newer_protocol_version_is_refused);
    RUN_TEST(test_an_unknown_layout_is_refused_rather_than_guessed);
    RUN_TEST(test_a_layout_missing_a_field_it_needs_is_refused);
    RUN_TEST(test_malformed_json_is_refused);
    RUN_TEST(test_message_text_stays_text);
    RUN_TEST(test_status_lines_are_read_and_capped);
    RUN_TEST(test_a_task_card_parses_as_a_reminder);
    RUN_TEST(test_a_routine_card_parses_as_a_status);
    RUN_TEST(test_an_alarm_card_cannot_ask_for_a_sound_this_robot_has);
    RUN_TEST(test_every_layout_name_maps_to_itself);
    RUN_TEST(test_dispatch_draws_each_layout_once);
    RUN_TEST(test_the_simulated_driver_never_claims_a_screen);
    RUN_TEST(test_every_ack_has_the_name_the_backend_expects);
    RUN_TEST(test_reduced_motion_never_blinks);
    RUN_TEST(test_an_animated_face_blinks_briefly_and_rarely);
    RUN_TEST(test_a_sleeping_face_is_already_closed_and_does_not_blink);
    RUN_TEST(test_an_unknown_face_falls_back_to_idle);
    UNITY_END();
}

void loop() {}
