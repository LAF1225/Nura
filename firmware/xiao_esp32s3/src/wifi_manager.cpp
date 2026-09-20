#include "wifi_manager.h"

#include <WiFi.h>

#include "log.h"

namespace nura::wifi {
namespace {

//: Looks for the network before trying to join it. This is what lets the app
//: say "Nura couldn't see that network -- it needs 2.4 GHz" instead of a bare
//: timeout, since the ESP32 cannot see 5 GHz networks at all.
//: A hidden network will not appear, so "not seen" is not treated as fatal.
struct ScanResult {
    bool seen = false;
    bool supported = true;
};

ScanResult lookFor(const String& ssid) {
    ScanResult result;
    const int found = WiFi.scanNetworks(/*async=*/false, /*show_hidden=*/true);
    for (int index = 0; index < found; index += 1) {
        if (WiFi.SSID(index) != ssid) continue;
        result.seen = true;
        const wifi_auth_mode_t mode = WiFi.encryptionType(index);
        // Enterprise networks need credentials this flow does not collect.
        result.supported = mode != WIFI_AUTH_WPA2_ENTERPRISE;
        break;
    }
    WiFi.scanDelete();
    return result;
}

//: Maps the ESP32's disconnect reason onto something a person can act on.
Outcome outcomeForReason(uint8_t reason) {
    switch (reason) {
        case WIFI_REASON_AUTH_FAIL:
        case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
        case WIFI_REASON_HANDSHAKE_TIMEOUT:
        case WIFI_REASON_AUTH_EXPIRE:
            return Outcome::AUTH_FAILED;
        case WIFI_REASON_NO_AP_FOUND:
            return Outcome::NOT_FOUND;
        case WIFI_REASON_ASSOC_FAIL:
        case WIFI_REASON_UNSUPP_RSN_IE_VERSION:
            return Outcome::UNSUPPORTED;
        default:
            return Outcome::TIMEOUT;
    }
}

volatile uint8_t g_lastDisconnectReason = 0;

void onWifiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
        g_lastDisconnectReason = info.wifi_sta_disconnected.reason;
    }
}

}  // namespace

void begin() {
    WiFi.mode(WIFI_STA);
    // Nura decides when to reconnect; the SDK retrying underneath would make
    // the state machine lie about what is happening.
    WiFi.setAutoReconnect(false);
    WiFi.onEvent(onWifiEvent);
}

Outcome connect(const settings::WifiCredentials& credentials) {
    const ScanResult scan = lookFor(credentials.ssid);
    if (scan.seen && !scan.supported) {
        NURA_ERROR("WIFI", "network %s uses an unsupported security type",
                   credentials.ssid.c_str());
        return Outcome::UNSUPPORTED;
    }

    for (uint8_t attempt = 1; attempt <= protocol::WIFI_ATTEMPTS; attempt += 1) {
        NURA_INFO("WIFI", "connecting to SSID %s (attempt %u)", credentials.ssid.c_str(),
                  static_cast<unsigned>(attempt));
        g_lastDisconnectReason = 0;
        WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
        // The password is passed straight to the driver and never logged.
        WiFi.begin(credentials.ssid.c_str(), credentials.password.c_str());

        const uint32_t deadline = millis() + protocol::WIFI_ATTEMPT_TIMEOUT_MS;
        while (millis() < deadline) {
            const wl_status_t status = WiFi.status();
            if (status == WL_CONNECTED) {
                NURA_INFO("WIFI", "connected, ip %s", WiFi.localIP().toString().c_str());
                return Outcome::CONNECTED;
            }
            if (g_lastDisconnectReason != 0) {
                const Outcome outcome = outcomeForReason(g_lastDisconnectReason);
                NURA_ERROR("WIFI", "connection failed (reason %u)",
                           static_cast<unsigned>(g_lastDisconnectReason));
                // A refused password will be refused again; say so now.
                if (outcome == Outcome::AUTH_FAILED || outcome == Outcome::UNSUPPORTED) {
                    WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
                    return outcome;
                }
                break;
            }
            delay(100);
        }
    }

    WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
    if (!scan.seen) {
        NURA_ERROR("WIFI", "network %s was not found", credentials.ssid.c_str());
        return Outcome::NOT_FOUND;
    }
    NURA_ERROR("WIFI", "timed out joining %s", credentials.ssid.c_str());
    return Outcome::TIMEOUT;
}

void disconnect() {
    WiFi.disconnect(/*wifioff=*/false, /*eraseap=*/true);
}

bool isConnected() {
    return WiFi.status() == WL_CONNECTED;
}

int rssi() {
    return WiFi.RSSI();
}

protocol::ProvisioningError errorFor(Outcome outcome) {
    switch (outcome) {
        case Outcome::AUTH_FAILED:
            return protocol::ProvisioningError::WIFI_AUTH_FAILED;
        case Outcome::NOT_FOUND:
            return protocol::ProvisioningError::WIFI_NOT_FOUND;
        case Outcome::UNSUPPORTED:
            return protocol::ProvisioningError::WIFI_UNSUPPORTED;
        case Outcome::TIMEOUT:
            return protocol::ProvisioningError::WIFI_TIMEOUT;
        case Outcome::CONNECTED:
            return protocol::ProvisioningError::NONE;
    }
    return protocol::ProvisioningError::UNKNOWN_ERROR;
}

}  // namespace nura::wifi
