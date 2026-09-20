#include "settings_store.h"

#include <Preferences.h>

#include "log.h"

namespace nura::settings {
namespace {

constexpr const char* NVS_NAMESPACE = "nura_cfg";
constexpr const char* KEY_SSID = "ssid";
constexpr const char* KEY_PASSWORD = "pass";
constexpr const char* KEY_API = "api";
constexpr const char* KEY_DEVICE_TOKEN = "devtoken";
constexpr const char* KEY_DEVICE_ID = "devid";

Preferences g_preferences;
bool g_open = false;

bool ensureOpen() {
    if (!g_open) {
        g_open = g_preferences.begin(NVS_NAMESPACE, /*readOnly=*/false);
        if (!g_open) {
            NURA_ERROR("CFG", "could not open settings storage");
        }
    }
    return g_open;
}

String readString(const char* key) {
    return ensureOpen() ? g_preferences.getString(key, "") : String("");
}

}  // namespace

void begin() {
    ensureOpen();
    NURA_INFO("CFG", "wi-fi %s, registration %s", log::present(hasWifi()),
              log::present(isRegistered()));
}

bool hasWifi() {
    return readString(KEY_SSID).length() > 0;
}

WifiCredentials wifi() {
    return WifiCredentials{readString(KEY_SSID), readString(KEY_PASSWORD)};
}

void saveWifi(const WifiCredentials& credentials) {
    if (!ensureOpen()) return;
    g_preferences.putString(KEY_SSID, credentials.ssid);
    g_preferences.putString(KEY_PASSWORD, credentials.password);
    // The SSID is fine to log; the password never is.
    NURA_INFO("CFG", "stored credentials for network %s", credentials.ssid.c_str());
}

void clearWifi() {
    if (!ensureOpen()) return;
    g_preferences.remove(KEY_SSID);
    g_preferences.remove(KEY_PASSWORD);
    NURA_INFO("CFG", "cleared stored wi-fi credentials");
}

String apiBaseUrl() {
    return readString(KEY_API);
}

void saveApiBaseUrl(const String& url) {
    if (!ensureOpen()) return;
    g_preferences.putString(KEY_API, url);
}

bool isRegistered() {
    return readString(KEY_DEVICE_TOKEN).length() > 0;
}

String deviceToken() {
    return readString(KEY_DEVICE_TOKEN);
}

String deviceId() {
    return readString(KEY_DEVICE_ID);
}

void saveRegistration(const String& token, const String& id) {
    if (!ensureOpen()) return;
    g_preferences.putString(KEY_DEVICE_TOKEN, token);
    g_preferences.putString(KEY_DEVICE_ID, id);
    NURA_INFO("CLOUD", "registration stored for device %s", id.c_str());
}

void clearRegistration() {
    if (!ensureOpen()) return;
    g_preferences.remove(KEY_DEVICE_TOKEN);
    g_preferences.remove(KEY_DEVICE_ID);
}

void factoryReset() {
    if (!ensureOpen()) return;
    g_preferences.clear();
    NURA_INFO("CFG", "factory reset: wi-fi, registration and settings cleared");
}

}  // namespace nura::settings
