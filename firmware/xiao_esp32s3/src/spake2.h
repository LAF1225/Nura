// SPAKE2, role B (the robot), from RFC 9382 (PRD 2, sections 16 and 24).
//
// The six digits on Nura's screen are the password. Running a PAKE rather
// than plain key agreement is what makes such a short secret safe: an
// attacker gets one guess per attempt and nothing to test offline. The app
// runs role A in mobile/src/services/provisioning/spake2.ts.
//
// Ciphersuite: SPAKE2-P256-SHA256-HKDF-HMAC, unmodified. The only
// Nura-specific part is how `w` is derived from the code, which is documented
// in docs/device/provisioning-protocol.md section 4.
#pragma once

#include <Arduino.h>

#include "protocol.h"

namespace nura::spake2 {

struct Session {
    uint8_t pB[protocol::POINT_LENGTH];
    //: What a genuine app must send back. Compared in constant time.
    uint8_t cA[protocol::MAC_LENGTH];
    //: Our confirmation, proving we knew the code too.
    uint8_t cB[protocol::MAC_LENGTH];
    //: Session key. Only the Wi-Fi payload key is derived from it.
    uint8_t ke[16];
};

//: Answers one PAKE_START. False means the message was malformed or the point
//: was not on the curve -- never that the code was wrong, which is only known
//: once the app's confirmation arrives.
bool respond(const String& hardwareId, const String& code, const uint8_t* pA, size_t pALength,
             Session& out);

//: As `respond`, but with the caller supplying the scalar y. Exists so the
//: on-device tests can reproduce the RFC's vectors exactly.
bool respondWithScalar(const String& hardwareId, const String& code, const uint8_t* pA,
                       size_t pALength, const uint8_t* y, size_t yLength, Session& out);

//: RFC 9382 section 4's key schedule, exposed for the RFC vector tests.
bool keySchedule(const uint8_t* idA, size_t idALength, const uint8_t* idB, size_t idBLength,
                 const uint8_t* pA, const uint8_t* pB, const uint8_t* sharedPoint,
                 const uint8_t* w, const uint8_t* aad, size_t aadLength, uint8_t ke[16],
                 uint8_t cA[protocol::MAC_LENGTH], uint8_t cB[protocol::MAC_LENGTH]);

//: w = OS2IP(SHA-512(domain || len(B) || B || len(code) || code)) mod n.
bool passwordScalar(const String& hardwareId, const String& code, uint8_t out[32]);

//: Comparison whose timing does not depend on where the difference is.
bool constantTimeEquals(const uint8_t* a, const uint8_t* b, size_t length);

//: HKDF-SHA256 (RFC 5869). Written out here because ESP-IDF's mbedTLS build
//: does not enable MBEDTLS_HKDF_C by default.
bool hkdfSha256(const uint8_t* ikm, size_t ikmLength, const uint8_t* info, size_t infoLength,
                uint8_t* out, size_t outLength);

}  // namespace nura::spake2
