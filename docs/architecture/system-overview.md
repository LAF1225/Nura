# System overview

Status: PRD 2 — Robot Pairing, BLE Discovery & Wi-Fi Provisioning.

> The robot itself has not been built. The firmware and the pairing flow exist
> and are tested as far as software allows, but no part of the phone-to-robot
> path has run on hardware.

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

| Area           | State                                                                          |
| -------------- | ------------------------------------------------------------------------------ |
| Navigation     | Five tabs, plus a separate onboarding stack shown until setup is finished      |
| Theming        | Light, Dark and System; persisted locally                                      |
| Networking     | Central API client with typed errors; attaches the bearer token automatically  |
| Server state   | TanStack Query                                                                 |
| Global state   | Zustand — theme, device selection and last onboarding step persisted           |
| Authentication | Supabase Auth. Email verified end to end; Google, Apple and phone implemented but unverified |
| Onboarding     | Welcome → auth → setup mode → profile → preferences → consent → ready to pair → robot connected |
| Pairing        | BLE discovery, SPAKE2 code verification, encrypted Wi-Fi provisioning, backend claim — written and tested in software, never run on hardware |
| Firmware       | `firmware/xiao_esp32s3`, compiles for three environments; no board exists to run it |
| Database       | `users`, `user_settings`, `profiles`, `account_profile_roles`, `devices`, `provisioning_sessions` |
| Endpoints      | `/health`, `/api/v1/version`, `/api/v1/me`, `/api/v1/onboarding`, `/api/v1/profiles`, `/api/v1/devices` |

Deliberately absent: symptom and medication tracking, appointments, AI or
chat, caregiver permissions, emergency detection, push notifications,
HealthKit and Health Connect.

### How a robot joins an account

```text
App ──BLE──▶ Robot          six-digit code on the robot's screen proves
    ◀───────                the user picked the right physical unit (SPAKE2)
App ──HTTPS─▶ Backend       short-lived, single-use provisioning token
App ──BLE──▶ Robot          Wi-Fi details + token, AES-GCM under the session key
              Robot ──▶ Backend   claim: token + the robot's own secret
              Robot ──▶ Backend   heartbeat
App ──HTTPS─▶ Backend       "is it online?" -- the only thing that decides success
```

The app never decides a robot is online, and the robot never sees the user's
access token. The full wire format is in
[the provisioning protocol](../device/provisioning-protocol.md); the crypto
reasoning is [ADR 0005](../decisions/0005-ble-pairing.md).

### Account holder vs. the person Nura is for

The `users` table is really the **account** — the identity that signs in. The
person Nura is set up for lives in `profiles`. In assisted setup those are
different people, so keeping them apart means assisted setup needs no
special-casing, and the caregiver model in a later PRD has somewhere to attach.

`account_profile_roles` joins them, with exactly two roles for now: `self` (the
account holder is the person Nura is for) and `setup_helper` (they are setting
it up for someone else). There are no permission columns yet — caregiver
permissions, invitations and emergency roles are later PRDs.

Onboarding progress lives in one column, `users.onboarding_status`. The step
number shown in the UI is derived from it rather than stored separately, so the
two can never disagree about where to resume.

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
users  (the account: who signs in)
  id                 uuid, primary key   ← the identity everything references
  auth_provider_id   unique, indexed     ← `sub` from the auth provider
  email              unique, nullable    ┐ sign-up can be by phone
  phone              unique, nullable    ┘ or by email
  setup_mode         self | assisted     ← null until chosen
  onboarding_status  state machine       ← single source of truth for progress
  terms_accepted_at        nullable      ┐ separate, and timestamps rather than
  privacy_acknowledged_at  nullable      ┘ booleans, so there is a record of when
  created_at, updated_at

profiles  (the person Nura is for)        account_profile_roles
  id              uuid, pk                  id          uuid, pk
  preferred_name  required                  account_id  → users (cascade)
  age_range       band, not a birth date    profile_id  → profiles (cascade)
  country_region  ISO 3166-1 alpha-2        role        self | setup_helper
  pronouns        optional                  unique (account_id, profile_id)
  avatar_url      reserved; no upload UI
  created_at, updated_at

user_settings                         devices  (a robot that has reached the backend)
  id          uuid, pk                  id                     uuid, pk
  user_id     unique → users            hardware_id            unique, indexed
  theme       system|light|dark         claimed_by_account_id  → users (cascade), nullable
  language                              owner_profile_id       → profiles (set null)
  larger_text                           display_name           a label, never identity
  high_contrast                         device_type            firmware_version
  reduce_motion                         provisioning_status    unclaimed | claimed
  voice_first_preference                bootstrap_secret_hash  ┐ sha-256 only;
  simplified_interface                  device_token_hash      ┘ never reversible
  created_at, updated_at                claimed_at, last_seen_at
                                        setup_completed_at
                                        introduction_requested_at, introduced_at
                                        created_at, updated_at

provisioning_sessions  (one robot may join one account, briefly)
  id          uuid, pk        token_hash   sha-256, unique
  account_id  → users         expires_at   10 minutes
  profile_id  → profiles      consumed_at  set by the claim that used it
  hardware_id indexed         device_id    → devices (set null)
  created_at, updated_at
```

`connection_status` is deliberately **not** a column: it is derived from
`last_seen_at` on every read, so it cannot go stale. Credentials are stored
only as hashes, so a leak of this table reveals no secret. The prototype's
trust model for `bootstrap_secret_hash` — trust on first claim, rather than a
credential written at manufacture — is spelled out in the protocol document.

Value sets (`theme`, `setup_mode`, `onboarding_status`, `age_range`, `role`) are
enforced by database CHECK constraints, not only in application code, and are
generated from the same tuples the API schemas validate against — so the two
cannot drift. Every child table cascades on account deletion.

An age *band* is stored rather than a date of birth: it is enough for
age-appropriate behaviour without holding a precise identifier. `profiles`
contains no medical information of any kind, and a test asserts that.

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
