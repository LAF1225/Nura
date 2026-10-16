# Nura firmware

Firmware for the Nura robot, built around the **Seeed Studio XIAO ESP32-S3**.

```text
firmware/
├── xiao_esp32s3/     the robot firmware (PlatformIO)
└── .venv/            PlatformIO itself, not tracked in git
```

Everything — how to build, flash, test, and what the robot does in each
situation — is in [xiao_esp32s3/README.md](xiao_esp32s3/README.md).

> **The robot has not been built.** The firmware compiles and its cryptography
> matches published test vectors, but nothing in this directory has run on
> hardware. PRD 11 added the whole presentation layer — the protocol, the
> renderers, the display and audio driver abstractions and the state machine —
> and **no frame has been drawn on a panel, no sound has been played, and no
> presentation has ever been acknowledged by a real device.** The physical
> drivers report `not_verified` rather than `available`, which is the honest
> state for code that compiles and has never been seen to work.

## Role

```text
First-time setup / recovery          Normal operation
───────────────────────────          ────────────────
  Mobile app                           Robot ──Wi-Fi──▶ Backend
      │ BLE                                                ▲
      ▼                                                    │
  XIAO ESP32-S3                                  Mobile app ┘
```

- **BLE** for discovery, verifying the physical unit, receiving Wi-Fi
  credentials, and recovery when the network changes.
- **Wi-Fi** for normal operation, talking to the backend rather than the phone.

The wire format is
[the provisioning protocol](../docs/device/provisioning-protocol.md); the
reasoning behind the library and crypto choices is
[ADR 0005](../docs/decisions/0005-ble-pairing.md), and the two-transport
strategy is [ADR 0003](../docs/decisions/0003-device-connectivity.md).

## What the backend provides

| Column              | Firmware relevance                                     |
| ------------------- | ------------------------------------------------------ |
| `hardware_id`       | Derived from the factory MAC; what BLE advertises       |
| `device_type`       | `xiao-esp32-s3`                                        |
| `firmware_version`  | Reported on claim and on every heartbeat                |
| `last_seen_at`      | Updated by heartbeats; the only source of online status |

`hardware_id` is unique but is **not** the primary key: the backend's own UUID
is the device's identity.
