// What a speaker can be asked to do (PRD 11, sections 41, 42, 43, 44, 81, 82
// and 94).
//
// The same shape as the display driver, and for the same reason: product logic
// asks ``AudioOutput`` for a chime, and the fact that nothing in this project
// has ever made a sound is a property of the implementation rather than
// something scattered through the callers.
//
// **Nothing here has ever played anything.** ``SilentAudioOutput`` is the
// driver on every build, it reports ``not_connected``, and
// ``speakText`` returns false. Section 94 keeps amplifier, speaker, volume,
// chime and TTS verification as separate physical steps that have not been
// taken.
//
// **No cloud provider is named in presentation logic** (section 42).
// ``TextToSpeechProvider`` is declared and has no implementation; the day one
// arrives it is a file, not a change to anything that decides *what* to say.
//
// **Nothing speaks on its own** (section 82). ``speak`` arrives on the
// envelope and is false unless the capability exists, the person turned it on
// and the mode allows it -- three conditions the backend checks, which is why
// no envelope this project has produced has ever had it set.
#pragma once

#include <Arduino.h>

#include "presentation_protocol.h"

namespace nura::audio_output {

//: Section 81's categories. Small and fixed: a chime vocabulary that grows
//: per event is how a companion becomes a notification billboard.
enum class Chime : uint8_t {
    NONE = 0x00,
    REMINDER = 0x01,
    MESSAGE = 0x02,
    SAFETY = 0x03,
    SUCCESS = 0x04,
    ERROR = 0x05,
};

Chime chimeFromName(const char* name);

//: A future text-to-speech provider (section 42). Declared so the interface is
//: the thing presentation logic depends on; there is no implementation, and a
//: build with a speaker but no provider reports ``tts`` as ``not_connected``.
class TextToSpeechProvider {
   public:
    virtual ~TextToSpeechProvider() = default;
    //: Returns false when nothing was spoken, which is the only thing this
    //: project can currently return.
    virtual bool speak(const String& text) = 0;
    virtual const char* name() const = 0;
};

class AudioOutput {
   public:
    virtual ~AudioOutput() = default;

    virtual bool begin() = 0;
    virtual bool playChime(Chime chime) = 0;
    //: Only ever called when the envelope said ``speak`` (section 43).
    virtual bool speakText(const String& text) = 0;
    virtual void stop() = 0;
    //: 0-100 (section 44).
    virtual void setVolume(uint8_t percent) = 0;

    virtual const char* name() const = 0;
    //: What to report for the ``speaker`` capability.
    virtual const char* speakerState() const = 0;
    //: What to report for ``audio_playback``.
    virtual const char* playbackState() const = 0;
    //: What to report for ``tts``.
    virtual const char* ttsState() const = 0;
};

//: The one on every build. Logs what it would have played and reports every
//: audio capability as not connected.
class SilentAudioOutput : public AudioOutput {
   public:
    bool begin() override;
    bool playChime(Chime chime) override;
    bool speakText(const String& text) override;
    void stop() override;
    void setVolume(uint8_t percent) override;
    const char* name() const override { return "silent"; }
    const char* speakerState() const override {
        return presentation::CAPABILITY_NOT_CONNECTED;
    }
    const char* playbackState() const override {
        return presentation::CAPABILITY_NOT_CONNECTED;
    }
    const char* ttsState() const override {
        return presentation::CAPABILITY_NOT_CONNECTED;
    }
};

#if NURA_HAS_AUDIO

//: An I2S amplifier, if one is ever fitted. Reports ``not_verified``: the pins
//: in board_config.h are assumptions and no sound has been heard from this
//: project (sections 90, 92 and 94).
class I2SAudioOutput : public AudioOutput {
   public:
    bool begin() override;
    bool playChime(Chime chime) override;
    bool speakText(const String& text) override;
    void stop() override;
    void setVolume(uint8_t percent) override;
    const char* name() const override { return "i2s"; }
    const char* speakerState() const override;
    const char* playbackState() const override;
    const char* ttsState() const override {
        // There is no provider. A speaker that cannot form words is not a
        // ``tts`` capability, however well it plays a chime.
        return presentation::CAPABILITY_NOT_CONNECTED;
    }

   private:
    bool _ready = false;
    uint8_t _volume = 40;
};

#endif  // NURA_HAS_AUDIO

AudioOutput& active();

}  // namespace nura::audio_output
