# Nura

Nura is a desktop health companion: a small robot built around a Seeed Studio
XIAO ESP32-S3, a cross-platform mobile app, and a backend service.

This repository is at **PRD 2 — Robot Pairing, BLE Discovery & Wi-Fi
Provisioning**. It is a working technical skeleton, not yet a health app: a
branded five-tab app with Light/Dark/System themes, account creation and
onboarding, a FastAPI backend, and the firmware and app flow for connecting a
robot.

> **The robot has not been built yet.** The pairing flow, the firmware and the
> backend are written and tested as far as software allows — the cryptography
> matches published test vectors on both sides — but no BLE connection, Wi-Fi
> provisioning or device registration has ever run on hardware.

> **Nura does not diagnose illness, prescribe treatment or change medication
> doses.** No health tracking, AI, caregiver or emergency functionality exists
> at this stage.

## Contents

```text
nura/
├── mobile/      React Native + Expo app (TypeScript)
├── backend/     FastAPI + PostgreSQL service
├── firmware/    XIAO ESP32-S3 robot firmware (PlatformIO)
├── docs/        Architecture notes and decision records
└── .env.example Template for every environment variable
```

## Prerequisites

Versions this project was built and verified against:

| Tool       | Version | Notes                            |
| ---------- | ------- | -------------------------------- |
| Node.js    | 24.19.0 | Ships npm 11.17.0                |
| Python     | 3.12.10 | 3.11+ works                      |
| PostgreSQL | 17.11   | Local server, or Supabase-hosted |
| Git        | 2.55    |                                  |

On Windows you can install all of them with winget:

```bash
winget install OpenJS.NodeJS.LTS Python.Python.3.12 PostgreSQL.PostgreSQL.17 Git.Git
```

To run the app on a phone, also install **Expo Go** from the App Store or Play
Store. Bluetooth pairing does not work in Expo Go — that needs a development
build and, on Android, **Android Studio** for its SDK (see section 5).
Building the robot firmware needs **PlatformIO**, which section 6 installs.

> After installing anything, open a **new** terminal so the updated `PATH` is
> picked up.

---

## 1. Database setup

Create a database and a role for the app. Run this once.

On Windows, `psql` lives in `C:\Program Files\PostgreSQL\17\bin`; add that
folder to your `PATH` or use the full path to `psql.exe`.

```bash
psql -U postgres -c "CREATE ROLE nura LOGIN PASSWORD 'change_me_locally';"
```

```bash
psql -U postgres -c "CREATE DATABASE nura_dev OWNER nura;"
```

Check it worked:

```bash
psql -U nura -h localhost -d nura_dev -c "SELECT current_database();"
```

> Choose your own password. It is a local development credential, it goes only
> in `backend/.env`, and that file is gitignored.

## 2. Environment variables

`.env.example` in the repository root documents every variable and which file
it belongs in. Create the backend one:

```bash
cd backend
cp ../.env.example .env
```

Then edit `backend/.env` so it contains at least:

```text
DATABASE_URL=postgresql+psycopg://nura:change_me_locally@localhost:5432/nura_dev
APP_ENV=development
```

The mobile app needs **no** `.env` for local development. It works out where
the backend is from the Expo dev server's address, which is what lets a
physical phone reach your computer without you editing an IP address. Set
`EXPO_PUBLIC_API_URL` in `mobile/.env` only when you want to point the app at
a different backend.

Never put a secret in an `EXPO_PUBLIC_*` variable — Expo inlines them into the
app bundle, where anyone can read them.

## 2b. Authentication setup (Supabase)

Sign-in needs a real provider. Without one the app still runs, but the sign-in
screen says plainly that authentication is not configured and every provider
button is disabled — it never pretends a login succeeded.

1. Create a project at [supabase.com](https://supabase.com). The free tier is
   enough for email sign-in.
2. **Project Settings → API** — copy the **Project URL** and the **anon /
   public** key.
3. **Authentication → Providers → Email** — make sure it is enabled. For local
   testing, turn **Confirm email off**, otherwise sign-up waits on an inbox
   round trip.
4. Put the values in both env files:

```text
# mobile/.env
EXPO_PUBLIC_SUPABASE_URL=https://<project>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<anon key>

# backend/.env
SUPABASE_URL=https://<project>.supabase.co
```

5. Restart Metro with `npx expo start --clear` — `EXPO_PUBLIC_*` values are
   baked in at bundle time, so a running server will not pick them up.

The anon key is designed to be public and is safe in the app bundle; it grants
nothing on its own. The backend needs only the project **URL**: it verifies
tokens against the project's public JWKS endpoint, so no shared secret is
involved. `SUPABASE_JWT_SECRET` exists for older projects that still sign with
HS256 — leave it blank otherwise.

### The other providers

| Provider   | What it additionally needs                                             |
| ---------- | ---------------------------------------------------------------------- |
| **Email**  | Nothing beyond the steps above.                                        |
| **Google** | An OAuth client in Google Cloud, the secret added to Supabase → Providers → Google, and the client id in `EXPO_PUBLIC_GOOGLE_CLIENT_ID`. |
| **Apple**  | An Apple Developer account ($99/yr), a Services ID and key configured in Supabase → Providers → Apple. Native Sign in with Apple is iOS-only, so it needs a Mac or an iOS device to exercise. |
| **Phone**  | An SMS provider (Twilio, MessageBird, Vonage) configured in Supabase → Providers → Phone. Sending real messages costs money. |

Add this redirect URL under **Authentication → URL Configuration** so the OAuth
providers can return to the app:

```text
nura://auth/callback
```

In Expo Go the redirect is an `exp://…` URL instead, which Supabase must also
allow; the exact address is printed when Metro starts.

## 3. Run the backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

```bash
# Windows (Git Bash)
source .venv/Scripts/activate
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install dependencies and create the database tables:

```bash
pip install -r requirements-dev.txt
```

```bash
alembic upgrade head
```

Start the server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` matters: a phone on your Wi-Fi cannot reach a server bound
only to `localhost`.

Verify it:

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "service": "nura-api" }
```

Interactive API docs are at <http://localhost:8000/docs>.

## 4. Run the mobile app

In a second terminal, with the backend still running:

```bash
cd mobile
npm install
```

```bash
npm start
```

Expo prints a QR code. Then:

- **Android phone** — open Expo Go and scan the QR code.
- **iPhone** — scan the QR code with the Camera app.
- **Android emulator** — press `a` in the Expo terminal, or `npm run android`.
- **iOS simulator** — press `i`, or `npm run ios` (requires macOS and Xcode).

Your phone and computer must be on the same Wi-Fi network.

When it loads you should see the Today screen with a green **Nura services
connected** chip. That chip appears in development builds only and confirms
the app reached `GET /health`. If the backend is not running it shows an amber
**Nura services unavailable** chip instead — that is handled, not a crash.

## 5. Bluetooth needs a development build

**Expo Go cannot do Bluetooth.** It has no Nura-specific native code in it, so
pairing screens will load but finding a robot will not work. Everything else —
sign-in, onboarding, themes — works in Expo Go as before.

To use Bluetooth you need a *development build*: your own app binary, with
Nura's native modules in it, that Metro still hot-reloads into.

**Android (free).** Install Android Studio, open it once, and let its setup
wizard install the Android SDK — that step is a GUI and cannot be scripted.
Then, with a phone plugged in and USB debugging enabled:

```bash
cd mobile
npx expo run:android
```

That builds the app, installs it, and starts Metro. After the first build,
`npm start` and opening the Nura app on the phone is enough.

**iOS.** Needs a Mac with Xcode (`npx expo run:ios`), or Expo's cloud build
plus a paid Apple Developer account. Nura's iOS Bluetooth configuration is
written but has never been built or run.

The generated `android/` and `ios/` directories are not tracked in git; delete
them and re-run the command to start clean.

## 6. The robot firmware

Building and flashing the XIAO ESP32-S3, what the robot does in each state,
and how to read its serial log are in
[firmware/xiao_esp32s3/README.md](firmware/xiao_esp32s3/README.md). Briefly:

```bash
python -m venv firmware/.venv && firmware/.venv/Scripts/pip install platformio
```

```bash
cd firmware/xiao_esp32s3 && ../.venv/Scripts/pio run -e xiao_esp32s3
```

Add `-t upload` with a board connected. `pio test -e xiao_esp32s3` runs the
firmware's crypto tests on the board.

## 7. Pairing a robot, once one exists

This procedure has **never been carried out** — there is no robot. It is the
intended sequence, written down so it can be followed the first time.

1. Start the backend with `--host 0.0.0.0`, and check the phone can reach it.
2. Flash a XIAO ESP32-S3 and power it. With no display fitted, watch the serial
   monitor: the pairing code is printed there as a development fallback.
3. Open the app, finish onboarding, and tap **Connect Nura → Find my Nura**.
   Allow Bluetooth when asked.
4. The robot should appear as `Nura • XXXX`. Pick it.
5. Type the six-digit code. A wrong code must be refused; three wrong codes
   must end the attempt.
6. Enter your 2.4 GHz network and its password, then **Connect**.
7. Watch the stages. The app should reach "Nura is ready" only after the
   backend has had a heartbeat — check the robot's serial log shows
   `[CLOUD] registered` and the backend's `last_seen_at` is moving.
8. Name the robot, then confirm on Today that it shows as online.
9. Power-cycle the robot: it should rejoin Wi-Fi by itself, stay linked, and
   not advertise over Bluetooth.
10. Hold BOOT for 3 seconds and re-run the flow with a different network: the
    device record must stay the same one, not a second entry.

## 8. Run the tests

Mobile:

```bash
cd mobile
npm test
```

Backend (with the virtual environment active):

```bash
cd backend
pytest
```

Firmware (on a connected board — they run on the ESP32 itself):

```bash
cd firmware/xiao_esp32s3
../.venv/Scripts/pio test -e xiao_esp32s3
```

The mobile suite needs nothing running. It covers the pairing flow end to end
against a simulated robot that runs the real protocol, and checks the app's
cryptography against RFC 9382's test vectors. One test parses the firmware's
`protocol.h` and fails if the app and the robot disagree about any UUID,
message type or status code.

The backend suite **does need PostgreSQL running**. It creates a separate
`nura_test` database on first run, applies the real migrations to it, and rolls
each test back afterwards — so the tests also prove the migrations produce a
schema the code works against. Your `nura_dev` data is never touched. Neither
suite needs a Supabase project or a network connection: tokens are signed with
a key pair generated inside the test run and verified by the real production
verifier.

## 9. Code quality

```bash
cd mobile
npm run lint
npm run typecheck
npm run format
```

```bash
cd backend
ruff check .
ruff format .
mypy app alembic
```

## Database migrations

Every schema change is migration-driven. After editing a model in
`backend/app/models/`:

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
```

```bash
alembic upgrade head
```

Always read the generated file before applying it — autogenerate is a good
first draft, not a finished migration. Generated migrations are automatically
formatted with Ruff, which needs the virtual environment to be active.

Other useful commands:

```bash
alembic current
alembic downgrade -1
alembic upgrade head --sql
```

## Switching to Supabase

The backend reaches PostgreSQL through `DATABASE_URL` and nothing else, so
moving to Supabase-hosted PostgreSQL is a one-line change: copy the connection
string from the Supabase dashboard into `backend/.env` and run
`alembic upgrade head`. See
[the database decision record](docs/decisions/0002-fastapi-postgresql.md).

## Where things live

| Path                      | What it holds                                   |
| ------------------------- | ----------------------------------------------- |
| `mobile/app/`             | Screens and routing (expo-router, file-based)   |
| `mobile/src/theme/`       | Design tokens, Light/Dark themes, ThemeProvider |
| `mobile/src/components/`  | Reusable UI components                          |
| `mobile/src/services/`    | API client, auth surface, secure storage        |
| `mobile/src/store/`       | Global state (Zustand)                          |
| `mobile/assets/branding/` | Supplied Nura logo files                        |
| `mobile/src/services/provisioning/` | BLE transport, SPAKE2, provisioning flow |
| `backend/app/api/`        | HTTP routes (`/health`, `/api/v1/*`)            |
| `backend/app/models/`     | SQLAlchemy models                               |
| `backend/alembic/`        | Migrations                                      |
| `firmware/xiao_esp32s3/`  | Robot firmware (PlatformIO)                     |
| `docs/device/`            | The phone-to-robot provisioning protocol        |
| `docs/`                   | Architecture overview and decision records      |

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Safety and emergency architecture](docs/architecture/safety-and-emergency.md)
- [API reference](docs/api/README.md)
- [Provisioning protocol](docs/device/provisioning-protocol.md) — UUIDs,
  messages, states and the security model for phone-to-robot setup
- [Firmware](firmware/xiao_esp32s3/README.md)
- Decision records:
  [React Native + Expo](docs/decisions/0001-react-native-expo.md),
  [FastAPI + PostgreSQL](docs/decisions/0002-fastapi-postgresql.md),
  [Device connectivity](docs/decisions/0003-device-connectivity.md),
  [Supabase Auth](docs/decisions/0004-supabase-auth.md),
  [BLE pairing](docs/decisions/0005-ble-pairing.md)

## Known issues

**Onboarding interactions are not covered by mobile tests.** Under this Jest
setup (React 19 + React Native Testing Library 14 + expo-router), a screen's
local `useState` does not re-render: the press handler runs, but the component
never updates, and React reports "overlapping act() calls". Anything that
writes to the Zustand store or the network is testable and is tested; anything
that only changes local component state — selecting a card, then pressing
Continue — is not. The rules those steps enforce (the consent gate, profile
validation, progression order, per-user access control) are covered against a
real database in `backend/tests/`, so the behaviour is verified, just not
through the UI. Tried without success: mocking `react-native-screens` freeze,
setting `IS_REACT_ACT_ENVIRONMENT`, draining timers inside `act`, and
navigating directly instead of through the gate.

**Only email sign-in has been verified end to end.** Google, Apple and phone
are implemented against the Supabase SDK and documented above, but marked
unverified: Apple needs macOS or an iOS device plus a paid developer account,
and phone needs a paid SMS provider. None of them simulate success — an
unconfigured provider is reported as unavailable.

**The app has not been run on a physical device or emulator.** The bundle
compiles and the suites pass, but no run on real hardware has happened yet.

**No part of robot pairing has run on hardware, because the robot does not
exist.** What that means in practice:

- BLE discovery, connection, the code exchange, Wi-Fi provisioning, the claim
  and heartbeats have never happened between a real phone and a real board.
- The firmware compiles for all three environments and its crypto matches RFC
  9382's vectors and a vector produced by the app, but its tests have never
  been executed — they run on the board.
- The display and audio drivers are written blind: the panel driver chip, the
  amplifier and every pin in `board_config.h` are assumptions.
- With no screen fitted, a development build prints the pairing code to the
  serial log. That is for developers only; a shipped robot needs the display.
- The backend and app sides of pairing *are* tested: the backend suite runs
  against a real database, and the mobile suite drives the whole flow against a
  simulated robot speaking the real protocol.

**The spoken introduction is a placeholder.** There is no voice clip yet, so a
fitted speaker plays a two-note chime instead of "Hi. I'm Nura."

## Troubleshooting

**The app shows "Nura services unavailable".** Check the backend is running and
was started with `--host 0.0.0.0`. Confirm the phone and computer share a
network, and that Windows Firewall is not blocking port 8000 — allow Python
through on private networks when prompted.

**`ValidationError: database_url Field required`.** `backend/.env` is missing or
has no `DATABASE_URL`. See step 2.

**`connection to server at "localhost" failed`.** PostgreSQL is not running. On
Windows, check with `Get-Service postgresql*`.

**`node`, `python` or `psql` not recognised.** Open a new terminal so `PATH`
updates, or add the install folder to `PATH` yourself.

**Metro serves a stale bundle.** Run `npx expo start --clear`.

**"Find my Nura" finds nothing.** Bluetooth does not work in Expo Go — you
need the development build from section 5. Otherwise: check the robot is
powered and in pairing mode, that Bluetooth is on, and, on Android 11 or
older, that the phone's Location setting is on, which the OS requires for any
Bluetooth scan.

**The robot's log says `[CLOUD] registered` but the app says it is not
online.** The robot reached the backend once and then could not send
heartbeats, or it was handed an address it cannot reach. Check
`DEVICE_API_BASE_URL` (or, when blank, that the phone reached the backend on
its LAN address rather than `localhost`), and that the backend was started with
`--host 0.0.0.0`.

**PlatformIO cannot find the board.** Hold **BOOT**, tap **RESET**, release
**BOOT** to force the bootloader, then pass `--upload-port COMx`.
