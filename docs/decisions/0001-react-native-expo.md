# ADR 0001 — React Native + Expo for the mobile app

- **Status:** Accepted
- **Date:** 2026-09-12
- **Context:** PRD 0

## Context

Nura needs one app on both iOS and Android, built and maintained by a very
small team. Later stages need capabilities that are unambiguously native: BLE
for robot provisioning, background notifications, microphone and camera access,
audio calls, Apple HealthKit and Android Health Connect.

Two things are therefore in tension. We want the speed of a managed
cross-platform toolchain now, and we must not be locked out of native modules
later.

## Decision

Use **React Native with TypeScript, via Expo**, and keep the project
**prebuild-compatible**.

Concretely:

- Expo SDK 57, React Native 0.86, TypeScript in `strict` mode.
- Routing with **expo-router** (file-based, `app/`).
- `ios/` and `android/` are **not** committed. They are generated on demand
  with `npx expo prebuild`, which is what keeps the escape hatch real rather
  than theoretical.
- Every native-capable dependency is installed with `npx expo install` so its
  version matches the SDK.

## Consequences

**Good**

- One codebase and one language across both platforms, and the same TypeScript
  types can describe the API on both sides of the wire.
- Expo Go means a phone can run the app today with no Xcode and no Android
  Studio, which matters for a project that must be demonstrable at every stage.
- Staying prebuild-compatible means adding BLE or HealthKit later is a
  configuration change, not a migration.
- Over-the-air updates and managed builds are available if wanted, without
  being required.

**Costs and risks**

- Expo Go only contains the native modules Expo ships. The first genuinely
  custom native module forces a move to development builds. This is expected
  at the robot-connectivity PRD and is planned for, not a surprise.
- Expo SDK upgrades are a coordinated event roughly twice a year, because the
  SDK pins React Native and its own module versions together.
- iOS builds still require macOS. Android is the day-to-day development
  target; iOS is configured (bundle identifier, icons, splash, tablet support)
  and buildable on a Mac.

## Notes

- Web is **not** a target. The `web` script and favicon that the Expo template
  generates were removed rather than left half-working, since `react-dom` and
  `react-native-web` are not installed. Adding web later means installing both
  and restoring the script.
- A `react-dom` override is pinned in `mobile/package.json`. Some of
  expo-router's web-facing dependencies pull a newer `react-dom` than the
  `react` version Expo pins, which npm rejects as a peer conflict. Pinning
  `react-dom` to the matching `react` version resolves it honestly, rather than
  hiding the conflict behind `--legacy-peer-deps`.

## Alternatives considered

- **Flutter.** Strong UI story, but it would mean Dart alongside the Python
  backend and TypeScript tooling, and no shared types with the API. The native
  bridging work for BLE and the health platforms is comparable, so the
  cross-platform benefit does not offset the extra language.
- **Native iOS and Android separately.** Best possible platform integration and
  the obvious choice at scale, but it doubles the surface a small team must
  build and keep in step. Not justifiable for this project.
- **React Native without Expo (bare CLI).** Maximum native control from day
  one, at the cost of hand-managing native projects, signing and upgrades
  immediately. Expo with prebuild gets the same ceiling, later, when the need
  is real.
