#include "presentation_manager.h"

#include "audio_output.h"
#include "backend_client.h"
#include "card_renderer.h"
#include "display_driver.h"
#include "log.h"
#include "settings_store.h"

namespace nura::presentation_manager {
namespace {

presentation::ManagerState g_state = presentation::ManagerState::IDLE;
uint32_t g_nextPollAt = 0;
bool g_pending = false;
String g_lastPresentationId;
String g_lastFailure;
bool g_capabilitiesReported = false;

display_driver::DisplayDriver& display() {
    return display_driver::active();
}

audio_output::AudioOutput& audio() {
    return audio_output::active();
}

bool online() {
    return settings::apiBaseUrl().length() > 0 && settings::isRegistered();
}

//: Sends one acknowledgement and records what it said.
void acknowledge(const String& presentationId, presentation::Ack ack,
                 const char* failureCode) {
    g_state = presentation::ManagerState::ACKING;
    g_lastFailure = failureCode == nullptr ? String("") : String(failureCode);
    const bool sent = backend::acknowledgePresentation(
        settings::apiBaseUrl(), settings::deviceToken(), presentationId, ack,
        failureCode);
    if (!sent) {
        // The backend will offer the same presentation again, with the same
        // id, so a lost acknowledgement costs one extra render and nothing
        // else (section 18).
        NURA_ERROR("PRES", "could not acknowledge; will be offered again");
    }
}

//: Draws one envelope and acknowledges whatever actually happened.
void renderAndAcknowledge(const card::Envelope& envelope) {
    g_state = presentation::ManagerState::RENDERING;
    display_driver::DisplayDriver& driver = display();

    if (envelope.card.layout != presentation::Layout::FACE && !driver.canRenderText()) {
        // Section 87: a card with words on it needs a screen that can draw
        // words. Reported rather than drawn badly.
        acknowledge(envelope.presentationId, presentation::Ack::UNSUPPORTED,
                    presentation::FAILURE_NO_DISPLAY);
        g_state = presentation::ManagerState::IDLE;
        return;
    }

    const bool drawn = card::render(driver, envelope);
    if (!drawn) {
        acknowledge(envelope.presentationId, presentation::Ack::FAILED,
                    presentation::FAILURE_RENDER_FAILED);
        g_state = presentation::ManagerState::IDLE;
        return;
    }

    // Audio, and only if the backend said so. ``speak`` arrives false on every
    // envelope this project has ever produced, because the backend checks the
    // capability, the preference and the mode first (sections 43 and 82).
    const audio_output::Chime chime = audio_output::chimeFromName(envelope.chime.c_str());
    if (chime != audio_output::Chime::NONE) {
        audio().setVolume(envelope.volume);
        audio().playChime(chime);
    }
    if (envelope.speak) {
        audio().setVolume(envelope.volume);
        audio().speakText(envelope.card.body);
    }

    g_lastPresentationId = envelope.presentationId;
    g_lastFailure = "";
    // ``render_started``, not ``render_completed``: the card is on the screen
    // and staying there. The backend finishes it when a later one replaces it
    // (section 14).
    acknowledge(envelope.presentationId, presentation::Ack::RENDER_STARTED, nullptr);
    g_state = presentation::ManagerState::WAITING;
}

void fetchOnce() {
    g_state = presentation::ManagerState::FETCHING;
    backend::PresentationResult result =
        backend::fetchPresentation(settings::apiBaseUrl(), settings::deviceToken());

    if (!result.ok) {
        g_state = presentation::ManagerState::ERROR;
        g_nextPollAt = millis() + presentation::PRESENTATION_RETRY_INTERVAL_MS;
        return;
    }
    if (result.empty) {
        g_pending = false;
        g_state = presentation::ManagerState::IDLE;
        g_nextPollAt = millis() + presentation::PRESENTATION_POLL_INTERVAL_MS;
        return;
    }

    card::Envelope envelope;
    const card::ParseResult parsed = card::parse(result.body.c_str(), envelope);
    // The body held somebody's medication name or a family message. It is not
    // kept a moment longer than the parse (section 67).
    result.body = "";

    if (parsed != card::ParseResult::OK) {
        NURA_ERROR("PRES", "refused an envelope (%d)", static_cast<int>(parsed));
        if (envelope.presentationId.length() > 0) {
            const bool unsupported =
                parsed == card::ParseResult::UNSUPPORTED_LAYOUT ||
                parsed == card::ParseResult::UNSUPPORTED_VERSION;
            acknowledge(envelope.presentationId,
                        unsupported ? presentation::Ack::UNSUPPORTED
                                    : presentation::Ack::FAILED,
                        card::failureFor(parsed));
        }
        g_state = presentation::ManagerState::IDLE;
        g_nextPollAt = millis() + presentation::PRESENTATION_POLL_INTERVAL_MS;
        return;
    }

    renderAndAcknowledge(envelope);
    // Something was shown, so ask again promptly: a queue with an emergency
    // behind a reminder should not wait five seconds.
    g_nextPollAt = millis() + presentation::PRESENTATION_POLL_INTERVAL_MS;
}

}  // namespace

void begin() {
    display().begin();
    audio().begin();
    g_state = presentation::ManagerState::IDLE;
    g_nextPollAt = 0;
    NURA_INFO("PRES", "presentation manager ready (display=%s audio=%s)",
              display().name(), audio().name());
}

bool reportCapabilities() {
    if (!online()) return false;

    // Section 92's startup self-test, and section 90's rule about flags. Every
    // value below is a driver reporting what it has proven: a panel that
    // initialised is ``not_verified`` rather than ``available``, and anything
    // nobody wired is ``not_connected``.
    display_driver::DisplayDriver& screen = display();
    audio_output::AudioOutput& sound = audio();

    backend::CapabilityReport report;
    report.add(presentation::CAPABILITY_DISPLAY, screen.capabilityState());
    report.add(presentation::CAPABILITY_DISPLAY_TEXT,
               screen.canRenderText() ? screen.capabilityState()
                                      : presentation::CAPABILITY_UNAVAILABLE);
    report.add(presentation::CAPABILITY_DISPLAY_ANIMATION,
               screen.canAnimate() ? screen.capabilityState()
                                   : presentation::CAPABILITY_UNAVAILABLE);
    report.add(presentation::CAPABILITY_SPEAKER, sound.speakerState());
    report.add(presentation::CAPABILITY_AUDIO_PLAYBACK, sound.playbackState());
    report.add(presentation::CAPABILITY_TTS, sound.ttsState());
    // Nothing is wired for any of these, and no code in this firmware reads a
    // microphone, a camera or a button other than BOOT. Saying
    // ``not_connected`` is the honest answer and the one the app renders as
    // "Not reported".
    report.add(presentation::CAPABILITY_MICROPHONE,
               presentation::CAPABILITY_NOT_CONNECTED);
    report.add(presentation::CAPABILITY_WAKE_WORD,
               presentation::CAPABILITY_UNAVAILABLE);
    report.add(presentation::CAPABILITY_CAMERA,
               presentation::CAPABILITY_NOT_CONNECTED);
    report.add(presentation::CAPABILITY_CAMERA_DETECTION,
               presentation::CAPABILITY_UNAVAILABLE);
    // The BOOT button is pairing and factory reset (PRD 2, section 6). It is
    // not an input the presentation layer may offer actions on, so this is
    // ``not_connected`` and section 86's "use the Nura app to respond" is what
    // every card says.
    report.add(presentation::CAPABILITY_BUTTONS,
               presentation::CAPABILITY_NOT_CONNECTED);
    report.add(presentation::CAPABILITY_TOUCH,
               presentation::CAPABILITY_NOT_CONNECTED);

    const bool sent = backend::reportCapabilities(
        settings::apiBaseUrl(), settings::deviceToken(), report,
        presentation::CAPABILITY_SOURCE_SELF_TEST);
    g_capabilitiesReported = g_capabilitiesReported || sent;
    return sent;
}

void notifyPending() {
    g_pending = true;
    // Ask on the next loop rather than waiting out the poll interval.
    g_nextPollAt = millis();
}

void loop() {
    if (!online()) return;
    if (!g_capabilitiesReported) {
        reportCapabilities();
    }

    const uint32_t now = millis();
    if (now < g_nextPollAt) return;

    // Nothing waiting and nothing on the screen: ask anyway, at the poll
    // interval. The backend is the one that knows when the companion face
    // should come back (sections 83 and 84), so the device does not decide.
    g_nextPollAt = now + presentation::PRESENTATION_POLL_INTERVAL_MS;
    fetchOnce();
}

void showOffline() {
    display_driver::Card card;
    card.layout = presentation::Layout::STATUS;
    card.title = "Nura offline";
    card.lines[0] = "Trying to reconnect";
    card.lineCount = 1;
    card.serious = true;
    display().renderStatus(card);
    g_state = presentation::ManagerState::IDLE;
}

void showIdleFace() {
    display().renderFace(presentation::Face::IDLE, true);
}

presentation::ManagerState state() {
    return g_state;
}

const String& lastPresentationId() {
    return g_lastPresentationId;
}

const String& lastFailure() {
    return g_lastFailure;
}

}  // namespace nura::presentation_manager
