# System overview

Status: PRD 0 — Project Foundation & Architecture.

## The pieces

```text
┌──────────────────────┐
│   Nura mobile app    │  React Native + Expo (TypeScript)
│   iOS and Android    │  The detailed control and information layer
└──────────┬───────────┘
           │ HTTPS / JSON
           ▼
┌──────────────────────┐
│   FastAPI backend    │  Owns authorisation and all health logic
└──────────┬───────────┘
           │ SQLAlchemy
           ▼
┌──────────────────────┐
│  PostgreSQL database │  Local in development, Supabase-hosted in the prototype
└──────────────────────┘

┌──────────────────────┐
│  Nura robot          │  Seeed Studio XIAO ESP32-S3
│  (later PRD)         │  Quick voice interaction, reminders, ambient presence
└──────────────────────┘
```

The robot handles short, ambient interactions. The mobile app is where detail
lives. The backend is the only component trusted with authorisation.

## What exists today

| Area           | State                                                       |
| -------------- | ----------------------------------------------------------- |
| Navigation     | Five tabs: Today, Health, Care, Nura, More                  |
| Theming        | Light, Dark and System; persisted locally                   |
| Networking     | Central API client with typed errors                        |
| Server state   | TanStack Query                                              |
| Global state   | Zustand, with theme and device selection persisted          |
| Authentication | Method surface only; no provider configured (see PRD 1)     |
| Database       | `users`, `user_settings`, `devices`, created by a migration |
| Endpoints      | `GET /health`, `GET /api/v1/version`                        |

Deliberately absent: symptom and medication tracking, appointments, AI or
chat, caregiver features, emergency detection, push notifications, HealthKit,
Health Connect, and robot pairing.

## Mobile architecture

```text
mobile/
├── app/                      Routes (expo-router, file-based)
│   ├── _layout.tsx           Providers: safe area, query client, theme
│   ├── (tabs)/               The five primary sections
│   ├── appearance.tsx        More → Appearance
│   └── +not-found.tsx
└── src/
    ├── components/           Screen, Card, Button, AppText, List, …
    ├── constants/            Runtime config; the only reader of process.env
    ├── hooks/                useBackendHealth
    ├── navigation/           Tab definitions (single source of tab order)
    ├── services/
    │   ├── api/              client, typed errors, endpoint functions
    │   ├── auth/             AuthService surface
    │   └── storage/          expo-secure-store wrapper
    ├── store/                Zustand store
    ├── theme/                tokens, themes, ThemeProvider
    ├── types/                Shared types
    └── utils/                logger
```

Feature folders (`medications/`, `symptoms/`, `caregivers/`, `safety/`, …) are
created when the PRD that needs them arrives, not in advance.

### Rules the code follows

- **One place knows the network.** Only `src/services/api/client.ts` calls
  `fetch`. Only `src/constants/config.ts` reads `process.env`.
- **Two kinds of state.** Zustand holds app-wide preferences; TanStack Query
  owns anything fetched from the backend. Server data is not mirrored into
  Zustand.
- **Errors are typed, messages are human.** Every failure becomes an `ApiError`
  with a `kind` (`offline`, `unavailable`, `timeout`, `unauthorized`,
  `notFound`, `validation`, `server`, `configuration`). A raw exception is
  never shown to a user.
- **Secrets go in secure storage.** Tokens use `expo-secure-store`
  (Keychain / Keystore). AsyncStorage holds only harmless preferences such as
  the theme.

### Theme resolution

The active theme comes from two inputs: the stored preference and the device
appearance.

```text
themePreference ('system' | 'light' | 'dark')   ← persisted to AsyncStorage
              +
useColorScheme() ('light' | 'dark' | 'unspecified')
              ↓
        resolveThemeName()
              ↓
    lightTheme | darkTheme
```

`resolveThemeName` is a plain function, which is why it can be unit-tested
without rendering. Dark mode is a separate palette rather than an inversion of
Light, and avoids pure black.

The root layout holds the splash screen until the persisted preference has been
read, so the app never paints the wrong theme and then snaps to the stored one.

### Finding the backend in development

A phone cannot reach `localhost` — that would be the phone. `EXPO_PUBLIC_API_URL`
wins when set; otherwise, in development, the app takes the host Expo is already
serving the bundle from and uses port 8000. A physical device therefore works
with no configuration. Release builds must set the variable explicitly.

## Backend architecture

```text
backend/
├── app/
│   ├── api/
│   │   ├── health.py         GET /health (unversioned)
│   │   └── v1/router.py      Everything under /api/v1
│   ├── core/                 Settings and logging
│   ├── db/                   Engine, session, declarative base
│   ├── models/               User, UserSettings, Device
│   ├── schemas/              Pydantic request/response models
│   └── main.py
├── alembic/                  Migrations
└── tests/
```

`/health` is unversioned on purpose: "is this process up?" does not change
shape between API versions. It does not touch the database, so a database blip
cannot make the app's connection indicator report the wrong thing. A readiness
endpoint that does check dependencies can be added when something needs one.

Versioned routes live under `/api/v1` so a future `/api/v2` can coexist while
older app builds keep working. `GET /api/v1/version` returns
`minimum_app_version` for exactly that reason.

### Data model

```text
users
  id                uuid, primary key    ← the identity everything references
  auth_provider_id  unique, indexed      ← subject from the auth provider
  email             unique, nullable     ┐ sign-up can be by phone
  phone             unique, nullable     ┘ or by email
  created_at, updated_at

user_settings                  devices
  id          uuid, pk           id                uuid, pk
  user_id     unique → users     owner_user_id     → users (cascade)
  theme       system|light|dark  device_identifier unique, indexed
  language                       display_name
  created_at, updated_at         device_type
                                 firmware_version
                                 last_seen_at
                                 created_at, updated_at
```

`theme` is constrained at the database level, not only in application code.
Both child tables cascade on user deletion.

## Security posture

These hold now and constrain every later PRD:

- **The server decides.** Authorisation is never left to the client. A request
  that supplies a user id does not thereby gain access to that user's data —
  the authenticated identity is what counts, and it comes from the verified
  token, never from the request body.
- **Health data is sensitive.** Every future health endpoint must confirm the
  authenticated user is entitled to the specific resource requested.
- **Caregiver access will be explicit.** Sharing requires a granted permission
  record, never an implicit relationship.
- **Camera, microphone and conversation data need retention rules** before any
  of it is captured. Nothing is uploaded permanently by default.
- **HTTPS everywhere outside local development.** Plain HTTP is for `localhost`
  only.
- **Secrets never enter the repository.** `.env.example` carries names only.

## Device connectivity

BLE is for first contact and recovery; normal operation is over Wi-Fi through
the backend.

```text
Provisioning                     Normal operation
────────────                     ────────────────
Mobile app                       Robot ──Wi-Fi──▶ Backend
    │ BLE                                            ▲
    ▼                                                │
XIAO ESP32-S3                              Mobile app ┘
```

The app never requires a standing Bluetooth connection for ordinary use. See
[the connectivity decision record](../decisions/0003-device-connectivity.md).

Device identity, which later PRDs must not conflate:

| Field               | Meaning                                            |
| ------------------- | -------------------------------------------------- |
| `id`                | Internal UUID. The stable identity.                |
| `device_identifier` | Provisioned on the hardware; what BLE reports.     |
| `display_name`      | User-facing and editable ("Bedroom Nura").         |

The owner's own name is never the device's identity.

## Nura modes

```ts
type NuraMode = 'normal' | 'focus' | 'sleep' | 'privacy' | 'safety' | 'emergency';
```

Declared so later PRDs share one vocabulary. Nothing reads or switches on these
values yet, and no behaviour is attached to them.

## Real-time communication

Not implemented. WebSockets and MQTT both remain open options; the choice is
deferred until robot communication is actually built, so it can be made against
real requirements.

## Medical safety boundary

Nura must never autonomously diagnose illness, prescribe treatment, change
medication doses, or claim an observed event is a confirmed diagnosis.

Acceptable future phrasing describes and defers:

- "Your symptoms appear to have worsened. Consider contacting a healthcare
  professional."
- "Nura noticed unusual movement." — never "Nura detected a seizure."

Health and safety logic stays separable from general assistant functionality,
so the companion features can evolve without touching the safety path. The
escalation design is written up in
[safety-and-emergency.md](safety-and-emergency.md) and is documented only —
none of it is implemented.
