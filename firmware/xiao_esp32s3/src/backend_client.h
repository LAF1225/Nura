// Talking to the Nura backend over Wi-Fi (PRD 2, sections 29, 32 and 35).
//
// Two requests exist: claim, which trades the app's provisioning token for a
// device token, and heartbeat, which says the robot is online and collects
// anything the backend wants it to do.
//
// Release builds refuse a plain http:// address. Development builds allow one
// on the local network, because the backend then runs on a laptop.
#pragma once

#include <Arduino.h>

#include "protocol.h"

namespace nura::backend {

struct ClaimResult {
    bool ok = false;
    String deviceId;
    String deviceToken;
    uint32_t heartbeatIntervalSeconds = 30;
    //: Set when the claim was refused for a reason the user should hear.
    protocol::ProvisioningError error = protocol::ProvisioningError::NONE;
};

struct HeartbeatResult {
    bool ok = false;
    uint32_t heartbeatIntervalSeconds = 30;
    //: The backend is asking the robot to introduce itself now.
    bool introduce = false;
    //: The device token is no longer accepted; the robot has been unlinked.
    bool unauthorised = false;
};

//: True when this build will talk to that address at all.
bool isAcceptableUrl(const String& baseUrl);

ClaimResult claim(const String& baseUrl, const String& provisioningToken);

HeartbeatResult heartbeat(const String& baseUrl, const String& deviceToken,
                          bool introductionPlayed);

}  // namespace nura::backend
