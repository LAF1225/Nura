#include "audio_output.h"

#include <cstring>

#include "audio.h"
#include "log.h"

namespace nura::audio_output {
namespace {

const char* chimeName(Chime chime) {
    switch (chime) {
        case Chime::REMINDER:
            return "reminder";
        case Chime::MESSAGE:
            return "message";
        case Chime::SAFETY:
            return "safety";
        case Chime::SUCCESS:
            return "success";
        case Chime::ERROR:
            return "error";
        case Chime::NONE:
        default:
            return "none";
    }
}

}  // namespace

Chime chimeFromName(const char* name) {
    if (name == nullptr) return Chime::NONE;
    if (std::strcmp(name, "reminder") == 0) return Chime::REMINDER;
    if (std::strcmp(name, "message") == 0) return Chime::MESSAGE;
    if (std::strcmp(name, "safety") == 0) return Chime::SAFETY;
    if (std::strcmp(name, "success") == 0) return Chime::SUCCESS;
    if (std::strcmp(name, "error") == 0) return Chime::ERROR;
    return Chime::NONE;
}

// --- the silent output ------------------------------------------------------

bool SilentAudioOutput::begin() {
    NURA_INFO("AUDIO", "no speaker in this build; chimes go to the log");
    return true;
}

bool SilentAudioOutput::playChime(Chime chime) {
    NURA_INFO("AUDIO", "[chime] %s (not played)", chimeName(chime));
    // False, and the falseness is the point: nothing was played, and the
    // caller must not be able to report that anything was.
    return false;
}

bool SilentAudioOutput::speakText(const String& text) {
    // The text is **not** logged. Section 67: an assistant reply, a medication
    // name or a family message would all arrive here.
    NURA_INFO("AUDIO", "[speak] %u characters (not spoken)",
              static_cast<unsigned>(text.length()));
    return false;
}

void SilentAudioOutput::stop() {}

void SilentAudioOutput::setVolume(uint8_t percent) {
    NURA_DEBUG("AUDIO", "[volume] %u%%", static_cast<unsigned>(percent));
}

// --- the I2S output ---------------------------------------------------------

#if NURA_HAS_AUDIO

bool I2SAudioOutput::begin() {
    // nura::audio already owns the I2S driver (PRD 2's introduction chime), so
    // this reuses it rather than installing a second one on the same port --
    // section 89's "reuse existing audio.*".
    _ready = nura::audio::isFitted();
    return _ready;
}

bool I2SAudioOutput::playChime(Chime chime) {
    if (!_ready) return false;
    // One sound exists in this project -- PRD 2's two-note introduction -- and
    // the five categories are not distinct yet. Using it for all of them is
    // honest; inventing four more placeholders would not be.
    NURA_INFO("AUDIO", "[chime] %s", chimeName(chime));
    return nura::audio::playIntroduction();
}

bool I2SAudioOutput::speakText(const String& text) {
    (void)text;
    // Section 42: no provider, so nothing is spoken. Returning false here is
    // what stops any caller reporting speech.
    NURA_INFO("AUDIO", "no text-to-speech provider; nothing spoken");
    return false;
}

void I2SAudioOutput::stop() {}

void I2SAudioOutput::setVolume(uint8_t percent) {
    _volume = percent > 100 ? 100 : percent;
    // The amplifier's gain is fixed in hardware on the boards being
    // considered, so this is recorded and not yet applied. Section 94 keeps
    // volume verification as a physical step.
    NURA_DEBUG("AUDIO", "[volume] %u%% (recorded, not applied)",
               static_cast<unsigned>(_volume));
}

const char* I2SAudioOutput::speakerState() const {
    if (!_ready) return presentation::CAPABILITY_UNAVAILABLE;
    // Section 12 again: the driver started, which is not the same as a sound
    // having been heard. Nobody has heard one.
    return presentation::CAPABILITY_NOT_VERIFIED;
}

const char* I2SAudioOutput::playbackState() const {
    return speakerState();
}

#endif  // NURA_HAS_AUDIO

AudioOutput& active() {
#if NURA_HAS_AUDIO
    static I2SAudioOutput i2s;
    return i2s;
#else
    static SilentAudioOutput silent;
    return silent;
#endif
}

}  // namespace nura::audio_output
