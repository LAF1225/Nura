# ADR 0003 — Device connectivity strategy

- **Status:** Accepted (architecture only; nothing implemented in PRD 0)
- **Date:** 2026-09-12
- **Context:** PRD 0

## Context

The Nura robot is built around a **Seeed Studio XIAO ESP32-S3**, which has both
Bluetooth Low Energy and Wi-Fi. The phone has to be able to do two quite
different things:

1. Meet a brand-new robot that has never been on the network, and get it onto
   Wi-Fi.
2. Interact with a robot that is already set up, day to day.

These pull in opposite directions. The first can only happen over a direct
radio link, because there is no network path yet. The second wants to work when
the phone is in another room, or not at home at all.

## Decision

**BLE for provisioning and recovery. Wi-Fi through the backend for everything
else.**

```text
First-time setup / recovery          Normal operation
───────────────────────────          ────────────────
  Mobile app                           Robot ──Wi-Fi──▶ Backend
      │ BLE                                                ▲
      ▼                                                    │
  XIAO ESP32-S3                                  Mobile app ┘
```

BLE is used for:

- first-time discovery of a nearby robot,
- verifying it is the right physical unit,
- handing over Wi-Fi credentials,
- recovery and re-pairing when the network changes or the robot cannot connect.

Everything else — state, reminders, settings, health data — goes over Wi-Fi via
the backend. **The app never requires a standing Bluetooth connection for
ordinary use.**

## Consequences

**Good**

- The app works away from home. If Nura only spoke BLE, the app would be
  useless outside the room, which would defeat the caregiver and remote
  check-in features entirely.
- The backend stays the single source of truth. Phone and robot both converge
  on it instead of trying to reconcile two copies of state over a peer link.
- Authorisation stays server-side. A BLE-first design would push permission
  decisions onto the devices, which is exactly where health data decisions
  should not live.
- Recovery has a defined path. A robot that cannot reach Wi-Fi is not bricked,
  because BLE remains available as the way back in.
- Battery and reliability both benefit from not holding a BLE link open.

**Costs and risks**

- Two transports to implement and test, each with its own permission model:
  Bluetooth and location-adjacent permissions on Android, Bluetooth usage
  descriptions on iOS.
- The robot depends on the household network for normal operation, so Wi-Fi
  outages degrade it. Which behaviours must survive offline is a question for
  the PRD that owns them; PRD 0 only prepares for offline states.
- BLE provisioning is the security-sensitive moment — it is when credentials
  cross — and needs its own careful design, including how the user confirms
  they are pairing with their own robot.

## Device identity

Three distinct identifiers, which later PRDs must not conflate:

| Concept             | Example         | Rules                                    |
| ------------------- | --------------- | ---------------------------------------- |
| `id`                | a UUID          | Internal, backend-issued. The identity.  |
| `device_identifier` | hardware id     | Provisioned on the device; BLE reports it. Unique, but not the primary key. |
| `display_name`      | "Bedroom Nura"  | User-facing, editable, never identity.   |

The owner's own display name is never the device's identity. A household may
have several units, and a renamed robot is still the same robot.

## Not decided yet

How the robot and backend talk once connected — **WebSockets or MQTT** —
is deliberately left open. Both remain candidates. The choice depends on
requirements that do not exist yet (message volume, latency tolerance, whether
the robot must receive pushes while idle, broker operational cost), so it is
deferred to the robot-communication PRD rather than guessed at now. PRD 0
implements no real-time transport at all.

## PRD 0 scope

Nothing here is built. PRD 0 contains only:

- the `devices` table and the `Device` type, with the identity rules above,
- `selectedDeviceId` in the app store,
- no BLE library, no pairing UI, no Wi-Fi provisioning, no firmware.

`firmware/` stays empty until the robot PRD.
