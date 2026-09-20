// Decrypting the Wi-Fi payload the app sends (PRD 2, section 24).
//
// AES-128-GCM under a key derived from the verified SPAKE2 session, with the
// hardware id as associated data so a payload captured near one robot cannot
// be replayed at another. Plaintext is wiped as soon as it has been parsed.
#pragma once

#include <Arduino.h>

namespace nura::secure_channel {

struct WifiConfig {
    String ssid;
    String password;
    String provisioningToken;
    String apiBaseUrl;
};

//: Derives the payload key from the SPAKE2 session key.
bool deriveWifiKey(const uint8_t ke[16], uint8_t out[16]);

//: Decrypts and parses `01 || nonce || ciphertext || tag`.
//: False means the payload was not produced by a verified app -- treated as
//: INVALID_PAYLOAD rather than as a Wi-Fi problem.
bool openWifiConfig(const uint8_t key[16], const String& hardwareId, const uint8_t* payload,
                    size_t length, WifiConfig& out);

}  // namespace nura::secure_channel
