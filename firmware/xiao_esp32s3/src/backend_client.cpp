#include "backend_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "device_identity.h"
#include "log.h"

namespace nura::backend {
namespace {

constexpr const char* CLAIM_PATH = "/api/v1/devices/claim";
constexpr const char* HEARTBEAT_PATH = "/api/v1/devices/heartbeat";

bool isHttps(const String& url) {
    return url.startsWith("https://");
}

//: One request, with the body built by the caller. Returns the HTTP status,
//: or a negative number if the request could not be made at all.
int post(const String& url, const String& body, const String& bearerToken, String& responseOut) {
    if (!isAcceptableUrl(url)) {
        NURA_ERROR("CLOUD", "refusing to use an insecure backend address");
        return -1;
    }

    HTTPClient http;
    http.setTimeout(protocol::HTTP_TIMEOUT_MS);
    http.setConnectTimeout(protocol::HTTP_TIMEOUT_MS);

    bool started = false;
    WiFiClientSecure secureClient;
    WiFiClient plainClient;
    if (isHttps(url)) {
#ifdef NURA_BACKEND_ROOT_CA
        // Certificates are never skipped: without a trust anchor compiled in,
        // the request is refused rather than made insecurely.
        secureClient.setCACert(NURA_BACKEND_ROOT_CA);
        started = http.begin(secureClient, url);
#else
        NURA_ERROR("CLOUD",
                   "https needs a root certificate; build with NURA_BACKEND_ROOT_CA");
        return -1;
#endif
    } else {
        started = http.begin(plainClient, url);
    }
    if (!started) {
        NURA_ERROR("CLOUD", "could not start the request");
        return -1;
    }

    http.addHeader("Content-Type", "application/json");
    if (bearerToken.length() > 0) {
        http.addHeader("Authorization", "Bearer " + bearerToken);
    }

    const int status = http.POST(body);
    if (status > 0) {
        responseOut = http.getString();
    }
    http.end();
    return status;
}

//: One GET, for the presentation fetch. Separate from ``post`` rather than a
//: flag on it: the two have different bodies, different failure meanings and
//: different logging, and one function with a verb argument would have made
//: the 204 case harder to read.
int get(const String& url, const String& bearerToken, String& responseOut) {
    if (!isAcceptableUrl(url)) {
        NURA_ERROR("CLOUD", "refusing to use an insecure backend address");
        return -1;
    }

    HTTPClient http;
    http.setTimeout(protocol::HTTP_TIMEOUT_MS);
    http.setConnectTimeout(protocol::HTTP_TIMEOUT_MS);

    bool started = false;
    WiFiClientSecure secureClient;
    WiFiClient plainClient;
    if (isHttps(url)) {
#ifdef NURA_BACKEND_ROOT_CA
        secureClient.setCACert(NURA_BACKEND_ROOT_CA);
        started = http.begin(secureClient, url);
#else
        NURA_ERROR("CLOUD",
                   "https needs a root certificate; build with NURA_BACKEND_ROOT_CA");
        return -1;
#endif
    } else {
        started = http.begin(plainClient, url);
    }
    if (!started) {
        NURA_ERROR("CLOUD", "could not start the request");
        return -1;
    }

    if (bearerToken.length() > 0) {
        http.addHeader("Authorization", "Bearer " + bearerToken);
    }

    const int status = http.GET();
    if (status > 0 && status != 204) {
        responseOut = http.getString();
    }
    http.end();
    return status;
}

protocol::ProvisioningError claimErrorFor(int status, const String& code) {
    if (code == "already_claimed") return protocol::ProvisioningError::ALREADY_CLAIMED;
    if (code == "identity_mismatch") return protocol::ProvisioningError::IDENTITY_MISMATCH;
    if (code == "provisioning_token_invalid") {
        return protocol::ProvisioningError::REGISTRATION_REJECTED;
    }
    if (status <= 0) return protocol::ProvisioningError::BACKEND_UNREACHABLE;
    if (status >= 500) return protocol::ProvisioningError::BACKEND_UNREACHABLE;
    return protocol::ProvisioningError::REGISTRATION_REJECTED;
}

}  // namespace

bool isAcceptableUrl(const String& baseUrl) {
    if (baseUrl.length() == 0) return false;
    if (isHttps(baseUrl)) return true;
#if NURA_ALLOW_INSECURE_HTTP
    return baseUrl.startsWith("http://");
#else
    return false;
#endif
}

ClaimResult claim(const String& baseUrl, const String& provisioningToken) {
    ClaimResult result;

    JsonDocument request;
    request["hardware_id"] = identity::hardwareId();
    request["provisioning_token"] = provisioningToken;
    request["bootstrap_secret"] = identity::bootstrapSecret();
    request["firmware_version"] = NURA_FIRMWARE_VERSION;
    String body;
    serializeJson(request, body);

    // A few attempts with a growing pause, never a tight loop
    // (PRD 2, section 51).
    uint32_t backoffMs = 2000;
    for (uint8_t attempt = 1; attempt <= protocol::CLAIM_ATTEMPTS; attempt += 1) {
        NURA_INFO("CLOUD", "registering device (attempt %u)", static_cast<unsigned>(attempt));
        String response;
        const int status = post(baseUrl + CLAIM_PATH, body, "", response);

        if (status == 200 || status == 201) {
            JsonDocument document;
            if (deserializeJson(document, response) == DeserializationError::Ok) {
                result.ok = true;
                result.deviceId = document["device_id"] | "";
                result.deviceToken = document["device_token"] | "";
                result.heartbeatIntervalSeconds = document["heartbeat_interval_seconds"] | 30;
                NURA_INFO("CLOUD", "registered as device %s", result.deviceId.c_str());
                // The response holds the device token: do not keep the raw
                // body around any longer than this.
                response = "";
                body = "";
                return result;
            }
            NURA_ERROR("CLOUD", "registration response could not be read");
        }

        String code;
        if (status > 0) {
            JsonDocument document;
            if (deserializeJson(document, response) == DeserializationError::Ok) {
                code = document["detail"]["code"] | "";
            }
        }
        result.error = claimErrorFor(status, code);
        NURA_ERROR("CLOUD", "registration refused (status %d, code %s)", status,
                   code.length() > 0 ? code.c_str() : "none");

        // A refusal about identity or ownership will not change on a retry.
        if (result.error == protocol::ProvisioningError::ALREADY_CLAIMED ||
            result.error == protocol::ProvisioningError::IDENTITY_MISMATCH ||
            result.error == protocol::ProvisioningError::REGISTRATION_REJECTED) {
            break;
        }
        if (attempt < protocol::CLAIM_ATTEMPTS) {
            delay(backoffMs);
            backoffMs *= 2;
        }
    }

    body = "";
    return result;
}

HeartbeatResult heartbeat(const String& baseUrl, const String& deviceToken,
                          bool introductionPlayed) {
    HeartbeatResult result;

    JsonDocument request;
    request["firmware_version"] = NURA_FIRMWARE_VERSION;
    request["introduction_played"] = introductionPlayed;
    String body;
    serializeJson(request, body);

    String response;
    const int status = post(baseUrl + HEARTBEAT_PATH, body, deviceToken, response);
    if (status == 401 || status == 403) {
        // The backend no longer knows this token: the device was unlinked.
        NURA_ERROR("CLOUD", "heartbeat was rejected; this robot is no longer linked");
        result.unauthorised = true;
        return result;
    }
    if (status != 200) {
        NURA_ERROR("CLOUD", "heartbeat failed (status %d)", status);
        return result;
    }

    JsonDocument document;
    if (deserializeJson(document, response) != DeserializationError::Ok) {
        NURA_ERROR("CLOUD", "heartbeat response could not be read");
        return result;
    }
    result.ok = true;
    result.heartbeatIntervalSeconds = document["heartbeat_interval_seconds"] | 30;
    result.introduce = document["introduce"] | false;
    // PRD 11, section 58. Absent on a backend older than PRD 11, which
    // defaults to false and means the robot simply never fetches.
    result.presentationPending = document["presentation_pending"] | false;
    return result;
}

// --- PRD 11: capabilities, presentations and acknowledgements ---------------

bool reportCapabilities(const String& baseUrl, const String& deviceToken,
                        const CapabilityReport& report, const char* source) {
    JsonDocument request;
    JsonObject capabilities = request["capabilities"].to<JsonObject>();
    for (uint8_t index = 0; index < report.count; index += 1) {
        capabilities[report.keys[index]] = report.states[index];
    }
    request["source"] = source;
    request["firmware_version"] = NURA_FIRMWARE_VERSION;
    String body;
    serializeJson(request, body);

    String response;
    const int status =
        post(baseUrl + presentation::PATH_CAPABILITIES, body, deviceToken, response);
    if (status != 200) {
        NURA_ERROR("PRES", "capability report refused (status %d)", status);
        return false;
    }
    NURA_INFO("PRES", "reported %u capabilities",
              static_cast<unsigned>(report.count));
    return true;
}

PresentationResult fetchPresentation(const String& baseUrl, const String& deviceToken) {
    PresentationResult result;
    String response;
    const int status = get(baseUrl + presentation::PATH_NEXT, deviceToken, response);

    if (status == 204) {
        // Nothing to show. Not a failure, and the common case.
        result.ok = true;
        result.empty = true;
        return result;
    }
    if (status != 200) {
        NURA_ERROR("PRES", "could not collect a presentation (status %d)", status);
        return result;
    }
    result.ok = true;
    result.body = response;
    return result;
}

bool acknowledgePresentation(const String& baseUrl, const String& deviceToken,
                             const String& presentationId, presentation::Ack ack,
                             const char* failureCode) {
    JsonDocument request;
    request["state"] = presentation::ackName(ack);
    if (failureCode != nullptr) {
        request["failure_code"] = failureCode;
    }
    String body;
    serializeJson(request, body);

    const String url = baseUrl + presentation::PATH_ACK_PREFIX + presentationId +
                       presentation::PATH_ACK_SUFFIX;
    String response;
    const int status = post(url, body, deviceToken, response);
    if (status != 200) {
        NURA_ERROR("PRES", "acknowledgement refused (status %d)", status);
        return false;
    }
    // The state is logged; the presentation id is not. An id is not sensitive,
    // but a log line pairing one with a type is the beginning of a history of
    // somebody's reminders (section 67).
    NURA_DEBUG("PRES", "acknowledged as %s", presentation::ackName(ack));
    return true;
}

}  // namespace nura::backend
