# Nura firmware

**Empty by design.** Firmware for the Nura robot is not part of PRD 0 and must
not be added until the robot-connectivity PRD.

## Target hardware

**Seeed Studio XIAO ESP32-S3** — Bluetooth Low Energy and Wi-Fi, which is what
makes the two-transport strategy possible.

## Planned role

```text
First-time setup / recovery          Normal operation
───────────────────────────          ────────────────
  Mobile app                           Robot ──Wi-Fi──▶ Backend
      │ BLE                                                ▲
      ▼                                                    │
  XIAO ESP32-S3                                  Mobile app ┘
```

- **BLE** for first-time discovery, verifying the physical unit, receiving
  Wi-Fi credentials, and recovery when the network changes.
- **Wi-Fi** for all normal operation, talking to the backend rather than to the
  phone directly.

The transport between robot and backend — WebSockets or MQTT — is deliberately
undecided. See
[ADR 0003](../docs/decisions/0003-device-connectivity.md).

## What the backend already provides

The `devices` table exists, so firmware work has a schema to target:

| Column              | Firmware relevance                                    |
| ------------------- | ----------------------------------------------------- |
| `device_identifier` | Provisioned on the hardware; what BLE advertises      |
| `device_type`       | `xiao-esp32-s3`                                       |
| `firmware_version`  | Reported by the device on check-in                    |
| `last_seen_at`      | Updated when the device contacts the backend          |

`device_identifier` is unique but is **not** the primary key. The backend's own
UUID is the device's identity — see
[the system overview](../docs/architecture/system-overview.md).
