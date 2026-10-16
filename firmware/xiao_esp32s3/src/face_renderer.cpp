#include "face_renderer.h"

namespace nura::face {

Shape shapeFor(presentation::Face state, bool animate, uint32_t millisNow) {
    Shape shape;

    switch (state) {
        case presentation::Face::IDLE:
            break;
        case presentation::Face::LISTENING:
            // A little wider open, which is the only difference and is not
            // meant to convey anything beyond "I am taking this in".
            shape.eyeHeight = 72;
            break;
        case presentation::Face::THINKING:
            // Looking slightly up and away.
            shape.offsetY = -10;
            shape.eyeHeight = 56;
            break;
        case presentation::Face::SPEAKING:
            shape.eyeHeight = 60;
            break;
        case presentation::Face::HAPPY:
            // Narrower and lower: the shape a smile makes of eyes, without a
            // mouth to overstate it.
            shape.eyeHeight = 36;
            shape.cornerRadius = 18;
            shape.offsetY = 6;
            break;
        case presentation::Face::CONCERNED:
            // Attentive, not alarmed (section 28). Slightly narrower, and
            // nothing that reads as distress.
            shape.eyeHeight = 52;
            break;
        case presentation::Face::SLEEPING:
            shape.eyeHeight = BLINK_HEIGHT;
            shape.cornerRadius = 4;
            shape.dimmed = true;
            break;
        case presentation::Face::PRIVACY:
            // Closed, dimmed, and still recognisably Nura: section 33 asks for
            // the privacy state to be clear, and a blank screen reads as
            // broken rather than as private.
            shape.eyeHeight = BLINK_HEIGHT;
            shape.cornerRadius = 4;
            break;
        case presentation::Face::OFFLINE:
            shape.dimmed = true;
            shape.eyeHeight = 40;
            break;
    }

    // Sleeping and privacy are *already* closed; blinking them would be a
    // flicker rather than a blink.
    const bool blinkable = state != presentation::Face::SLEEPING &&
                           state != presentation::Face::PRIVACY;
    if (animate && blinkable) {
        shape.blinking = (millisNow % BLINK_PERIOD_MS) < BLINK_DURATION_MS;
        if (shape.blinking) {
            shape.eyeHeight = BLINK_HEIGHT;
        }
    }
    return shape;
}

}  // namespace nura::face
