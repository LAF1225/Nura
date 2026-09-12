# Nura

Nura is a desktop health companion: a small robot built around a Seeed Studio
XIAO ESP32-S3, a cross-platform mobile app, and a backend service.

This repository is at **PRD 0 — Project Foundation & Architecture**. It is a
working technical skeleton, not yet a health app: a branded five-tab app with
Light/Dark/System themes, a FastAPI backend, and a migrated PostgreSQL schema.

> **Nura does not diagnose illness, prescribe treatment or change medication
> doses.** No health tracking, AI, caregiver or emergency functionality exists
> at this stage.

## Contents

```text
nura/
├── mobile/      React Native + Expo app (TypeScript)
├── backend/     FastAPI + PostgreSQL service
├── firmware/    XIAO ESP32-S3 firmware (empty until the robot PRD)
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
Store. Android Studio is only needed for native builds, not for PRD 0.

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

### Native builds

The project is prebuild-compatible, so native capabilities (BLE, background
notifications, HealthKit, Health Connect) can be added later:

```bash
cd mobile
npx expo prebuild
```

This generates `ios/` and `android/` directories, which are intentionally not
tracked in git.

## 5. Run the tests

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

The mobile suite needs nothing running.

The backend suite **does need PostgreSQL running**. It creates a separate
`nura_test` database on first run, applies the real migrations to it, and rolls
each test back afterwards — so the tests also prove the migrations produce a
schema the code works against. Your `nura_dev` data is never touched. Neither
suite needs a Supabase project or a network connection: tokens are signed with
a key pair generated inside the test run and verified by the real production
verifier.

## 6. Code quality

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
| `backend/app/api/`        | HTTP routes (`/health`, `/api/v1/*`)            |
| `backend/app/models/`     | SQLAlchemy models                               |
| `backend/alembic/`        | Migrations                                      |
| `docs/`                   | Architecture overview and decision records      |

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Safety and emergency architecture](docs/architecture/safety-and-emergency.md)
- [API reference](docs/api/README.md)
- Decision records:
  [React Native + Expo](docs/decisions/0001-react-native-expo.md),
  [FastAPI + PostgreSQL](docs/decisions/0002-fastapi-postgresql.md),
  [Device connectivity](docs/decisions/0003-device-connectivity.md),
  [Supabase Auth](docs/decisions/0004-supabase-auth.md)

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
