// Joining Wi-Fi, and saying precisely why when it does not work
// (PRD 2, sections 26-28).
//
// A scan runs first, so "that network isn't here" and "that password is
// wrong" are told apart properly rather than both surfacing as a timeout.
#pragma once

#include <Arduino.h>

#include "protocol.h"
#include "settings_store.h"

namespace nura::wifi {

enum class Outcome {
    CONNECTED,
    AUTH_FAILED,
    NOT_FOUND,
    TIMEOUT,
    UNSUPPORTED,
};

void begin();

//: Blocks for up to WIFI_ATTEMPT_TIMEOUT_MS per attempt. A wrong password is
//: reported at once rather than retried.
Outcome connect(const settings::WifiCredentials& credentials);

void disconnect();
bool isConnected();
int rssi();

//: The BLE error code the app should be told about.
protocol::ProvisioningError errorFor(Outcome outcome);

}  // namespace nura::wifi
