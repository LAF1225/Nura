// Talking to the Nura backend over Wi-Fi (PRD 2, sections 29, 32 and 35;
// PRD 11, sections 58, 59, 60 and 61).
//
// Five requests: claim, which trades the app's provisioning token for a device
// token; heartbeat, which says the robot is online and collects anything the
// backend wants it to do; and PRD 11's three -- report what this hardware can
// do, collect the next presentation, and say what happened when it was drawn.
//
// PRD 11 section 58 asks for the heartbeat to be extended rather than a second
// transport added, and that is what ``presentationPending`` is. The heartbeat
// carries the *flag* and never the presentation: a heartbeat is retried and
// logged, and section 67 keeps payloads out of anything that is.
//
// Release builds refuse a plain http:// address. Development builds allow one
// on the local network, because the backend then runs on a laptop.
#pragma once

#include <Arduino.h>

#include "presentation_protocol.h"
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
    //: There is something to show, so fetch it (PRD 11, section 58).
    bool presentationPending = false;
};

//: One presentation envelope, still as JSON. Parsed by card_renderer, which is
//: the only thing in this firmware that reads a payload.
struct PresentationResult {
    bool ok = false;
    //: 204: there is nothing to show right now, which is not a failure.
    bool empty = false;
    //: The envelope. The caller clears this as soon as it has parsed it --
    //: it holds a medication name or a message (PRD 11, section 67).
    String body;
};

//: What this device can actually do (PRD 11, sections 11 and 61).
//:
//: A fixed-size list rather than a map: there are twelve capability keys and
//: there is no sense in heap-allocating on a robot to describe them.
struct CapabilityReport {
    static constexpr uint8_t MAX_ENTRIES = 12;
    const char* keys[MAX_ENTRIES] = {};
    const char* states[MAX_ENTRIES] = {};
    uint8_t count = 0;

    void add(const char* key, const char* state) {
        if (count >= MAX_ENTRIES) return;
        keys[count] = key;
        states[count] = state;
        count += 1;
    }
};

//: True when this build will talk to that address at all.
bool isAcceptableUrl(const String& baseUrl);

ClaimResult claim(const String& baseUrl, const String& provisioningToken);

HeartbeatResult heartbeat(const String& baseUrl, const String& deviceToken,
                          bool introductionPlayed);

//: Section 61. ``source`` is ``self_test`` or ``device_report``; the backend
//: refuses its own ``default``, because that value means "nobody has said".
bool reportCapabilities(const String& baseUrl, const String& deviceToken,
                        const CapabilityReport& report, const char* source);

//: Section 59. A 204 comes back as ``ok`` with ``empty`` set.
PresentationResult fetchPresentation(const String& baseUrl, const String& deviceToken);

//: Section 60. ``failureCode`` is null unless the ack is FAILED or
//: UNSUPPORTED, and it is always one of presentation_protocol.h's stable
//: codes -- never this device's own error text (section 67).
bool acknowledgePresentation(const String& baseUrl, const String& deviceToken,
                             const String& presentationId, presentation::Ack ack,
                             const char* failureCode);

}  // namespace nura::backend
