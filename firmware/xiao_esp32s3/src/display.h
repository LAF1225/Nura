// What Nura shows while it is being set up (PRD 2, sections 14 and 39).
//
// The robot has no screen yet, so this is a small interface with two
// implementations chosen at build time: a real 240x320 SPI TFT when
// NURA_HAS_DISPLAY is 1, and otherwise a serial-only stand-in.
//
// The serial stand-in prints the pairing code, which is a DEVELOPMENT
// fallback only: PRD 2 section 20 is clear that ordinary users must never be
// sent to a serial monitor. A shipped robot needs the screen.
#pragma once

#include <Arduino.h>

namespace nura::display {

void begin();

//: Idle in pairing mode: shows which Nura this is, so the user can match it
//: to the list in the app.
void showPairingReady(const String& bleName);

//: The six digits the user types into the app.
void showPairingCode(const String& code);

//: A short line of progress, e.g. "Joining Wi-Fi".
void showStatus(const String& message);

//: The calm face shown once setup is complete (PRD 2, section 39).
void showConnected();

void showOffline();

//: True when this build drives a real screen.
bool isFitted();

// --- primitives for the presentation layer (PRD 11, section 89) -------------
//
// PRD 11's DisplayDriver is the abstraction product logic talks to; these are
// the three shapes it needs drawn, and they live here because this file owns
// the panel. Nothing above this line changed, and PRD 2's pairing screens
// still go through showPairingCode() and friends.
//
// All of them are no-ops in a build with no panel, which is every build so
// far.

//: Two rounded eyes, from the geometry face_renderer.cpp worked out.
//: Named drawEyes rather than drawFace so it does not read as an overload
//: of PRD 2's own calm-face helper, which is a different thing.
void drawEyes(uint16_t eyeWidth, uint16_t eyeHeight, uint16_t cornerRadius,
              uint16_t gap, int16_t offsetY, bool dimmed);

//: A heading and up to five short lines. ``highContrast`` drops the accent
//: colour, which is what a serious or emergency card asks for
//: (PRD 11, section 106).
void drawLines(const String& title, const String* lines, uint8_t count,
               bool highContrast);

//: Blanks the panel without turning the backlight off.
void blank();

//: 0-100. Mapped onto the backlight's own range (PRD 11, section 45).
void setBrightness(uint8_t percent);

}  // namespace nura::display
