#include "display.h"

#include "board_config.h"
#include "log.h"

#if NURA_HAS_DISPLAY
#define LGFX_USE_V1
#include <LovyanGFX.hpp>
#endif

namespace nura::display {
namespace {

#if NURA_HAS_DISPLAY

//: Panel wiring for the XIAO ESP32-S3. UNVERIFIED: the robot has not been
//: built, so both the panel driver and the pins are assumptions to check
//: against the real hardware before trusting this.
class NuraPanel : public lgfx::LGFX_Device {
   public:
    NuraPanel() {
        auto bus = _bus.config();
        bus.spi_host = SPI2_HOST;
        bus.spi_mode = 0;
        bus.freq_write = 40000000;
        bus.pin_sclk = board::PIN_TFT_SCLK;
        bus.pin_mosi = board::PIN_TFT_MOSI;
        bus.pin_miso = -1;
        bus.pin_dc = board::PIN_TFT_DC;
        _bus.config(bus);
        _panel.setBus(&_bus);

        auto panel = _panel.config();
        panel.pin_cs = board::PIN_TFT_CS;
        panel.pin_rst = board::PIN_TFT_RST;
        panel.panel_width = board::TFT_WIDTH;
        panel.panel_height = board::TFT_HEIGHT;
        _panel.config(panel);

        auto light = _light.config();
        light.pin_bl = board::PIN_TFT_BACKLIGHT;
        _light.config(light);
        _panel.setLight(&_light);

        setPanel(&_panel);
    }

   private:
#if NURA_DISPLAY_ILI9341
    lgfx::Panel_ILI9341 _panel;
#else
    lgfx::Panel_ST7789 _panel;
#endif
    lgfx::Bus_SPI _bus;
    lgfx::Light_PWM _light;
};

NuraPanel g_panel;
bool g_ready = false;

void drawScreen(const String& heading, const String& body, uint8_t bodySize) {
    if (!g_ready) return;
    g_panel.fillScreen(board::COLOUR_BACKGROUND);
    g_panel.setTextColor(board::COLOUR_ACCENT, board::COLOUR_BACKGROUND);
    g_panel.setTextDatum(textdatum_t::middle_center);
    g_panel.setTextSize(2);
    g_panel.drawString(heading, board::TFT_WIDTH / 2, board::TFT_HEIGHT / 3);
    g_panel.setTextColor(board::COLOUR_TEXT, board::COLOUR_BACKGROUND);
    g_panel.setTextSize(bodySize);
    g_panel.drawString(body, board::TFT_WIDTH / 2, board::TFT_HEIGHT / 2);
}

//: Two rounded eyes: the calm face, not the full animation system, which
//: PRD 2 section 39 keeps out of this stage.
void drawFace() {
    if (!g_ready) return;
    g_panel.fillScreen(board::COLOUR_BACKGROUND);
    const int eyeWidth = 48;
    const int eyeHeight = 64;
    const int y = board::TFT_HEIGHT / 2 - eyeHeight / 2;
    g_panel.fillSmoothRoundRect(board::TFT_WIDTH / 2 - 70, y, eyeWidth, eyeHeight, 20,
                                board::COLOUR_ACCENT);
    g_panel.fillSmoothRoundRect(board::TFT_WIDTH / 2 + 22, y, eyeWidth, eyeHeight, 20,
                                board::COLOUR_ACCENT);
}

#endif  // NURA_HAS_DISPLAY

}  // namespace

void begin() {
#if NURA_HAS_DISPLAY
    g_ready = g_panel.init();
    if (g_ready) {
        g_panel.setRotation(0);
        g_panel.fillScreen(board::COLOUR_BACKGROUND);
        NURA_INFO("UI", "display ready");
    } else {
        NURA_ERROR("UI", "display did not initialise");
    }
#else
    NURA_INFO("UI", "no display fitted in this build; status goes to serial");
#endif
}

bool isFitted() {
#if NURA_HAS_DISPLAY
    return g_ready;
#else
    return false;
#endif
}

void showPairingReady(const String& bleName) {
#if NURA_HAS_DISPLAY
    drawScreen("Ready to set up", bleName, 2);
#endif
    NURA_INFO("PAIR", "ready to pair as %s", bleName.c_str());
}

void showPairingCode(const String& code) {
#if NURA_HAS_DISPLAY
    // Grouped as "482 731", which is easier to read off a screen.
    String spaced = code.substring(0, 3) + " " + code.substring(3);
    drawScreen("Enter this code", spaced, 4);
#else
    // Development fallback only. With no screen fitted there is no other way
    // to see the code, and pairing would otherwise be impossible to exercise.
    // A shipped robot must show this on its display instead.
    NURA_INFO("PAIR", "development fallback -- pairing code is %s", code.c_str());
#endif
}

void showStatus(const String& message) {
#if NURA_HAS_DISPLAY
    drawScreen("Nura", message, 2);
#endif
    NURA_INFO("UI", "%s", message.c_str());
}

void showConnected() {
#if NURA_HAS_DISPLAY
    drawFace();
#endif
    NURA_INFO("UI", "connected");
}

void showOffline() {
#if NURA_HAS_DISPLAY
    drawScreen("Nura", "Offline", 2);
#endif
    NURA_INFO("UI", "offline");
}

}  // namespace nura::display
