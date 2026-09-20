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

}  // namespace nura::display
