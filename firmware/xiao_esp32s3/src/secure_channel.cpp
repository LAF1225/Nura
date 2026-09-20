#include "secure_channel.h"

#include <ArduinoJson.h>
#include <mbedtls/gcm.h>
#include <string.h>

#include <vector>

#include "log.h"
#include "protocol.h"
#include "spake2.h"

namespace nura::secure_channel {
namespace {

//: `01 || nonce(12) || ciphertext || tag(16)`.
constexpr size_t HEADER_LENGTH = 1;
constexpr size_t MINIMUM_LENGTH =
    HEADER_LENGTH + protocol::NONCE_LENGTH + protocol::TAG_LENGTH + 1;

}  // namespace

bool deriveWifiKey(const uint8_t ke[16], uint8_t out[16]) {
    const char* info = protocol::WIFI_KEY_INFO;
    return spake2::hkdfSha256(ke, 16, reinterpret_cast<const uint8_t*>(info), strlen(info), out,
                              protocol::WIFI_KEY_LENGTH);
}

bool openWifiConfig(const uint8_t key[16], const String& hardwareId, const uint8_t* payload,
                    size_t length, WifiConfig& out) {
    if (payload == nullptr || length < MINIMUM_LENGTH || length > protocol::MAX_ATTRIBUTE_LENGTH) {
        return false;
    }
    if (payload[0] != protocol::WIFI_CONFIG_VERSION) {
        NURA_ERROR("PAIR", "wi-fi payload used an unknown version");
        return false;
    }

    const uint8_t* nonce = payload + HEADER_LENGTH;
    const uint8_t* ciphertext = nonce + protocol::NONCE_LENGTH;
    const size_t ciphertextLength =
        length - HEADER_LENGTH - protocol::NONCE_LENGTH - protocol::TAG_LENGTH;
    const uint8_t* tag = ciphertext + ciphertextLength;

    // Associated data binds the payload to this robot: version byte, then id.
    std::vector<uint8_t> associated;
    associated.push_back(protocol::WIFI_CONFIG_VERSION);
    associated.insert(associated.end(), hardwareId.c_str(),
                      hardwareId.c_str() + hardwareId.length());

    std::vector<uint8_t> plaintext(ciphertextLength);
    mbedtls_gcm_context gcm;
    mbedtls_gcm_init(&gcm);
    bool ok = mbedtls_gcm_setkey(&gcm, MBEDTLS_CIPHER_ID_AES, key, 128) == 0 &&
              mbedtls_gcm_auth_decrypt(&gcm, ciphertextLength, nonce, protocol::NONCE_LENGTH,
                                       associated.data(), associated.size(), tag,
                                       protocol::TAG_LENGTH, ciphertext, plaintext.data()) == 0;
    mbedtls_gcm_free(&gcm);

    if (!ok) {
        // Either not from the verified app, or altered in flight.
        NURA_ERROR("PAIR", "wi-fi payload failed authentication");
        return false;
    }

    JsonDocument document;
    const DeserializationError error =
        deserializeJson(document, plaintext.data(), plaintext.size());
    if (error) {
        memset(plaintext.data(), 0, plaintext.size());
        NURA_ERROR("PAIR", "wi-fi payload was not valid JSON");
        return false;
    }

    out.ssid = document["ssid"] | "";
    out.password = document["password"] | "";
    out.provisioningToken = document["provisioning_token"] | "";
    out.apiBaseUrl = document["api_base_url"] | "";

    // The decrypted buffer holds the password; do not leave it in RAM.
    memset(plaintext.data(), 0, plaintext.size());

    const bool complete = out.ssid.length() > 0 && out.ssid.length() <= protocol::SSID_MAX_BYTES &&
                          out.password.length() >= protocol::PASSWORD_MIN_LENGTH &&
                          out.password.length() <= protocol::PASSWORD_MAX_LENGTH &&
                          out.provisioningToken.length() > 0 && out.apiBaseUrl.length() > 0;
    if (!complete) {
        NURA_ERROR("PAIR", "wi-fi payload was missing or malformed fields");
        out = WifiConfig{};
        return false;
    }
    return true;
}

}  // namespace nura::secure_channel
