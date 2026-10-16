// What a screen can be asked to do (PRD 11, sections 39, 40 and 90).
//
// Product logic talks to this interface and never to a display library, which
// is section 39. Three implementations are supported conceptually (section
// 40) and two exist here:
//
//   SimulatedDisplayDriver   writes what it would have drawn to the serial log
//   PhysicalDisplayDriver    drives the SPI TFT through nura::display
//
// A SerialDisplayDriver -- a panel on the other end of a UART -- would be a
// third, and the interface is what makes adding one a file rather than a
// refactor.
//
// **The physical driver reports itself NOT_VERIFIED, always.** Section 12: a
// compiled driver is not a working screen, and this firmware has never drawn a
// frame on real hardware. ``capabilityState()`` is the one function the backend
// learns the truth from, and it does not consult a build flag to decide that
// something works -- a flag says the code is present, and that is a different
// claim (section 90).
#pragma once

#include <Arduino.h>

#include "presentation_protocol.h"

namespace nura::display_driver {

//: One card, already shortened by the backend to the limits in
//: presentation_protocol.h. The firmware never lengthens, reflows or
//: re-interprets any of it.
struct Card {
    presentation::Layout layout = presentation::Layout::UNKNOWN;
    String title;
    String primary;
    String secondary;
    String prompt;
    String body;
    String sender;
    String value;
    String code;
    String lines[presentation::MAX_LINES];
    uint8_t lineCount = 0;
    presentation::Face face = presentation::Face::IDLE;
    //: Section 7: no face, no decoration, high contrast.
    bool serious = false;
    //: Section 86: the device has no input, so say where the answer goes.
    bool respondInApp = false;
    //: Sections 78 and 79.
    bool continueInApp = false;
};

class DisplayDriver {
   public:
    virtual ~DisplayDriver() = default;

    //: Brings the screen up. False means there is no usable screen, which the
    //: manager reports as a capability rather than treating as an error.
    virtual bool begin() = 0;

    virtual bool renderFace(presentation::Face face, bool animate) = 0;
    virtual bool renderCard(const Card& card) = 0;
    virtual bool renderStatus(const Card& card) = 0;
    virtual bool renderEmergency(const Card& card) = 0;
    virtual void clear() = 0;
    virtual void setBrightness(uint8_t percent) = 0;

    //: For the log and for diagnostics. Never shown to a user.
    virtual const char* name() const = 0;

    //: What to report for the ``display`` capability (sections 11, 12 and 91).
    virtual const char* capabilityState() const = 0;

    //: Whether this driver can draw text, as opposed to only shapes.
    virtual bool canRenderText() const = 0;

    //: Whether it can animate at all (section 10's ``display_animation``).
    virtual bool canAnimate() const = 0;
};

//: The one that exists on every build. Writes a one-line summary of what it
//: would have drawn, which is how a development board exercises the whole
//: protocol with no panel attached.
//:
//: It reports ``unavailable`` rather than ``available``: there is no screen,
//: and a simulated driver claiming one would be the exact failure PRD 11
//: section 12 is written against.
class SimulatedDisplayDriver : public DisplayDriver {
   public:
    bool begin() override;
    bool renderFace(presentation::Face face, bool animate) override;
    bool renderCard(const Card& card) override;
    bool renderStatus(const Card& card) override;
    bool renderEmergency(const Card& card) override;
    void clear() override;
    void setBrightness(uint8_t percent) override;
    const char* name() const override { return "simulated"; }
    const char* capabilityState() const override {
        return presentation::CAPABILITY_UNAVAILABLE;
    }
    bool canRenderText() const override { return false; }
    bool canAnimate() const override { return false; }
};

#if NURA_HAS_DISPLAY

//: The SPI TFT, through the panel nura::display already owns.
//:
//: Reports ``not_verified`` even when ``begin()`` succeeded. An init that
//: returns true means the driver talked to *something* over SPI; it does not
//: mean a person has seen a legible frame, and section 93 keeps that
//: verification as a separate, later, physical step.
class PhysicalDisplayDriver : public DisplayDriver {
   public:
    bool begin() override;
    bool renderFace(presentation::Face face, bool animate) override;
    bool renderCard(const Card& card) override;
    bool renderStatus(const Card& card) override;
    bool renderEmergency(const Card& card) override;
    void clear() override;
    void setBrightness(uint8_t percent) override;
    const char* name() const override { return "tft"; }
    const char* capabilityState() const override;
    bool canRenderText() const override;
    bool canAnimate() const override;

   private:
    bool _ready = false;
};

#endif  // NURA_HAS_DISPLAY

//: The driver this build uses. One place to change when a real panel arrives.
DisplayDriver& active();

}  // namespace nura::display_driver
