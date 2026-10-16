// Nura's face, as geometry rather than as artwork (PRD 11, sections 5, 27,
// 29, 30, 109 and 110).
//
// Section 109 rules out avatar packs and section 110 rules out needing local
// media storage, so the face is two rounded rectangles and a handful of
// numbers. ``shapeFor`` is a pure function of the face state, the motion
// preference and the clock -- which is what makes it the one piece of the
// renderer that can be reasoned about without a panel.
//
// Section 29's rules are properties of this function:
//
//   - subtle: the blink is the only movement, and it is brief;
//   - interruptible: there is no animation *state*, only a function of time,
//     so drawing something else needs nothing unwound;
//   - reduced-motion compatible: ``animate`` false means no blink at all
//     (section 30);
//   - non-essential: nothing is conveyed by the movement. A blinking face and
//     a still face say exactly the same thing, which is section 29's last
//     sentence.
//
// Section 28 is why there is no ``shapeFor`` parameter for severity, urgency
// or anything from the health record: the face takes a face state and nothing
// else, so it cannot come to imply a medical judgement.
#pragma once

#include <Arduino.h>

#include "presentation_protocol.h"

namespace nura::face {

//: Where the eyes are and how big, in pixels, for a 240x320 panel.
struct Shape {
    uint16_t eyeWidth = 48;
    uint16_t eyeHeight = 64;
    uint16_t cornerRadius = 20;
    //: Gap between the two eyes.
    uint16_t gap = 44;
    //: Positive moves the pair down the screen.
    int16_t offsetY = 0;
    //: True on the frames of a blink, when the eyes are drawn as slits.
    bool blinking = false;
    //: Dim the whole face, for sleep (section 31).
    bool dimmed = false;
};

//: How often the eyes blink, and for how long. Slow enough not to be busy
//: (section 29's "low frequency"), long enough to read as a blink.
constexpr uint32_t BLINK_PERIOD_MS = 5200;
constexpr uint32_t BLINK_DURATION_MS = 140;

//: The height the eyes collapse to mid-blink.
constexpr uint16_t BLINK_HEIGHT = 8;

//: The geometry for one face state at one moment.
//:
//: ``animate`` false -- reduced motion, or the face-animation preference off
//: -- produces a shape with ``blinking`` always false, which is section 30's
//: "static/minimal eyes, no rapid blink sequences".
Shape shapeFor(presentation::Face state, bool animate, uint32_t millisNow);

}  // namespace nura::face
