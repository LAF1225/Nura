#include "ble_provisioning.h"

#include <ArduinoJson.h>
#include <NimBLEDevice.h>
#include <esp_random.h>
#include <string.h>

#include "device_identity.h"
#include "display.h"
#include "log.h"
#include "spake2.h"

namespace nura::ble {
namespace {

using protocol::PairingMessage;
using protocol::PairingResult;
using protocol::ProvisioningError;
using protocol::ProvisioningState;

Delegate* g_delegate = nullptr;
NimBLEServer* g_server = nullptr;
NimBLECharacteristic* g_deviceInfo = nullptr;
NimBLECharacteristic* g_pairing = nullptr;
NimBLECharacteristic* g_status = nullptr;

bool g_pairingMode = false;
bool g_connected = false;
bool g_verified = false;
bool g_provisioned = false;
bool g_registered = false;
uint32_t g_pairingModeEndsAt = 0;

// --- pairing session (valid only while one phone is connected) ---
String g_code;
uint32_t g_codeExpiresAt = 0;
uint8_t g_attemptsThisConnection = 0;
uint8_t g_attemptsThisWindow = 0;
uint8_t g_expectedConfirmation[protocol::MAC_LENGTH];
bool g_awaitingConfirmation = false;
uint8_t g_wifiKey[protocol::WIFI_KEY_LENGTH];

// --- work handed from the BLE task to the main loop ---
portMUX_TYPE g_mux = portMUX_INITIALIZER_UNLOCKED;
uint8_t g_pendingPairing[1 + protocol::POINT_LENGTH];
size_t g_pendingPairingLength = 0;
uint8_t g_pendingConfig[protocol::MAX_ATTRIBUTE_LENGTH];
size_t g_pendingConfigLength = 0;
uint8_t g_pendingCommand = 0;
bool g_hasPendingCommand = false;

void forgetSession() {
    g_verified = false;
    g_awaitingConfirmation = false;
    g_attemptsThisConnection = 0;
    memset(g_expectedConfirmation, 0, sizeof(g_expectedConfirmation));
    memset(g_wifiKey, 0, sizeof(g_wifiKey));
}

//: Six digits from the hardware RNG, rejection-sampled so every code is
//: equally likely. Never a fixed factory PIN (PRD 2, section 16).
String generateCode() {
    uint32_t value = 0;
    do {
        value = esp_random();
    } while (value >= 4294000000u);  // largest multiple of 1e6 below 2^32
    value %= 1000000u;

    char digits[protocol::CODE_DIGITS + 1];
    snprintf(digits, sizeof(digits), "%06u", static_cast<unsigned>(value));
    return String(digits);
}

void showNewCode() {
    g_code = generateCode();
    g_codeExpiresAt = millis() + protocol::CODE_TTL_MS;
    g_awaitingConfirmation = false;
    display::showPairingCode(g_code);
}

void notifyPairing(const uint8_t* payload, size_t length) {
    if (g_pairing == nullptr) return;
    g_pairing->notify(payload, length);
}

void notifyResult(PairingResult result) {
    const uint8_t message[2] = {static_cast<uint8_t>(PairingMessage::PAIRING_RESULT),
                                static_cast<uint8_t>(result)};
    notifyPairing(message, sizeof(message));
}

String deviceInfoJson() {
    JsonDocument document;
    document["protocol"] = protocol::PROTOCOL_VERSION;
    document["hardware_id"] = identity::hardwareId();
    document["model"] = protocol::MODEL_NAME;
    document["firmware_version"] = NURA_FIRMWARE_VERSION;
    document["provisioned"] = g_provisioned;
    document["registered"] = g_registered;
    String out;
    serializeJson(document, out);
    return out;
}

void refreshDeviceInfo() {
    if (g_deviceInfo == nullptr) return;
    const String json = deviceInfoJson();
    g_deviceInfo->setValue(reinterpret_cast<const uint8_t*>(json.c_str()), json.length());
}

class ServerCallbacks : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* /*server*/, NimBLEConnInfo& /*info*/) override {
        g_connected = true;
        forgetSession();
        // A fresh code for every phone that connects.
        showNewCode();
        publishStatus(ProvisioningState::WAITING);
        NURA_INFO("PAIR", "app connected");
    }

    void onDisconnect(NimBLEServer* /*server*/, NimBLEConnInfo& /*info*/, int reason) override {
        g_connected = false;
        forgetSession();
        NURA_INFO("PAIR", "app disconnected (reason %d)", reason);
        if (g_pairingMode) {
            display::showPairingReady(identity::bleName());
            NimBLEDevice::getAdvertising()->start();
        }
    }
};

class PairingCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* characteristic, NimBLEConnInfo& /*info*/) override {
        const NimBLEAttValue value = characteristic->getValue();
        if (value.length() == 0 || value.length() > sizeof(g_pendingPairing)) {
            notifyResult(PairingResult::MALFORMED);
            return;
        }
        // Copied out and processed in loop(): the exchange takes long enough
        // that doing it here would stall the BLE host task.
        portENTER_CRITICAL(&g_mux);
        memcpy(g_pendingPairing, value.data(), value.length());
        g_pendingPairingLength = value.length();
        portEXIT_CRITICAL(&g_mux);
    }
};

class WifiConfigCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* characteristic, NimBLEConnInfo& /*info*/) override {
        const NimBLEAttValue value = characteristic->getValue();
        if (!g_verified) {
            // Nothing is decrypted before verification (PRD 2, section 15).
            publishStatus(ProvisioningState::FAILED, ProvisioningError::NOT_VERIFIED);
            return;
        }
        if (value.length() == 0 || value.length() > sizeof(g_pendingConfig)) {
            publishStatus(ProvisioningState::FAILED, ProvisioningError::INVALID_PAYLOAD);
            return;
        }
        portENTER_CRITICAL(&g_mux);
        memcpy(g_pendingConfig, value.data(), value.length());
        g_pendingConfigLength = value.length();
        portEXIT_CRITICAL(&g_mux);
    }
};

class CommandCallbacks : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic* characteristic, NimBLEConnInfo& /*info*/) override {
        const NimBLEAttValue value = characteristic->getValue();
        if (!g_verified) {
            publishStatus(ProvisioningState::FAILED, ProvisioningError::NOT_VERIFIED);
            return;
        }
        if (value.length() != 1) return;
        portENTER_CRITICAL(&g_mux);
        g_pendingCommand = value.data()[0];
        g_hasPendingCommand = true;
        portEXIT_CRITICAL(&g_mux);
    }
};

void handlePakeStart(const uint8_t* message, size_t length) {
    if (!g_pairingMode) {
        notifyResult(PairingResult::NOT_PAIRING);
        return;
    }
    if (length != 1 + protocol::POINT_LENGTH) {
        notifyResult(PairingResult::MALFORMED);
        return;
    }
    if (g_attemptsThisWindow >= protocol::MAX_FAILED_ATTEMPTS_PER_WINDOW) {
        NURA_ERROR("PAIR", "too many attempts; leaving pairing mode");
        notifyResult(PairingResult::TOO_MANY_ATTEMPTS);
        stopPairingMode();
        return;
    }
    if (g_attemptsThisConnection >= protocol::MAX_FAILED_ATTEMPTS_PER_CONNECTION) {
        notifyResult(PairingResult::TOO_MANY_ATTEMPTS);
        if (g_server != nullptr) {
            g_server->disconnect(0);
        }
        return;
    }
    if (millis() > g_codeExpiresAt) {
        NURA_INFO("PAIR", "code expired; showing a new one");
        showNewCode();
        notifyResult(PairingResult::CODE_EXPIRED);
        return;
    }

    // Counted as an attempt now; cleared only by a correct confirmation.
    g_attemptsThisConnection += 1;
    g_attemptsThisWindow += 1;

    spake2::Session session;
    if (!spake2::respond(identity::hardwareId(), g_code, message + 1, protocol::POINT_LENGTH,
                         session)) {
        NURA_ERROR("PAIR", "pairing message could not be processed");
        notifyResult(PairingResult::MALFORMED);
        return;
    }

    memcpy(g_expectedConfirmation, session.cA, sizeof(g_expectedConfirmation));
    secure_channel::deriveWifiKey(session.ke, g_wifiKey);
    g_awaitingConfirmation = true;

    uint8_t reply[1 + protocol::POINT_LENGTH + protocol::MAC_LENGTH];
    reply[0] = static_cast<uint8_t>(PairingMessage::PAKE_RESPONSE);
    memcpy(reply + 1, session.pB, protocol::POINT_LENGTH);
    memcpy(reply + 1 + protocol::POINT_LENGTH, session.cB, protocol::MAC_LENGTH);
    notifyPairing(reply, sizeof(reply));

    memset(&session, 0, sizeof(session));
}

void handlePakeConfirm(const uint8_t* message, size_t length) {
    if (!g_awaitingConfirmation || length != 1 + protocol::MAC_LENGTH) {
        notifyResult(PairingResult::MALFORMED);
        return;
    }
    g_awaitingConfirmation = false;

    if (!spake2::constantTimeEquals(message + 1, g_expectedConfirmation, protocol::MAC_LENGTH)) {
        NURA_INFO("PAIR", "verification failed");
        memset(g_wifiKey, 0, sizeof(g_wifiKey));
        notifyResult(PairingResult::WRONG_CODE);
        if (g_attemptsThisConnection >= protocol::MAX_FAILED_ATTEMPTS_PER_CONNECTION &&
            g_server != nullptr) {
            g_server->disconnect(0);
        }
        return;
    }

    g_verified = true;
    g_attemptsThisConnection = 0;
    NURA_INFO("PAIR", "verification accepted");
    notifyResult(PairingResult::VERIFIED);
    publishStatus(ProvisioningState::VERIFIED);
    display::showStatus("Setting up");
}

void handleConfigPayload(const uint8_t* payload, size_t length) {
    secure_channel::WifiConfig config;
    if (!secure_channel::openWifiConfig(g_wifiKey, identity::hardwareId(), payload, length,
                                        config)) {
        publishStatus(ProvisioningState::FAILED, ProvisioningError::INVALID_PAYLOAD);
        return;
    }
    NURA_INFO("WIFI", "credentials received for network %s", config.ssid.c_str());
    publishStatus(ProvisioningState::RECEIVED_CREDENTIALS);
    if (g_delegate != nullptr) {
        g_delegate->onCredentialsReceived(config);
    }
    // The caller keeps what it needs; this copy must not linger.
    config = secure_channel::WifiConfig{};
}

void handleCommand(uint8_t command) {
    if (g_delegate == nullptr) return;
    switch (static_cast<protocol::Command>(command)) {
        case protocol::Command::CONNECT_WIFI:
            g_delegate->onConnectWifi();
            break;
        case protocol::Command::RETRY_WIFI:
            g_delegate->onRetryWifi();
            break;
        case protocol::Command::CLEAR_WIFI:
            g_delegate->onClearWifi();
            break;
        case protocol::Command::FINISH:
            g_delegate->onFinish();
            break;
        default:
            NURA_ERROR("PAIR", "unknown command 0x%02X", command);
            break;
    }
}

}  // namespace

void begin(Delegate* delegate) {
    g_delegate = delegate;

    NimBLEDevice::init(identity::bleName().c_str());
    // Enough for the 98-byte PAKE response in one notification.
    NimBLEDevice::setMTU(protocol::BLE_PREFERRED_MTU);

    g_server = NimBLEDevice::createServer();
    g_server->setCallbacks(new ServerCallbacks());

    NimBLEService* service = g_server->createService(protocol::UUID_SERVICE);

    g_deviceInfo = service->createCharacteristic(protocol::UUID_DEVICE_INFO, NIMBLE_PROPERTY::READ,
                                                 protocol::MAX_ATTRIBUTE_LENGTH);
    g_pairing = service->createCharacteristic(
        protocol::UUID_PAIRING, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::NOTIFY,
        protocol::MAX_ATTRIBUTE_LENGTH);
    g_pairing->setCallbacks(new PairingCallbacks());

    NimBLECharacteristic* wifiConfig = service->createCharacteristic(
        protocol::UUID_WIFI_CONFIG, NIMBLE_PROPERTY::WRITE, protocol::MAX_ATTRIBUTE_LENGTH);
    wifiConfig->setCallbacks(new WifiConfigCallbacks());

    NimBLECharacteristic* command =
        service->createCharacteristic(protocol::UUID_COMMAND, NIMBLE_PROPERTY::WRITE, 1);
    command->setCallbacks(new CommandCallbacks());

    g_status = service->createCharacteristic(
        protocol::UUID_STATUS, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY, 2);

    refreshDeviceInfo();
    publishStatus(ProvisioningState::WAITING);
    service->start();

    NimBLEAdvertising* advertising = NimBLEDevice::getAdvertising();
    advertising->addServiceUUID(protocol::UUID_SERVICE);
    // The service UUID alone nearly fills the advertising packet, so the name
    // goes in the scan response.
    NimBLEAdvertisementData scanResponse;
    scanResponse.setName(identity::bleName().c_str());
    advertising->setScanResponseData(scanResponse);
    advertising->enableScanResponse(true);

    NURA_INFO("PAIR", "provisioning service ready");
}

void startPairingMode(uint32_t windowMs) {
    if (g_pairingMode) return;
    g_pairingMode = true;
    g_attemptsThisWindow = 0;
    g_pairingModeEndsAt = windowMs == 0 ? 0 : millis() + windowMs;
    NimBLEDevice::getAdvertising()->start();
    display::showPairingReady(identity::bleName());
    NURA_INFO("PAIR", "BLE advertising started as %s", identity::bleName().c_str());
}

void stopPairingMode() {
    if (!g_pairingMode) return;
    g_pairingMode = false;
    g_pairingModeEndsAt = 0;
    NimBLEDevice::getAdvertising()->stop();
    forgetSession();
    if (g_connected && g_server != nullptr) {
        g_server->disconnect(0);
    }
    NURA_INFO("PAIR", "BLE advertising stopped");
}

bool isPairingMode() {
    return g_pairingMode;
}

bool isConnected() {
    return g_connected;
}

bool isVerified() {
    return g_verified;
}

void publishStatus(ProvisioningState state, ProvisioningError error) {
    if (g_status == nullptr) return;
    const uint8_t payload[2] = {static_cast<uint8_t>(state), static_cast<uint8_t>(error)};
    g_status->setValue(payload, sizeof(payload));
    g_status->notify(payload, sizeof(payload));
}

void setProvisioningFlags(bool provisioned, bool registered) {
    g_provisioned = provisioned;
    g_registered = registered;
    refreshDeviceInfo();
}

void loop() {
    uint8_t pairingMessage[sizeof(g_pendingPairing)];
    size_t pairingLength = 0;
    uint8_t configPayload[sizeof(g_pendingConfig)];
    size_t configLength = 0;
    uint8_t command = 0;
    bool hasCommand = false;

    portENTER_CRITICAL(&g_mux);
    if (g_pendingPairingLength > 0) {
        pairingLength = g_pendingPairingLength;
        memcpy(pairingMessage, g_pendingPairing, pairingLength);
        g_pendingPairingLength = 0;
    }
    if (g_pendingConfigLength > 0) {
        configLength = g_pendingConfigLength;
        memcpy(configPayload, g_pendingConfig, configLength);
        g_pendingConfigLength = 0;
    }
    if (g_hasPendingCommand) {
        command = g_pendingCommand;
        hasCommand = true;
        g_hasPendingCommand = false;
    }
    portEXIT_CRITICAL(&g_mux);

    if (pairingLength > 0) {
        switch (static_cast<PairingMessage>(pairingMessage[0])) {
            case PairingMessage::PAKE_START:
                handlePakeStart(pairingMessage, pairingLength);
                break;
            case PairingMessage::PAKE_CONFIRM:
                handlePakeConfirm(pairingMessage, pairingLength);
                break;
            default:
                notifyResult(PairingResult::MALFORMED);
                break;
        }
    }

    if (configLength > 0) {
        handleConfigPayload(configPayload, configLength);
        memset(configPayload, 0, sizeof(configPayload));
    }

    if (hasCommand) {
        handleCommand(command);
    }

    const uint32_t now = millis();
    // An unused code is replaced rather than left on screen indefinitely.
    if (g_connected && !g_verified && now > g_codeExpiresAt) {
        showNewCode();
    }
    // A set-up robot does not stay discoverable (PRD 2, section 6).
    if (g_pairingMode && g_pairingModeEndsAt != 0 && now > g_pairingModeEndsAt && !g_connected) {
        NURA_INFO("PAIR", "pairing window closed");
        stopPairingMode();
    }
}

}  // namespace nura::ble
