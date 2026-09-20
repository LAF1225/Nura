// Who this robot is (PRD 2, sections 11 and 30).
//
//   hardware_id       NURA-3C84279A1B2C, derived from the factory MAC
//   short id          1B2C, shown on screen and advertised as Nura-1B2C
//   bootstrap secret  32 random bytes made on first boot, kept in NVS
//
// The bootstrap secret is the prototype stand-in for a credential written at
// manufacture. It is never advertised, displayed or logged, and it survives a
// factory reset so the robot can be claimed again afterwards.
#pragma once

#include <Arduino.h>

namespace nura::identity {

//: Reads the identity from NVS, creating the bootstrap secret on first boot.
void begin();

const String& hardwareId();
const String& shortId();
const String& bleName();

//: Hex-encoded 32-byte secret. Sent to the backend only over TLS at claim time.
const String& bootstrapSecret();

}  // namespace nura::identity
