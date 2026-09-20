#include "audio.h"

#include <math.h>

#include "board_config.h"
#include "log.h"

#if NURA_HAS_AUDIO
// The ESP32 Arduino core in use here (2.0.x) predates the ESP_I2S library, so
// this uses the I2S driver that core ships. On core 3.x this would become
// ESP_I2S.h and I2SClass.
#include <driver/i2s.h>
#endif

namespace nura::audio {
namespace {

constexpr uint32_t SAMPLE_RATE = 16000;

#if NURA_HAS_AUDIO
constexpr i2s_port_t I2S_PORT = I2S_NUM_0;
bool g_ready = false;

//: A gentle sine note that fades in and out, so the amplifier is never asked
//: to jump from silence to full amplitude.
void playNote(float frequency, uint32_t milliseconds) {
    const uint32_t samples = (SAMPLE_RATE * milliseconds) / 1000;
    const uint32_t fade = SAMPLE_RATE / 50;
    for (uint32_t index = 0; index < samples; index += 1) {
        float envelope = 1.0f;
        if (index < fade) envelope = static_cast<float>(index) / fade;
        if (index > samples - fade) envelope = static_cast<float>(samples - index) / fade;

        const float phase = 2.0f * static_cast<float>(PI) * frequency * index / SAMPLE_RATE;
        const int16_t sample = static_cast<int16_t>(sinf(phase) * envelope * 6000.0f);
        const int16_t frame[2] = {sample, sample};
        size_t written = 0;
        i2s_write(I2S_PORT, frame, sizeof(frame), &written, portMAX_DELAY);
    }
    i2s_zero_dma_buffer(I2S_PORT);
}
#endif

}  // namespace

void begin() {
#if NURA_HAS_AUDIO
    i2s_config_t config = {};
    config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
    config.sample_rate = SAMPLE_RATE;
    config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
    config.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
    config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
    config.intr_alloc_flags = 0;
    config.dma_buf_count = 8;
    config.dma_buf_len = 256;
    config.use_apll = false;
    config.tx_desc_auto_clear = true;

    i2s_pin_config_t pins = {};
    pins.mck_io_num = I2S_PIN_NO_CHANGE;
    pins.bck_io_num = board::PIN_I2S_BCLK;
    pins.ws_io_num = board::PIN_I2S_LRCK;
    pins.data_out_num = board::PIN_I2S_DIN;
    pins.data_in_num = I2S_PIN_NO_CHANGE;

    g_ready = i2s_driver_install(I2S_PORT, &config, 0, nullptr) == ESP_OK &&
              i2s_set_pin(I2S_PORT, &pins) == ESP_OK;
    NURA_INFO("AUDIO", "amplifier %s", g_ready ? "ready" : "did not start");
#else
    NURA_INFO("AUDIO", "no speaker fitted in this build");
#endif
}

bool isFitted() {
#if NURA_HAS_AUDIO
    return g_ready;
#else
    return false;
#endif
}

bool playIntroduction() {
#if NURA_HAS_AUDIO
    if (!g_ready) return false;
    // Placeholder for the spoken introduction, which needs a voice clip that
    // does not exist yet (PRD 2, section 38).
    playNote(587.33f, 220);  // D5
    playNote(880.00f, 320);  // A5
    NURA_INFO("AUDIO", "played the introduction chime (placeholder for speech)");
    return true;
#else
    NURA_INFO("AUDIO", "introduction would play here: \"Hi. I'm Nura. It's nice to meet you.\"");
    return false;
#endif
}

}  // namespace nura::audio
