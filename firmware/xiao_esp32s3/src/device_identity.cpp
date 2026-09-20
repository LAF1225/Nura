#include "device_identity.h"

#include <Preferences.h>
#include <esp_mac.h>
#include <esp_random.h>

#include "log.h"
#include "protocol.h"

namespace nura::identity {
namespace {

//: NVS namespace for identity. Deliberately separate from the settings
//: namespace so a factory reset can clear settings without destroying the
//: identity the backend knows this robot by.
constexpr const char* NVS_NAMESPACE = "nura_id";
constexpr const char* KEY_BOOTSTRAP = "bootstrap";
constexpr size_t BOOTSTRAP_BYTES = 32;

String g_hardwareId;
String g_shortId;
String g_bleName;
String g_bootstrapSecret;

String toHex(const uint8_t* bytes, size_t length) {
    static const char* digits = "0123456789abcdef";
    String out;
    out.reserve(length * 2);
    for (size_t index = 0; index < length; index += 1) {
        out += digits[bytes[index] >> 4];
        out += digits[bytes[index] & 0x0F];
    }
    return out;
}

//: `NURA-` plus the 12 upper-case hex digits of the factory MAC.
String readHardwareId() {
    uint8_t mac[6] = {0};
    esp_err_t status = esp_efuse_mac_get_default(mac);
    if (status != ESP_OK) {
        NURA_ERROR("ID", "could not read the factory MAC (%d)", status);
    }
    String hex = toHex(mac, sizeof(mac));
    hex.toUpperCase();
    return String(protocol::HARDWARE_ID_PREFIX) + hex;
}

//: Loads the bootstrap secret, generating one the first time.
String loadOrCreateBootstrapSecret() {
    Preferences preferences;
    if (!preferences.begin(NVS_NAMESPACE, /*readOnly=*/false)) {
        NURA_ERROR("ID", "could not open identity storage");
        return "";
    }

    String stored = preferences.getString(KEY_BOOTSTRAP, "");
    if (stored.length() == BOOTSTRAP_BYTES * 2) {
        preferences.end();
        return stored;
    }

    // esp_random() is a true random source once the RF subsystem is running,
    // which it is by the time this is called (BLE has been initialised).
    uint8_t secret[BOOTSTRAP_BYTES];
    esp_fill_random(secret, sizeof(secret));
    String created = toHex(secret, sizeof(secret));
    memset(secret, 0, sizeof(secret));

    if (!preferences.putString(KEY_BOOTSTRAP, created)) {
        NURA_ERROR("ID", "could not store the device credential");
    } else {
        NURA_INFO("ID", "created this device's credential for the first time");
    }
    preferences.end();
    return created;
}

}  // namespace

void begin() {
    g_hardwareId = readHardwareId();
    g_shortId = g_hardwareId.substring(g_hardwareId.length() - 4);
    g_bleName = String(protocol::BLE_NAME_PREFIX) + g_shortId;
    g_bootstrapSecret = loadOrCreateBootstrapSecret();

    NURA_INFO("ID", "hardware id %s, credential %s", g_hardwareId.c_str(),
              log::present(g_bootstrapSecret.length() > 0));
}

const String& hardwareId() {
    return g_hardwareId;
}

const String& shortId() {
    return g_shortId;
}

const String& bleName() {
    return g_bleName;
}

const String& bootstrapSecret() {
    return g_bootstrapSecret;
}

}  // namespace nura::identity
