// The Nura provisioning GATT service (PRD 2, sections 12 and 13).
//
// Owns the pairing session: the code on the screen, the SPAKE2 exchange, and
// the verified state that unlocks the Wi-Fi and command characteristics.
// Everything it receives is handed to a Delegate, so the radio code stays
// separate from what the robot then does about it.
#pragma once

#include <Arduino.h>

#include "protocol.h"
#include "secure_channel.h"

namespace nura::ble {

class Delegate {
   public:
    virtual ~Delegate() = default;
    //: Credentials arrived and decrypted. Held in RAM only until they work.
    virtual void onCredentialsReceived(const secure_channel::WifiConfig& config) = 0;
    virtual void onConnectWifi() = 0;
    virtual void onRetryWifi() = 0;
    virtual void onClearWifi() = 0;
    //: The app says setup is finished, so stop advertising.
    virtual void onFinish() = 0;
};

//: Starts the BLE stack and publishes the service. Does not advertise yet.
void begin(Delegate* delegate);

//: Enters pairing mode for `windowMs`, or indefinitely when `windowMs` is 0
//: (first boot, before the robot has ever been set up).
void startPairingMode(uint32_t windowMs);
void stopPairingMode();

bool isPairingMode();
bool isConnected();
bool isVerified();

//: Must be called from the main loop: the PAKE exchange and payload handling
//: run here rather than in the BLE callback, so the radio task is never
//: blocked by elliptic-curve arithmetic.
void loop();

//: Publishes the two status bytes the app reads and subscribes to.
void publishStatus(protocol::ProvisioningState state,
                   protocol::ProvisioningError error = protocol::ProvisioningError::NONE);

//: Keeps DEVICE_INFO honest about whether the robot has Wi-Fi and a token.
void setProvisioningFlags(bool provisioned, bool registered);

}  // namespace nura::ble
