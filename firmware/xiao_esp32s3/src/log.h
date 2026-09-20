// Structured serial logging (PRD 2, section 49).
//
//   [PAIR] BLE advertising started
//   [WIFI] Connecting to SSID
//   [CLOUD] Registered
//
// NEVER log: the Wi-Fi password, the pairing code (outside the deliberate
// development fallback in display.cpp), SPAKE2 values, the provisioning token,
// the device token, or the bootstrap secret. Helpers below exist so that
// diagnosing a problem never tempts anyone into printing one.
#pragma once

#include <Arduino.h>

//: 0 = silent, 1 = warnings and errors, 2 = + info, 3 = + debug.
#ifndef NURA_LOG_LEVEL
#define NURA_LOG_LEVEL 2
#endif

#define NURA_LOG(level, tag, format, ...)                     \
    do {                                                      \
        if ((level) <= NURA_LOG_LEVEL) {                      \
            Serial.printf("[" tag "] " format "\n", ##__VA_ARGS__); \
        }                                                     \
    } while (0)

#define NURA_ERROR(tag, format, ...) NURA_LOG(1, tag, format, ##__VA_ARGS__)
#define NURA_INFO(tag, format, ...) NURA_LOG(2, tag, format, ##__VA_ARGS__)
#define NURA_DEBUG(tag, format, ...) NURA_LOG(3, tag, format, ##__VA_ARGS__)

namespace nura::log {

//: Describes a secret's presence without revealing any of it.
inline const char* present(bool value) {
    return value ? "present" : "absent";
}

}  // namespace nura::log
