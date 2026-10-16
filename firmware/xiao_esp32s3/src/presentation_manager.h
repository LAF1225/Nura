// The robot's side of the presentation protocol (PRD 11, sections 19, 58, 86,
// 87, 88, 92 and 98).
//
// One state machine, kept separate from the connectivity one in main.cpp and
// from anything to do with safety, which section 88 asks for explicitly:
//
//   IDLE      nothing to show, waiting for the poll interval
//   FETCHING  asking for the next presentation
//   RENDERING drawing it
//   WAITING   drawn, and staying on the screen
//   ACKING    telling the backend what happened
//   ERROR     the last fetch failed; backing off
//
// **Nothing is reported as rendered that was not rendered.** The ack is sent
// after the driver returns, and it carries what the driver actually did:
// ``render_started`` for a card now on the screen, ``failed`` when the driver
// refused, ``unsupported`` for a layout or protocol version this build does
// not know. Sections 14 and 19, from the device's end.
//
// **The self-test is what the capability report is built from** (section 92).
// It asks the drivers, and the drivers answer with what they have proven --
// which is ``not_verified`` for a panel that initialised and ``not_connected``
// for a speaker nobody has wired. Nothing here reads a build flag to decide
// that something works: a flag says the code is present (section 90).
//
// **Offline means local** (section 98). With no network the manager does not
// retry in a loop; it shows the offline card once and waits.
#pragma once

#include <Arduino.h>

#include "presentation_protocol.h"

namespace nura::presentation_manager {

//: Brings up the drivers and reports what they can do. Call once at boot,
//: after settings and display are up.
void begin();

//: Reports the self-test result to the backend (section 61). Safe to call
//: again; the backend treats a repeat report as the same answer.
bool reportCapabilities();

//: The backend said there is something waiting (section 58's heartbeat flag).
void notifyPending();

//: Called from the main loop. Does at most one unit of work per call, so the
//: BLE stack and the button are never starved.
void loop();

//: Shows the offline card, locally, without reaching the backend
//: (sections 34 and 98).
void showOffline();

//: Shows the companion face locally, used when the robot comes back online
//: before the first fetch answers.
void showIdleFace();

presentation::ManagerState state();

//: The last presentation this device drew, for diagnostics (section 65).
//: Empty until something has been drawn. An id, never a payload.
const String& lastPresentationId();

//: The last failure code this device reported, for diagnostics. Empty when
//: the last render succeeded.
const String& lastFailure();

}  // namespace nura::presentation_manager
