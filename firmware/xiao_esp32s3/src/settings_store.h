// Everything the robot remembers across reboots (PRD 2, section 25).
//
// Wi-Fi credentials are written only *after* the robot has actually joined
// that network, so a mistyped password can never replace credentials that
// work. Nothing here is ever logged.
#pragma once

#include <Arduino.h>

namespace nura::settings {

struct WifiCredentials {
    String ssid;
    String password;
};

void begin();

//: True when a network has been stored, i.e. the robot is provisioned.
bool hasWifi();
WifiCredentials wifi();
void saveWifi(const WifiCredentials& credentials);
void clearWifi();

//: Where this robot talks to the backend, as given by the app during setup.
String apiBaseUrl();
void saveApiBaseUrl(const String& url);

//: True once the backend has issued this robot a device token.
bool isRegistered();
String deviceToken();
String deviceId();
void saveRegistration(const String& deviceToken, const String& deviceId);
void clearRegistration();

//: Clears Wi-Fi, registration and local configuration, keeping the device
//: identity so the robot can be set up again (PRD 2, section 45). Nothing in
//: the cloud is touched.
void factoryReset();

}  // namespace nura::settings
