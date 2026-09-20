// Nura provisioning protocol, version 1 -- firmware side.
//
// The contract is docs/device/provisioning-protocol.md. The same values are
// defined for the app in mobile/src/services/provisioning/protocol.ts, and
// mobile/tests/provisioningProtocol.test.ts parses THIS file to make sure the
// two never drift. Keep the `enum class ... : uint8_t` / `constexpr` shapes
// below so that test can still read them.
#pragma once

#include <cstddef>
#include <cstdint>

namespace nura::protocol {

constexpr uint8_t PROTOCOL_VERSION = 1;

// --- GATT ------------------------------------------------------------------
constexpr const char* UUID_SERVICE = "3326ea00-822c-4b86-884f-74b2d9c77b2f";
constexpr const char* UUID_DEVICE_INFO = "3326ea01-822c-4b86-884f-74b2d9c77b2f";
constexpr const char* UUID_PAIRING = "3326ea02-822c-4b86-884f-74b2d9c77b2f";
constexpr const char* UUID_WIFI_CONFIG = "3326ea03-822c-4b86-884f-74b2d9c77b2f";
constexpr const char* UUID_COMMAND = "3326ea04-822c-4b86-884f-74b2d9c77b2f";
constexpr const char* UUID_STATUS = "3326ea05-822c-4b86-884f-74b2d9c77b2f";

constexpr const char* BLE_NAME_PREFIX = "Nura-";
constexpr const char* HARDWARE_ID_PREFIX = "NURA-";
constexpr const char* MODEL_NAME = "Nura";

// --- PAIRING messages ------------------------------------------------------
enum class PairingMessage : uint8_t {
  PAKE_START = 0x01,
  PAKE_RESPONSE = 0x02,
  PAKE_CONFIRM = 0x03,
  PAIRING_RESULT = 0x04,
};

enum class PairingResult : uint8_t {
  VERIFIED = 0x00,
  WRONG_CODE = 0x01,
  CODE_EXPIRED = 0x02,
  TOO_MANY_ATTEMPTS = 0x03,
  MALFORMED = 0x04,
  NOT_PAIRING = 0x05,
};

// --- COMMAND ---------------------------------------------------------------
enum class Command : uint8_t {
  CONNECT_WIFI = 0x01,
  RETRY_WIFI = 0x02,
  CLEAR_WIFI = 0x03,
  FINISH = 0x04,
};

// --- STATUS ----------------------------------------------------------------
enum class ProvisioningState : uint8_t {
  WAITING = 0x00,
  VERIFIED = 0x01,
  RECEIVED_CREDENTIALS = 0x02,
  WIFI_CONNECTING = 0x03,
  WIFI_CONNECTED = 0x04,
  REGISTERING = 0x05,
  REGISTERED = 0x06,
  FAILED = 0x07,
};

enum class ProvisioningError : uint8_t {
  NONE = 0x00,
  WIFI_AUTH_FAILED = 0x01,
  WIFI_NOT_FOUND = 0x02,
  WIFI_TIMEOUT = 0x03,
  WIFI_UNSUPPORTED = 0x04,
  BACKEND_UNREACHABLE = 0x05,
  REGISTRATION_REJECTED = 0x06,
  ALREADY_CLAIMED = 0x07,
  IDENTITY_MISMATCH = 0x08,
  INVALID_PAYLOAD = 0x09,
  NOT_VERIFIED = 0x0A,
  NO_CREDENTIALS = 0x0B,
  UNKNOWN_ERROR = 0xFF,
};

// --- SPAKE2 (RFC 9382, P256-SHA256-HKDF-HMAC) ------------------------------
constexpr const char* PAKE_IDENTITY_APP = "nura-app";
constexpr const char* PAKE_AAD = "nura-provisioning-v1";
constexpr const char* PAKE_W_DOMAIN = "nura-pake-w-v1";
constexpr const char* WIFI_KEY_INFO = "nura wifi config v1";

constexpr size_t POINT_LENGTH = 65;     // uncompressed SEC1
constexpr size_t MAC_LENGTH = 32;       // HMAC-SHA256
constexpr size_t NONCE_LENGTH = 12;     // AES-GCM
constexpr size_t TAG_LENGTH = 16;       // AES-GCM
constexpr size_t WIFI_KEY_LENGTH = 16;  // AES-128
constexpr uint8_t WIFI_CONFIG_VERSION = 1;
constexpr size_t MAX_ATTRIBUTE_LENGTH = 512;
//: Big enough for the 98-byte PAKE response in a single notification. The app
//: requests the same value on Android; iOS negotiates its own.
constexpr uint16_t BLE_PREFERRED_MTU = 247;

// --- Limits and timings (docs section 4, 6 and 8) --------------------------
constexpr size_t CODE_DIGITS = 6;
constexpr uint32_t CODE_TTL_MS = 120000;
constexpr uint8_t MAX_FAILED_ATTEMPTS_PER_CONNECTION = 3;
constexpr uint8_t MAX_FAILED_ATTEMPTS_PER_WINDOW = 10;
constexpr uint32_t PAIRING_WINDOW_MS = 300000;
constexpr uint32_t PAIRING_GRACE_AFTER_REGISTER_MS = 60000;
constexpr uint32_t PAIRING_BUTTON_HOLD_MS = 3000;
constexpr uint32_t FACTORY_RESET_HOLD_MS = 10000;
constexpr uint32_t WIFI_ATTEMPT_TIMEOUT_MS = 20000;
constexpr uint8_t WIFI_ATTEMPTS = 2;
constexpr uint8_t CLAIM_ATTEMPTS = 3;
constexpr uint32_t HTTP_TIMEOUT_MS = 10000;
constexpr uint32_t DEFAULT_HEARTBEAT_INTERVAL_MS = 30000;

// --- Wi-Fi credential rules ------------------------------------------------
constexpr size_t SSID_MAX_BYTES = 32;
constexpr size_t PASSWORD_MIN_LENGTH = 8;
constexpr size_t PASSWORD_MAX_LENGTH = 63;

}  // namespace nura::protocol
