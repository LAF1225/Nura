// Which hardware this build expects, and where it is wired.
//
// IMPORTANT: the Nura robot has not been assembled yet. The default build
// therefore assumes a bare XIAO ESP32-S3 with nothing attached, and every
// optional peripheral is compiled out. Pairing still works: the pairing code
// goes to the serial log in development builds (see display.cpp).
//
// When the hardware exists, enable a peripheral with a build flag in
// platformio.ini and check the pins below against how it is actually wired.
// The pin numbers are placeholders chosen so nothing collides; none of them
// has been verified against a real board.
#pragma once

//: 240x320 SPI TFT. 0 = no screen fitted.
#ifndef NURA_HAS_DISPLAY
#define NURA_HAS_DISPLAY 0
#endif

//: Which panel driver the TFT uses. Unconfirmed -- the two common ones for a
//: 240x320 SPI module are ILI9341 and ST7789.
#ifndef NURA_DISPLAY_ILI9341
#define NURA_DISPLAY_ILI9341 1
#endif

//: I2S amplifier and speaker (e.g. MAX98357A). 0 = no audio fitted.
#ifndef NURA_HAS_AUDIO
#define NURA_HAS_AUDIO 0
#endif

namespace nura::board {

// XIAO ESP32-S3 pin map: the silkscreen D-numbers in GPIO terms.
constexpr int PIN_D0 = 1;
constexpr int PIN_D1 = 2;
constexpr int PIN_D2 = 3;
constexpr int PIN_D3 = 4;
constexpr int PIN_D4 = 5;
constexpr int PIN_D5 = 6;
constexpr int PIN_D6 = 43;
constexpr int PIN_D7 = 44;
constexpr int PIN_D8 = 7;
constexpr int PIN_D9 = 8;
constexpr int PIN_D10 = 9;

//: BOOT button, which every XIAO ESP32-S3 has. Active low. Held for 3 s to
//: enter pairing mode, 10 s for a factory reset (PRD 2, section 6).
constexpr int PIN_PAIRING_BUTTON = 0;

//: The board's user LED. Active low on this board.
constexpr int PIN_STATUS_LED = 21;
constexpr bool STATUS_LED_ACTIVE_LOW = true;

// --- provisional wiring for hardware that does not exist yet ---
constexpr int PIN_TFT_SCLK = PIN_D8;
constexpr int PIN_TFT_MOSI = PIN_D10;
constexpr int PIN_TFT_CS = PIN_D1;
constexpr int PIN_TFT_DC = PIN_D3;
constexpr int PIN_TFT_RST = PIN_D2;
constexpr int PIN_TFT_BACKLIGHT = PIN_D0;
constexpr int TFT_WIDTH = 240;
constexpr int TFT_HEIGHT = 320;

constexpr int PIN_I2S_BCLK = PIN_D4;
constexpr int PIN_I2S_LRCK = PIN_D5;
constexpr int PIN_I2S_DIN = PIN_D7;

// Nura brand colours (PRD 0, section 10), as RGB565 for the display.
constexpr uint16_t COLOUR_BACKGROUND = 0x0208;  // #0E1C1B dark teal
constexpr uint16_t COLOUR_TEXT = 0xFFFF;
constexpr uint16_t COLOUR_ACCENT = 0xA75A;  // #A5E3D1 mint

}  // namespace nura::board
