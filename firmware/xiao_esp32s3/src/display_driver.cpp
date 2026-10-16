#include "display_driver.h"

#include "display.h"
#include "face_renderer.h"
#include "log.h"

namespace nura::display_driver {
namespace {

//: What the serial log prints instead of drawing. Deliberately the same
//: shape as the simulator's own ``lines`` in
//: ``backend/app/services/robot/simulator.py``, so a developer reading one can
//: recognise the other.
String summarise(const Card& card) {
    String out = card.title;
    const auto add = [&out](const String& value) {
        if (value.length() == 0) return;
        if (out.length() > 0) out += " / ";
        out += value;
    };
    add(card.sender);
    add(card.primary);
    add(card.secondary);
    add(card.value);
    add(card.prompt);
    add(card.body);
    add(card.code);
    for (uint8_t index = 0; index < card.lineCount; index += 1) {
        add(card.lines[index]);
    }
    return out;
}

}  // namespace

// --- the simulated driver ---------------------------------------------------

bool SimulatedDisplayDriver::begin() {
    NURA_INFO("DISP", "no panel in this build; presentations go to the log");
    // True: the driver is usable. What it is *not* is a screen, and
    // ``capabilityState`` is where that is reported.
    return true;
}

bool SimulatedDisplayDriver::renderFace(presentation::Face face, bool animate) {
    NURA_INFO("DISP", "[face] %s%s", presentation::faceName(face),
              animate ? "" : " (still)");
    return true;
}

bool SimulatedDisplayDriver::renderCard(const Card& card) {
    NURA_INFO("DISP", "[%s] %s", presentation::layoutName(card.layout),
              summarise(card).c_str());
    return true;
}

bool SimulatedDisplayDriver::renderStatus(const Card& card) {
    return renderCard(card);
}

bool SimulatedDisplayDriver::renderEmergency(const Card& card) {
    return renderCard(card);
}

void SimulatedDisplayDriver::clear() {
    NURA_INFO("DISP", "[clear]");
}

void SimulatedDisplayDriver::setBrightness(uint8_t percent) {
    NURA_DEBUG("DISP", "[brightness] %u%%", static_cast<unsigned>(percent));
}

// --- the physical driver ----------------------------------------------------

#if NURA_HAS_DISPLAY

bool PhysicalDisplayDriver::begin() {
    _ready = nura::display::isFitted();
    if (!_ready) {
        NURA_ERROR("DISP", "the panel did not initialise");
    }
    return _ready;
}

const char* PhysicalDisplayDriver::capabilityState() const {
    if (!_ready) {
        // The driver is compiled in and the panel did not answer.
        return presentation::CAPABILITY_UNAVAILABLE;
    }
    // Section 12, and the single most important line in this file. ``init()``
    // returning true means this code talked to something over SPI. It does not
    // mean a person has seen a legible frame, and until one has, the honest
    // state is ``not_verified`` -- section 91 makes that mandatory and section
    // 93 keeps the physical check as a separate, later step.
    return presentation::CAPABILITY_NOT_VERIFIED;
}

bool PhysicalDisplayDriver::canRenderText() const {
    return _ready;
}

bool PhysicalDisplayDriver::canAnimate() const {
    return _ready;
}

bool PhysicalDisplayDriver::renderFace(presentation::Face face, bool animate) {
    if (!_ready) return false;
    const nura::face::Shape shape = nura::face::shapeFor(face, animate, millis());
    nura::display::drawEyes(shape.eyeWidth, shape.eyeHeight, shape.cornerRadius,
                            shape.gap, shape.offsetY, shape.dimmed);
    return true;
}

bool PhysicalDisplayDriver::renderCard(const Card& card) {
    if (!_ready) return false;
    String lines[presentation::MAX_LINES];
    uint8_t count = 0;
    const auto add = [&lines, &count](const String& value) {
        if (value.length() == 0 || count >= presentation::MAX_LINES) return;
        lines[count] = value;
        count += 1;
    };
    add(card.sender);
    add(card.primary);
    add(card.secondary);
    add(card.value);
    add(card.body);
    add(card.code);
    add(card.prompt);
    nura::display::drawLines(card.title, lines, count, card.serious);
    return true;
}

bool PhysicalDisplayDriver::renderStatus(const Card& card) {
    if (!_ready) return false;
    nura::display::drawLines(card.title, card.lines, card.lineCount, true);
    return true;
}

bool PhysicalDisplayDriver::renderEmergency(const Card& card) {
    if (!_ready) return false;
    // Section 106: readability over brand gradients. The high-contrast flag is
    // what the panel code reads to drop the accent colour.
    nura::display::drawLines(card.title, card.lines, card.lineCount, true);
    return true;
}

void PhysicalDisplayDriver::clear() {
    if (_ready) nura::display::blank();
}

void PhysicalDisplayDriver::setBrightness(uint8_t percent) {
    if (_ready) nura::display::setBrightness(percent);
}

#endif  // NURA_HAS_DISPLAY

// --- which one this build uses ----------------------------------------------

DisplayDriver& active() {
#if NURA_HAS_DISPLAY
    static PhysicalDisplayDriver physical;
    return physical;
#else
    static SimulatedDisplayDriver simulated;
    return simulated;
#endif
}

}  // namespace nura::display_driver
