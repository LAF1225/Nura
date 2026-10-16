// Turning an envelope into a drawn card (PRD 11, sections 37, 38, 111, 112,
// 116 and 131).
//
// Two jobs, and they are kept apart because only one of them needs a screen:
//
//   parse()   JSON -> Envelope. No drawing, no hardware, pure logic.
//   render()  Envelope -> one call on a DisplayDriver. Dispatch on layout.
//
// **Parsing is where a bad envelope stops.** An unknown protocol version, an
// unknown layout and a payload missing a field the layout needs are all
// refusals (section 116), and each one has its own stable failure code to
// report back. Nothing is guessed at and nothing partial is drawn.
//
// **A text field is never structure.** Section 112: the fields are read by
// name out of the parsed JSON object and copied into a struct of Strings. A
// message whose text happens to look like a payload is a String in
// ``Card::body``; there is no second parse and no place for one.
//
// **Dispatch is a switch over the layout enum** (section 37). Eight branches,
// one per layout, and ``Layout::UNKNOWN`` reports ``unsupported`` rather than
// falling through to something that looks close enough.
#pragma once

#include <Arduino.h>

#include "display_driver.h"
#include "presentation_protocol.h"

namespace nura::card {

enum class ParseResult : uint8_t {
    OK = 0,
    //: The JSON could not be read at all.
    MALFORMED = 1,
    //: A newer backend. Section 116: fail safely rather than guessing.
    UNSUPPORTED_VERSION = 2,
    //: A layout this build does not draw.
    UNSUPPORTED_LAYOUT = 3,
    //: The layout is known and a field it needs is missing.
    INCOMPLETE = 4,
};

//: One envelope, parsed. The settings travel with every presentation
//: (sections 30, 44 and 45), so a robot that has just reconnected draws with
//: the current preferences without a second request.
struct Envelope {
    String presentationId;
    String type;
    String mode;
    uint8_t protocolVersion = 0;
    uint16_t priority = 0;
    display_driver::Card card;
    uint8_t brightness = 70;
    uint8_t volume = 0;
    bool reducedMotion = false;
    bool faceAnimation = true;
    //: Section 43: may this be read aloud? False on every envelope this
    //: project has ever produced, because no capability report has ever
    //: included a speaker.
    bool speak = false;
    //: Section 81's category, if any.
    String chime;
};

//: Reads an envelope. Never draws anything, never touches hardware, and is
//: the function section 131's "payload parsing" means.
ParseResult parse(const char* json, Envelope& out);

//: The failure code to report for a parse result (section 67's stable codes).
const char* failureFor(ParseResult result);

//: Draws a parsed envelope on a driver. One call per layout.
//:
//: Returns false when the driver could not draw it, which the manager reports
//: as ``failed`` -- distinct from ``unsupported``, which is a layout this
//: build does not know.
bool render(display_driver::DisplayDriver& driver, const Envelope& envelope);

}  // namespace nura::card
