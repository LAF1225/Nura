// Nura robot firmware -- XIAO ESP32-S3 (PRD 2).
//
// Boot:
//   never set up      -> pairing mode, advertising until it is set up
//   set up            -> join the stored Wi-Fi and start heartbeats
//   button held 3 s   -> pairing mode again, to change Wi-Fi or re-link
//   button held 10 s  -> factory reset (local only; nothing in the cloud)
//
// The connectivity state machine below is deliberately explicit rather than a
// set of booleans (PRD 2, section 26).
#include <Arduino.h>

#include "audio.h"
#include "backend_client.h"
#include "ble_provisioning.h"
#include "board_config.h"
#include "device_identity.h"
#include "display.h"
#include "log.h"
#include "protocol.h"
#include "secure_channel.h"
#include "settings_store.h"
#include "spake2.h"
#include "wifi_manager.h"

namespace {

using nura::protocol::ProvisioningError;
using nura::protocol::ProvisioningState;

enum class Connectivity {
    UNPROVISIONED,
    CREDENTIALS_RECEIVED,
    WIFI_CONNECTING,
    WIFI_CONNECTED,
    BACKEND_REGISTERING,
    ONLINE,
    ERROR,
};

Connectivity g_state = Connectivity::UNPROVISIONED;

//: Credentials live here only until they have been proven to work.
nura::secure_channel::WifiConfig g_staged;
bool g_hasStaged = false;

uint32_t g_heartbeatIntervalMs = nura::protocol::DEFAULT_HEARTBEAT_INTERVAL_MS;
uint32_t g_nextHeartbeatAt = 0;
uint32_t g_nextReconnectAt = 0;
bool g_introductionPlayed = false;
bool g_introductionPending = false;
//: Set once a claim has succeeded in this session, so the pairing window can
//: close shortly afterwards even if the app never sends FINISH.
uint32_t g_closePairingAt = 0;

void setState(Connectivity state) {
    g_state = state;
}

void publishFlags() {
    nura::ble::setProvisioningFlags(nura::settings::hasWifi(), nura::settings::isRegistered());
}

//: Sends one heartbeat and acts on what comes back.
void sendHeartbeat() {
    const String baseUrl = nura::settings::apiBaseUrl();
    const String token = nura::settings::deviceToken();
    if (baseUrl.length() == 0 || token.length() == 0) return;

    const nura::backend::HeartbeatResult result =
        nura::backend::heartbeat(baseUrl, token, g_introductionPlayed);

    // Only report the introduction once; after that the flag is cleared.
    if (g_introductionPlayed && result.ok) {
        g_introductionPlayed = false;
    }

    if (result.unauthorised) {
        // The account unlinked this robot. Keep the identity, drop the token,
        // and wait for someone to set it up again deliberately.
        nura::settings::clearRegistration();
        publishFlags();
        setState(Connectivity::ERROR);
        nura::display::showStatus("Needs setup");
        return;
    }

    if (!result.ok) {
        // Nothing dramatic: the next heartbeat will try again.
        return;
    }

    g_heartbeatIntervalMs = result.heartbeatIntervalSeconds * 1000;
    if (result.introduce && !g_introductionPending) {
        g_introductionPending = true;
    }
}

void playIntroductionIfAsked() {
    if (!g_introductionPending) return;
    g_introductionPending = false;
    NURA_INFO("UI", "playing the first introduction");
    nura::display::showConnected();
    nura::audio::playIntroduction();
    // Tell the backend on the next heartbeat, so it stops asking.
    g_introductionPlayed = true;
    g_nextHeartbeatAt = millis();
}

//: Wi-Fi, then registration, reporting each step over BLE as it goes.
void runProvisioning(const nura::settings::WifiCredentials& credentials,
                     const String& provisioningToken, const String& apiBaseUrl) {
    setState(Connectivity::WIFI_CONNECTING);
    nura::ble::publishStatus(ProvisioningState::WIFI_CONNECTING);
    nura::display::showStatus("Joining Wi-Fi");

    const nura::wifi::Outcome outcome = nura::wifi::connect(credentials);
    if (outcome != nura::wifi::Outcome::CONNECTED) {
        setState(Connectivity::ERROR);
        nura::ble::publishStatus(ProvisioningState::FAILED, nura::wifi::errorFor(outcome));
        nura::display::showStatus("Wi-Fi failed");
        return;
    }

    setState(Connectivity::WIFI_CONNECTED);
    nura::ble::publishStatus(ProvisioningState::WIFI_CONNECTED);

    // Only now are the credentials worth keeping (PRD 2, section 25).
    nura::settings::saveWifi(credentials);
    if (apiBaseUrl.length() > 0) {
        nura::settings::saveApiBaseUrl(apiBaseUrl);
    }
    publishFlags();

    if (provisioningToken.length() == 0) {
        // Re-joining a network on a robot that is already linked.
        setState(Connectivity::ONLINE);
        nura::ble::publishStatus(ProvisioningState::REGISTERED);
        g_nextHeartbeatAt = millis();
        return;
    }

    setState(Connectivity::BACKEND_REGISTERING);
    nura::ble::publishStatus(ProvisioningState::REGISTERING);
    nura::display::showStatus("Linking account");

    const nura::backend::ClaimResult claim =
        nura::backend::claim(nura::settings::apiBaseUrl(), provisioningToken);
    if (!claim.ok) {
        setState(Connectivity::ERROR);
        nura::ble::publishStatus(ProvisioningState::FAILED, claim.error);
        nura::display::showStatus("Setup failed");
        return;
    }

    nura::settings::saveRegistration(claim.deviceToken, claim.deviceId);
    publishFlags();
    g_heartbeatIntervalMs = claim.heartbeatIntervalSeconds * 1000;
    setState(Connectivity::ONLINE);
    nura::ble::publishStatus(ProvisioningState::REGISTERED);
    nura::display::showConnected();

    // The app now confirms with the backend rather than over BLE; give it a
    // moment to do so, then stop advertising by ourselves.
    g_closePairingAt = millis() + nura::protocol::PAIRING_GRACE_AFTER_REGISTER_MS;
    g_nextHeartbeatAt = millis();
}

class ProvisioningDelegate : public nura::ble::Delegate {
    void onCredentialsReceived(const nura::secure_channel::WifiConfig& config) override {
        g_staged = config;
        g_hasStaged = true;
        setState(Connectivity::CREDENTIALS_RECEIVED);
    }

    void onConnectWifi() override {
        if (!g_hasStaged) {
            nura::ble::publishStatus(ProvisioningState::FAILED, ProvisioningError::NO_CREDENTIALS);
            return;
        }
        runProvisioning({g_staged.ssid, g_staged.password}, g_staged.provisioningToken,
                        g_staged.apiBaseUrl);
    }

    void onRetryWifi() override {
        if (g_hasStaged) {
            onConnectWifi();
            return;
        }
        if (nura::settings::hasWifi()) {
            runProvisioning(nura::settings::wifi(), "", "");
            return;
        }
        nura::ble::publishStatus(ProvisioningState::FAILED, ProvisioningError::NO_CREDENTIALS);
    }

    void onClearWifi() override {
        nura::settings::clearWifi();
        nura::wifi::disconnect();
        g_hasStaged = false;
        g_staged = nura::secure_channel::WifiConfig{};
        setState(Connectivity::UNPROVISIONED);
        publishFlags();
        nura::ble::publishStatus(ProvisioningState::WAITING);
    }

    void onFinish() override {
        NURA_INFO("PAIR", "app finished setup");
        // Whatever happens, the staged password does not stay in RAM.
        g_staged = nura::secure_channel::WifiConfig{};
        g_hasStaged = false;
        nura::ble::stopPairingMode();
        g_closePairingAt = 0;
        if (g_state == Connectivity::ONLINE) {
            nura::display::showConnected();
        }
    }
};

ProvisioningDelegate g_delegate;

//: BOOT held for 3 s enters pairing mode; 10 s is a factory reset.
void handleButton() {
    static uint32_t pressedAt = 0;
    static bool handledPairing = false;

    const bool down = digitalRead(nura::board::PIN_PAIRING_BUTTON) == LOW;
    if (!down) {
        pressedAt = 0;
        handledPairing = false;
        return;
    }

    const uint32_t now = millis();
    if (pressedAt == 0) {
        pressedAt = now;
        return;
    }
    const uint32_t heldFor = now - pressedAt;

    if (heldFor >= nura::protocol::FACTORY_RESET_HOLD_MS) {
        NURA_INFO("CFG", "factory reset requested from the button");
        nura::display::showStatus("Resetting");
        nura::settings::factoryReset();
        delay(500);
        ESP.restart();
    }

    if (!handledPairing && heldFor >= nura::protocol::PAIRING_BUTTON_HOLD_MS) {
        handledPairing = true;
        NURA_INFO("PAIR", "pairing mode requested from the button");
        nura::ble::startPairingMode(nura::protocol::PAIRING_WINDOW_MS);
    }
}

//: Keeps a set-up robot on the network without hammering it.
void maintainWifi() {
    if (g_state != Connectivity::ONLINE && g_state != Connectivity::ERROR) return;
    if (nura::wifi::isConnected()) return;
    if (!nura::settings::hasWifi()) return;

    const uint32_t now = millis();
    if (now < g_nextReconnectAt) return;
    g_nextReconnectAt = now + 30000;

    NURA_INFO("WIFI", "reconnecting to the stored network");
    nura::display::showOffline();
    if (nura::wifi::connect(nura::settings::wifi()) == nura::wifi::Outcome::CONNECTED) {
        setState(Connectivity::ONLINE);
        nura::display::showConnected();
        g_nextHeartbeatAt = now;
    }
}

}  // namespace

// The unit tests bring their own setup()/loop() (see test/), so the firmware's
// own entry points step aside when PlatformIO builds a test.
#ifndef PIO_UNIT_TESTING

void setup() {
    Serial.begin(115200);
    // A moment for the USB serial port to come up, so the first lines are not
    // lost when someone is watching the log.
    delay(300);
    NURA_INFO("BOOT", "Nura firmware %s starting", NURA_FIRMWARE_VERSION);

    pinMode(nura::board::PIN_PAIRING_BUTTON, INPUT_PULLUP);

    nura::identity::begin();
    nura::settings::begin();
    nura::display::begin();
    nura::audio::begin();
    nura::wifi::begin();
    nura::ble::begin(&g_delegate);
    publishFlags();

    const bool setUp = nura::settings::hasWifi() && nura::settings::isRegistered();
    if (!setUp) {
        // First boot, or a robot that never finished setup: advertise until
        // it is set up (PRD 2, section 6).
        setState(Connectivity::UNPROVISIONED);
        nura::ble::startPairingMode(0);
        return;
    }

    if (nura::wifi::connect(nura::settings::wifi()) == nura::wifi::Outcome::CONNECTED) {
        setState(Connectivity::ONLINE);
        nura::display::showConnected();
        g_nextHeartbeatAt = millis();
    } else {
        // Not bricked: hold the button to re-provision (PRD 2, section 44).
        setState(Connectivity::ERROR);
        nura::display::showOffline();
    }
}

void loop() {
    nura::ble::loop();
    handleButton();
    maintainWifi();

    const uint32_t now = millis();
    if (g_state == Connectivity::ONLINE && nura::wifi::isConnected() && now >= g_nextHeartbeatAt) {
        g_nextHeartbeatAt = now + g_heartbeatIntervalMs;
        sendHeartbeat();
    }

    playIntroductionIfAsked();

    if (g_closePairingAt != 0 && now > g_closePairingAt) {
        g_closePairingAt = 0;
        if (nura::ble::isPairingMode() && !nura::ble::isConnected()) {
            nura::ble::stopPairingMode();
        }
    }

    delay(10);
}

#endif  // PIO_UNIT_TESTING
