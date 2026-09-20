#include "spake2.h"

#include <esp_random.h>
#include <mbedtls/bignum.h>
#include <mbedtls/ecp.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <mbedtls/sha512.h>
#include <mbedtls/version.h>
#include <string.h>

#include <vector>

namespace nura::spake2 {
namespace {

// RFC 9382 section 6, P-256. The RFC gives these compressed; mbedTLS cannot
// decompress points, so they are stored uncompressed here. The compressed
// forms in the protocol document decompress to exactly these bytes.
constexpr uint8_t M_POINT[65] = {
    0x04, 0x88, 0x6e, 0x2f, 0x97, 0xac, 0xe4, 0x6e,
    0x55, 0xba, 0x9d, 0xd7, 0x24, 0x25, 0x79, 0xf2,
    0x99, 0x3b, 0x64, 0xe1, 0x6e, 0xf3, 0xdc, 0xab,
    0x95, 0xaf, 0xd4, 0x97, 0x33, 0x3d, 0x8f, 0xa1,
    0x2f, 0x5f, 0xf3, 0x55, 0x16, 0x3e, 0x43, 0xce,
    0x22, 0x4e, 0x0b, 0x0e, 0x65, 0xff, 0x02, 0xac,
    0x8e, 0x5c, 0x7b, 0xe0, 0x94, 0x19, 0xc7, 0x85,
    0xe0, 0xca, 0x54, 0x7d, 0x55, 0xa1, 0x2e, 0x2d,
    0x20};
constexpr uint8_t N_POINT[65] = {
    0x04, 0xd8, 0xbb, 0xd6, 0xc6, 0x39, 0xc6, 0x29,
    0x37, 0xb0, 0x4d, 0x99, 0x7f, 0x38, 0xc3, 0x77,
    0x07, 0x19, 0xc6, 0x29, 0xd7, 0x01, 0x4d, 0x49,
    0xa2, 0x4b, 0x4f, 0x98, 0xba, 0xa1, 0x29, 0x2b,
    0x49, 0x07, 0xd6, 0x0a, 0xa6, 0xbf, 0xad, 0xe4,
    0x50, 0x08, 0xa6, 0x36, 0x33, 0x7f, 0x51, 0x68,
    0xc6, 0x4d, 0x9b, 0xd3, 0x60, 0x34, 0x80, 0x8c,
    0xd5, 0x64, 0x49, 0x0b, 0x1e, 0x65, 0x6e, 0xdb,
    0xe7};

constexpr size_t SCALAR_BYTES = 32;
//: 16 bytes more than the scalar needs, so reducing mod n-1 is unbiased.
constexpr size_t SCALAR_SEED_BYTES = 48;

// mbedTLS 2.x returns the status from the `_ret` variants; 3.x dropped the
// suffix and made the plain names return it instead. These wrappers keep the
// code readable whichever the toolchain ships.
int sha256(const uint8_t* input, size_t length, uint8_t output[32]) {
#if MBEDTLS_VERSION_MAJOR >= 3
    return mbedtls_sha256(input, length, output, /*is224=*/0);
#else
    return mbedtls_sha256_ret(input, length, output, /*is224=*/0);
#endif
}

int sha512(const uint8_t* input, size_t length, uint8_t output[64]) {
#if MBEDTLS_VERSION_MAJOR >= 3
    return mbedtls_sha512(input, length, output, /*is384=*/0);
#else
    return mbedtls_sha512_ret(input, length, output, /*is384=*/0);
#endif
}

//: mbedTLS wants a random source for point multiplication blinding.
int hardwareRandom(void* /*context*/, unsigned char* output, size_t length) {
    esp_fill_random(output, length);
    return 0;
}

void appendWithLength(std::vector<uint8_t>& out, const uint8_t* data, size_t length) {
    // RFC 9382: an eight-byte little-endian length prefix.
    uint64_t size = length;
    for (size_t index = 0; index < 8; index += 1) {
        out.push_back(static_cast<uint8_t>((size >> (8 * index)) & 0xFF));
    }
    out.insert(out.end(), data, data + length);
}

bool hmacSha256(const uint8_t* key, size_t keyLength, const uint8_t* message, size_t messageLength,
                uint8_t out[32]) {
    const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
    if (info == nullptr) return false;
    return mbedtls_md_hmac(info, key, keyLength, message, messageLength, out) == 0;
}

}  // namespace

bool hkdfSha256(const uint8_t* ikm, size_t ikmLength, const uint8_t* info, size_t infoLength,
                uint8_t* out, size_t outLength) {
    // RFC 5869 with an empty salt, which extract treats as 32 zero bytes.
    const uint8_t zeroSalt[32] = {0};
    uint8_t prk[32];
    if (!hmacSha256(zeroSalt, sizeof(zeroSalt), ikm, ikmLength, prk)) return false;

    uint8_t block[32];
    size_t blockLength = 0;
    size_t produced = 0;
    for (uint8_t counter = 1; produced < outLength; counter += 1) {
        std::vector<uint8_t> input;
        input.insert(input.end(), block, block + blockLength);
        input.insert(input.end(), info, info + infoLength);
        input.push_back(counter);
        if (!hmacSha256(prk, sizeof(prk), input.data(), input.size(), block)) return false;
        blockLength = sizeof(block);

        const size_t take = std::min(outLength - produced, sizeof(block));
        memcpy(out + produced, block, take);
        produced += take;
    }
    memset(prk, 0, sizeof(prk));
    memset(block, 0, sizeof(block));
    return true;
}

bool constantTimeEquals(const uint8_t* a, const uint8_t* b, size_t length) {
    uint8_t difference = 0;
    for (size_t index = 0; index < length; index += 1) {
        difference |= static_cast<uint8_t>(a[index] ^ b[index]);
    }
    return difference == 0;
}

bool passwordScalar(const String& hardwareId, const String& code, uint8_t out[32]) {
    std::vector<uint8_t> input;
    const char* domain = protocol::PAKE_W_DOMAIN;
    input.insert(input.end(), domain, domain + strlen(domain));
    appendWithLength(input, reinterpret_cast<const uint8_t*>(hardwareId.c_str()),
                     hardwareId.length());
    appendWithLength(input, reinterpret_cast<const uint8_t*>(code.c_str()), code.length());

    uint8_t digest[64];
    if (sha512(input.data(), input.size(), digest) != 0) return false;

    mbedtls_ecp_group group;
    mbedtls_mpi w;
    mbedtls_ecp_group_init(&group);
    mbedtls_mpi_init(&w);

    bool ok = mbedtls_ecp_group_load(&group, MBEDTLS_ECP_DP_SECP256R1) == 0 &&
              mbedtls_mpi_read_binary(&w, digest, sizeof(digest)) == 0 &&
              mbedtls_mpi_mod_mpi(&w, &w, &group.N) == 0 &&
              mbedtls_mpi_cmp_int(&w, 0) != 0 &&
              mbedtls_mpi_write_binary(&w, out, SCALAR_BYTES) == 0;

    memset(digest, 0, sizeof(digest));
    mbedtls_mpi_free(&w);
    mbedtls_ecp_group_free(&group);
    return ok;
}

bool keySchedule(const uint8_t* idA, size_t idALength, const uint8_t* idB, size_t idBLength,
                 const uint8_t* pA, const uint8_t* pB, const uint8_t* sharedPoint,
                 const uint8_t* w, const uint8_t* aad, size_t aadLength, uint8_t ke[16],
                 uint8_t cA[protocol::MAC_LENGTH], uint8_t cB[protocol::MAC_LENGTH]) {
    std::vector<uint8_t> transcript;
    appendWithLength(transcript, idA, idALength);
    appendWithLength(transcript, idB, idBLength);
    appendWithLength(transcript, pA, protocol::POINT_LENGTH);
    appendWithLength(transcript, pB, protocol::POINT_LENGTH);
    appendWithLength(transcript, sharedPoint, protocol::POINT_LENGTH);
    appendWithLength(transcript, w, SCALAR_BYTES);

    uint8_t hashed[32];
    if (sha256(transcript.data(), transcript.size(), hashed) != 0) {
        return false;
    }
    memcpy(ke, hashed, 16);
    const uint8_t* ka = hashed + 16;

    // KcA || KcB = HKDF(Ka, nil, "ConfirmationKeys" || AAD, 32)
    static const char* label = "ConfirmationKeys";
    std::vector<uint8_t> info;
    info.insert(info.end(), label, label + strlen(label));
    info.insert(info.end(), aad, aad + aadLength);

    uint8_t confirmationKeys[32];
    bool ok = hkdfSha256(ka, 16, info.data(), info.size(), confirmationKeys,
                         sizeof(confirmationKeys)) &&
              hmacSha256(confirmationKeys, 16, transcript.data(), transcript.size(), cA) &&
              hmacSha256(confirmationKeys + 16, 16, transcript.data(), transcript.size(), cB);

    memset(hashed + 16, 0, 16);
    memset(confirmationKeys, 0, sizeof(confirmationKeys));
    return ok;
}

bool respondWithScalar(const String& hardwareId, const String& code, const uint8_t* pA,
                       size_t pALength, const uint8_t* yBytes, size_t yLength, Session& out) {
    if (pA == nullptr || pALength != protocol::POINT_LENGTH || pA[0] != 0x04) return false;

    uint8_t wBytes[SCALAR_BYTES];
    if (!passwordScalar(hardwareId, code, wBytes)) return false;

    mbedtls_ecp_group group;
    mbedtls_ecp_point pointM, pointN, pointA, pointB, shared, scratch;
    mbedtls_mpi w, y, negativeW, one;
    mbedtls_ecp_group_init(&group);
    mbedtls_ecp_point_init(&pointM);
    mbedtls_ecp_point_init(&pointN);
    mbedtls_ecp_point_init(&pointA);
    mbedtls_ecp_point_init(&pointB);
    mbedtls_ecp_point_init(&shared);
    mbedtls_ecp_point_init(&scratch);
    mbedtls_mpi_init(&w);
    mbedtls_mpi_init(&y);
    mbedtls_mpi_init(&negativeW);
    mbedtls_mpi_init(&one);

    bool ok = mbedtls_ecp_group_load(&group, MBEDTLS_ECP_DP_SECP256R1) == 0 &&
              mbedtls_ecp_point_read_binary(&group, &pointM, M_POINT, sizeof(M_POINT)) == 0 &&
              mbedtls_ecp_point_read_binary(&group, &pointN, N_POINT, sizeof(N_POINT)) == 0 &&
              mbedtls_mpi_read_binary(&w, wBytes, sizeof(wBytes)) == 0 &&
              mbedtls_mpi_lset(&one, 1) == 0;

    // Refuse anything that is not a valid point of the group: an invalid-curve
    // point would otherwise leak information about y.
    ok = ok && mbedtls_ecp_point_read_binary(&group, &pointA, pA, pALength) == 0 &&
         mbedtls_ecp_check_pubkey(&group, &pointA) == 0;

    if (ok) {
        if (yBytes != nullptr) {
            ok = mbedtls_mpi_read_binary(&y, yBytes, yLength) == 0;
        } else {
            // y random in [1, n-1], from 16 extra bytes reduced mod n-1.
            uint8_t seed[SCALAR_SEED_BYTES];
            esp_fill_random(seed, sizeof(seed));
            mbedtls_mpi order;
            mbedtls_mpi_init(&order);
            ok = mbedtls_mpi_read_binary(&y, seed, sizeof(seed)) == 0 &&
                 mbedtls_mpi_copy(&order, &group.N) == 0 &&
                 mbedtls_mpi_sub_int(&order, &order, 1) == 0 &&
                 mbedtls_mpi_mod_mpi(&y, &y, &order) == 0 &&
                 mbedtls_mpi_add_int(&y, &y, 1) == 0;
            mbedtls_mpi_free(&order);
            memset(seed, 0, sizeof(seed));
        }
    }

    // pB = y*G + w*N
    size_t written = 0;
    ok = ok && mbedtls_ecp_muladd(&group, &pointB, &y, &group.G, &w, &pointN) == 0 &&
         mbedtls_ecp_point_write_binary(&group, &pointB, MBEDTLS_ECP_PF_UNCOMPRESSED, &written,
                                        out.pB, sizeof(out.pB)) == 0 &&
         written == protocol::POINT_LENGTH;

    // K = y * (pA - w*M), computed as pA + (n - w)*M then multiplied by y.
    ok = ok && mbedtls_mpi_sub_mpi(&negativeW, &group.N, &w) == 0 &&
         mbedtls_ecp_muladd(&group, &scratch, &one, &pointA, &negativeW, &pointM) == 0 &&
         mbedtls_ecp_mul(&group, &shared, &y, &scratch, hardwareRandom, nullptr) == 0 &&
         mbedtls_ecp_is_zero(&shared) == 0;

    uint8_t sharedBytes[protocol::POINT_LENGTH];
    ok = ok && mbedtls_ecp_point_write_binary(&group, &shared, MBEDTLS_ECP_PF_UNCOMPRESSED,
                                              &written, sharedBytes, sizeof(sharedBytes)) == 0 &&
         written == protocol::POINT_LENGTH;

    if (ok) {
        const char* aad = protocol::PAKE_AAD;
        const char* idA = protocol::PAKE_IDENTITY_APP;
        ok = keySchedule(reinterpret_cast<const uint8_t*>(idA), strlen(idA),
                         reinterpret_cast<const uint8_t*>(hardwareId.c_str()),
                         hardwareId.length(), pA, out.pB, sharedBytes, wBytes,
                         reinterpret_cast<const uint8_t*>(aad), strlen(aad), out.ke, out.cA,
                         out.cB);
    }

    // The password scalar and the shared point must not outlive the exchange.
    memset(wBytes, 0, sizeof(wBytes));
    memset(sharedBytes, 0, sizeof(sharedBytes));
    mbedtls_mpi_free(&one);
    mbedtls_mpi_free(&negativeW);
    mbedtls_mpi_free(&y);
    mbedtls_mpi_free(&w);
    mbedtls_ecp_point_free(&scratch);
    mbedtls_ecp_point_free(&shared);
    mbedtls_ecp_point_free(&pointB);
    mbedtls_ecp_point_free(&pointA);
    mbedtls_ecp_point_free(&pointN);
    mbedtls_ecp_point_free(&pointM);
    mbedtls_ecp_group_free(&group);
    return ok;
}

bool respond(const String& hardwareId, const String& code, const uint8_t* pA, size_t pALength,
             Session& out) {
    return respondWithScalar(hardwareId, code, pA, pALength, nullptr, 0, out);
}

}  // namespace nura::spake2
