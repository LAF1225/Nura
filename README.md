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

Neither suite needs a running backend or database.

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
  [Device connectivity](docs/decisions/0003-device-connectivity.md)

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
