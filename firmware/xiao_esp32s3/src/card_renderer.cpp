#include "card_renderer.h"

#include <ArduinoJson.h>

#include "log.h"

namespace nura::card {
namespace {

String textField(JsonObjectConst payload, const char* key) {
    const char* value = payload[key] | "";
    return String(value);
}

bool present(const String& value) {
    return value.length() > 0;
}

//: Whether the layout has the fields it needs. The backend validates this
//: before sending; the device checks again because a device that drew a card
//: with an empty title would be showing somebody a blank box.
bool complete(const display_driver::Card& card) {
    switch (card.layout) {
        case presentation::Layout::FACE:
            return true;  // the face enum always resolves
        case presentation::Layout::TITLE_BODY:
            return present(card.title) && present(card.body);
        case presentation::Layout::TITLE_VALUE:
            return present(card.title) && present(card.value);
        case presentation::Layout::REMINDER:
            return present(card.title) && present(card.primary);
        case presentation::Layout::MESSAGE:
            return present(card.title) && present(card.body);
        case presentation::Layout::STATUS:
        case presentation::Layout::EMERGENCY:
            return present(card.title) && card.lineCount > 0;
        case presentation::Layout::PAIRING_CODE:
            return present(card.title) && present(card.code);
        case presentation::Layout::UNKNOWN:
        default:
            return false;
    }
}

}  // namespace

ParseResult parse(const char* json, Envelope& out) {
    JsonDocument document;
    if (deserializeJson(document, json) != DeserializationError::Ok) {
        return ParseResult::MALFORMED;
    }

    out.protocolVersion = document["protocol_version"] | 0;
    if (out.protocolVersion != presentation::PRESENTATION_PROTOCOL_VERSION) {
        // Section 116. A device that guessed at a newer envelope is a device
        // that eventually draws the wrong thing in an emergency.
        return ParseResult::UNSUPPORTED_VERSION;
    }

    out.presentationId = String(document["presentation_id"] | "");
    out.type = String(document["type"] | "");
    out.mode = String(document["mode"] | "");
    out.priority = document["priority"] | 0;

    JsonObjectConst settings = document["settings"];
    if (!settings.isNull()) {
        out.brightness = settings["brightness"] | 70;
        out.volume = settings["volume"] | 0;
        out.reducedMotion = settings["reduced_motion"] | false;
        out.faceAnimation = settings["face_animation"] | true;
    }

    const char* layoutName = document["layout"] | "";
    display_driver::Card& card = out.card;
    card.layout = presentation::layoutFromName(layoutName);
    if (card.layout == presentation::Layout::UNKNOWN) {
        return ParseResult::UNSUPPORTED_LAYOUT;
    }

    JsonObjectConst payload = document["payload"];
    if (payload.isNull()) {
        return ParseResult::INCOMPLETE;
    }

    // Read by name, one field at a time. Nothing here interprets a value.
    card.title = textField(payload, "title");
    card.primary = textField(payload, "primary");
    card.secondary = textField(payload, "secondary");
    card.prompt = textField(payload, "prompt");
    card.body = textField(payload, "body");
    card.sender = textField(payload, "sender");
    card.value = textField(payload, "value");
    card.code = textField(payload, "code");
    card.serious = payload["serious"] | false;
    card.respondInApp = payload["respond_in_app"] | false;
    card.continueInApp = payload["continue_in_app"] | false;
    card.face = presentation::faceFromName(payload["face_state"] | "");
    out.speak = payload["speak"] | false;
    out.chime = String(payload["chime"] | "");

    card.lineCount = 0;
    JsonArrayConst lines = payload["lines"];
    for (JsonVariantConst line : lines) {
        if (card.lineCount >= presentation::MAX_LINES) break;
        card.lines[card.lineCount] = String(line.as<const char*>());
        card.lineCount += 1;
    }

    if (!complete(card)) {
        return ParseResult::INCOMPLETE;
    }
    return ParseResult::OK;
}

const char* failureFor(ParseResult result) {
    switch (result) {
        case ParseResult::UNSUPPORTED_VERSION:
            return presentation::FAILURE_UNSUPPORTED_PROTOCOL;
        case ParseResult::UNSUPPORTED_LAYOUT:
            return presentation::FAILURE_UNSUPPORTED_LAYOUT;
        case ParseResult::MALFORMED:
        case ParseResult::INCOMPLETE:
            return presentation::FAILURE_RENDER_FAILED;
        case ParseResult::OK:
        default:
            return presentation::FAILURE_DEVICE_ERROR;
    }
}

bool render(display_driver::DisplayDriver& driver, const Envelope& envelope) {
    const display_driver::Card& card = envelope.card;
    driver.setBrightness(envelope.brightness);

    switch (card.layout) {
        case presentation::Layout::FACE:
            // Section 30: one field, already combined by the backend, so the
            // firmware has no rule to remember about reduced motion.
            return driver.renderFace(card.face,
                                     envelope.faceAnimation && !envelope.reducedMotion);
        case presentation::Layout::EMERGENCY:
            // Section 106: readability over everything, and its own method so
            // a future driver can give it the whole panel.
            return driver.renderEmergency(card);
        case presentation::Layout::STATUS:
            return driver.renderStatus(card);
        case presentation::Layout::TITLE_BODY:
        case presentation::Layout::TITLE_VALUE:
        case presentation::Layout::REMINDER:
        case presentation::Layout::MESSAGE:
        case presentation::Layout::PAIRING_CODE:
            return driver.renderCard(card);
        case presentation::Layout::UNKNOWN:
        default:
            // Unreachable: parse() refuses an unknown layout before this.
            NURA_ERROR("CARD", "refusing to draw an unknown layout");
            return false;
    }
}

}  // namespace nura::card
