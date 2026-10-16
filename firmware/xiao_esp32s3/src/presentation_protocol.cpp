#include "presentation_protocol.h"

#include <cstring>

namespace nura::presentation {
namespace {

bool same(const char* a, const char* b) {
    if (a == nullptr || b == nullptr) return false;
    return std::strcmp(a, b) == 0;
}

}  // namespace

Layout layoutFromName(const char* name) {
    if (same(name, LAYOUT_NAME_FACE)) return Layout::FACE;
    if (same(name, LAYOUT_NAME_TITLE_BODY)) return Layout::TITLE_BODY;
    if (same(name, LAYOUT_NAME_TITLE_VALUE)) return Layout::TITLE_VALUE;
    if (same(name, LAYOUT_NAME_REMINDER)) return Layout::REMINDER;
    if (same(name, LAYOUT_NAME_MESSAGE)) return Layout::MESSAGE;
    if (same(name, LAYOUT_NAME_STATUS)) return Layout::STATUS;
    if (same(name, LAYOUT_NAME_EMERGENCY)) return Layout::EMERGENCY;
    if (same(name, LAYOUT_NAME_PAIRING_CODE)) return Layout::PAIRING_CODE;
    // Section 111: not a guess, and not a fallback that draws something.
    return Layout::UNKNOWN;
}

const char* layoutName(Layout layout) {
    switch (layout) {
        case Layout::FACE:
            return LAYOUT_NAME_FACE;
        case Layout::TITLE_BODY:
            return LAYOUT_NAME_TITLE_BODY;
        case Layout::TITLE_VALUE:
            return LAYOUT_NAME_TITLE_VALUE;
        case Layout::REMINDER:
            return LAYOUT_NAME_REMINDER;
        case Layout::MESSAGE:
            return LAYOUT_NAME_MESSAGE;
        case Layout::STATUS:
            return LAYOUT_NAME_STATUS;
        case Layout::EMERGENCY:
            return LAYOUT_NAME_EMERGENCY;
        case Layout::PAIRING_CODE:
            return LAYOUT_NAME_PAIRING_CODE;
        case Layout::UNKNOWN:
        default:
            return "UNKNOWN";
    }
}

Face faceFromName(const char* name) {
    if (same(name, FACE_NAME_LISTENING)) return Face::LISTENING;
    if (same(name, FACE_NAME_THINKING)) return Face::THINKING;
    if (same(name, FACE_NAME_SPEAKING)) return Face::SPEAKING;
    if (same(name, FACE_NAME_HAPPY)) return Face::HAPPY;
    if (same(name, FACE_NAME_CONCERNED)) return Face::CONCERNED;
    if (same(name, FACE_NAME_SLEEPING)) return Face::SLEEPING;
    if (same(name, FACE_NAME_PRIVACY)) return Face::PRIVACY;
    if (same(name, FACE_NAME_OFFLINE)) return Face::OFFLINE;
    // Unrecognised, including the empty string: calm rather than blank.
    return Face::IDLE;
}

const char* faceName(Face face) {
    switch (face) {
        case Face::LISTENING:
            return FACE_NAME_LISTENING;
        case Face::THINKING:
            return FACE_NAME_THINKING;
        case Face::SPEAKING:
            return FACE_NAME_SPEAKING;
        case Face::HAPPY:
            return FACE_NAME_HAPPY;
        case Face::CONCERNED:
            return FACE_NAME_CONCERNED;
        case Face::SLEEPING:
            return FACE_NAME_SLEEPING;
        case Face::PRIVACY:
            return FACE_NAME_PRIVACY;
        case Face::OFFLINE:
            return FACE_NAME_OFFLINE;
        case Face::IDLE:
        default:
            return FACE_NAME_IDLE;
    }
}

const char* ackName(Ack ack) {
    switch (ack) {
        case Ack::RECEIVED:
            return ACK_NAME_RECEIVED;
        case Ack::RENDER_STARTED:
            return ACK_NAME_RENDER_STARTED;
        case Ack::RENDER_COMPLETED:
            return ACK_NAME_RENDER_COMPLETED;
        case Ack::FAILED:
            return ACK_NAME_FAILED;
        case Ack::UNSUPPORTED:
        default:
            return ACK_NAME_UNSUPPORTED;
    }
}

}  // namespace nura::presentation
