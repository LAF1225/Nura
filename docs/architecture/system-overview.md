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
| Today          | Greeting, daily wellbeing check-in, Important Today, configurable cards, robot status — none of it needs a robot |
| Check-ins      | One per person per local day, editable, queued on the device when offline |
| Dashboard      | Cards resolved from a server registry; show, hide and reorder from Customize Today |
| Health record  | Conditions, medications, allergies, doctors, procedures, notes and blood type — full CRUD, owned by a profile |
| Health setup   | Gradual, resumable, skippable; an equal-weight completeness figure that blocks nothing |
| Database       | `users`, `user_settings`, `profiles`, `account_profile_roles`, `devices`, `provisioning_sessions`, `daily_checkins`, `dashboard_preferences`, `medical_conditions`, `medications`, `allergies`, `clinicians`, `procedures`, `medical_notes` |
| Endpoints      | `/health`, `/api/v1/version`, `/api/v1/me`, `/api/v1/onboarding`, `/api/v1/profiles`, `/api/v1/devices`, `/api/v1/today`, `/api/v1/daily-checkins`, `/api/v1/dashboard-preferences`, and the health record under `/api/v1/profiles/{id}/…` |

Deliberately absent: medication *scheduling* and reminders, symptom logging,
appointments, AI or chat, caregiver permissions, emergency detection, push
notifications, HealthKit and Health Connect. The daily check-in is a wellbeing
prompt with three answers and an optional note -- it is not symptom tracking.
The health record stores medications but attaches no schedule to them, and
nothing in the system interprets any of it.

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
│   ├── customize-today.tsx   More → Customize Today
│   ├── health/               The health record: setup, sections, forms
│   └── +not-found.tsx
└── src/
    ├── components/           Screen, Card, Button, AppText, List, …
    │   └── today/            Today cards and the card registry
    ├── features/health/      Section specs, form logic, API, hooks, drafts
    ├── constants/            Runtime config; the only reader of process.env
    ├── hooks/                useToday, useDevices, network status, …
    ├── navigation/           Tab definitions (single source of tab order)
    ├── services/
    │   ├── api/              client, typed errors, endpoint functions
    │   ├── auth/             AuthService surface
    │   ├── checkins/         The offline check-in queue
    │   ├── dashboard/        Card layout rules (pure functions)
    │   ├── provisioning/     BLE transport, SPAKE2, provisioning flow
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
  the theme, and one draft: a check-in the phone has not managed to send.
- **Rules live on the server.** The app decides what to show, never what is
  allowed. Which profile a record belongs to, whether a card may be enabled,
  whether a robot is online and which edit wins are all settled by the
  backend.

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
│   ├── models/               User, Profile, Device, DailyCheckIn, health, …
│   ├── schemas/              Pydantic request/response models
│   ├── services/             The rules: onboarding, devices, check-ins, cards
│   └── main.py
├── alembic/                  Migrations
├── scripts/                  Development fixtures (never for production)
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

The health record -- six tables, all owned by a profile and all cascading
with it -- is described in [health-data.md](health-data.md) rather than
repeated here.

```text
medical_conditions   medications   allergies
clinicians           procedures    medical_notes
```

```text
daily_checkins  (how one person said they were   dashboard_preferences
                 feeling on one day)               id          uuid, pk
  id              uuid, pk                         profile_id  → profiles (cascade)
  profile_id      → profiles (cascade)             card_key    no CHECK: see below
  checkin_date    a plain date, the user's own     visible     bool
  wellbeing_level good | okay | not_great          position    int, ascending
  note            optional, ≤ 280 chars            unique (profile_id, card_key)
  unique (profile_id, checkin_date)                created_at, updated_at
  created_at, updated_at
```

`profiles` also gained `blood_type` and the two columns that remember where
someone got to in health setup -- each a single answer about the person rather
than a list they keep. They are medical data all the same: only the health
routes return them, and `/me` does not.

A check-in belongs to a **profile**, not to the account that submitted it: in
assisted setup those differ, and it is the person Nura is for whose day is
being described. `checkin_date` is a plain date rather than a timestamp,
because it is the day as the user experienced it — someone checking in at 11pm
in Karachi means that day, not the following one in UTC. The unique constraint
is the whole design of the edit flow: changing an answer updates that row, and
a submission arriving late from the offline queue cannot create a second one.

`dashboard_preferences.card_key` deliberately has **no** CHECK constraint. The
set of cards grows with every feature PRD, and a constraint would mean a
migration each time; the API validates against the card registry in
`app/services/dashboard.py` instead, which is the thing that actually knows
whether a card exists. A card the user has never touched has no row and falls
back to the registry defaults, so a card added later appears for everyone
without a data migration.

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

## The Today screen

Today is assembled by the server and rendered as a list of cards looked up by
key. Two consequences, both deliberate:

**One request fills the screen.** `/api/v1/today` returns the profile, the
check-in state, the robot and the card layout together. As feature areas land
they extend that response rather than adding requests — the alternative is an
app that opens with six spinners and fills in piece by piece.

**Adding a card does not mean editing the screen.** A card is declared in the
server registry, given a key in `DashboardCardKey`, and given one entry in the
client's renderer map. A key the client has no renderer for is skipped, and a
card whose feature does not exist yet is never shown and cannot be enabled —
which is how `medications` and `appointments` reserve their keys now without
anyone seeing an empty medication card.

Important Today is the one part of Today the user cannot switch off. It is
empty in PRD 3, but it will carry medication and appointment reminders, and a
reminder someone hid months ago is a reminder that failed.

### Refresh policy

Today refreshes when the screen is focused and the data has gone stale (30
seconds), and on pull-to-refresh. It never polls. The robot's status is the
only thing on the screen that changes without the user doing something, and
the backend already treats a robot as online for 90 seconds after a heartbeat,
so a timer would spend battery to tell the user something they can see the
moment they look.

### Today with no signal

The last successful `/api/v1/today` body is kept on the device. If the backend
cannot be reached, Today renders from it rather than showing an error where the
screen used to be: the user still sees their check-in and their card layout,
marked as saved rather than live.

Two limits keep that honest. The saved day is only used **for the day it was
fetched on** — yesterday’s check-in presented as today’s would be a lie. And
the robot’s connection is *not* carried over: offline we genuinely do not know
it, so the card says "Status unavailable" instead of repeating a value that may
be hours old. Presence only ever comes from the backend.

### A check-in made with no signal

```text
user answers ──▶ PUT /daily-checkins/today ──▶ stored, card shows it
                        │ transport failure
                        ▼
                 saved on the device, card says so
                        │ connection returns, or Today regains focus
                        ▼
                 PUT again, carrying client_updated_at
                        │
                        ├─ server had no newer edit  ─▶ applied, queue cleared
                        ├─ server had a newer edit   ─▶ server's answer returned,
                        │                               client adopts it, queue cleared
                        └─ server refused it outright ─▶ dropped, not retried forever
```

The queue holds at most one entry, because there is at most one check-in per
day and only today's can be edited. It is deliberately not a general offline
synchronisation engine. Conflicts are settled by **the latest explicit user
edit**: `client_updated_at` is when the user chose the answer, not when the
request arrived, so an answer that sat in the queue for hours cannot overwrite
a newer one made since.

The queued entry lives in AsyncStorage, in the app's private data directory —
not secure storage, which is for credentials. A note is written there and to
the database, and nowhere else: never to a log, never to analytics.

### Analytics

No analytics SDK is configured, and none is added here. When one is, these are
the events Today should emit, and they carry no content:

```text
today_opened              daily_checkin_submitted   daily_checkin_changed
today_card_hidden         today_card_reordered      connect_nura_selected
```

A check-in *level* may be counted. A note, a preferred name, a device
credential or an auth token may never be sent anywhere.

## The health record

Six record types, one shape. Everything belongs to a **profile** rather than
to the account that typed it in, because in assisted setup those are different
people and getting it wrong once would be hard to unpick.

Three decisions run through it, and each is there to stop the system saying
something the user did not:

**Dates keep their precision.** An approximate date is two columns -- an exact
date and a year -- with a constraint that at most one is set. "Diagnosed in
2015" stays a year, and "I don't remember" stays nothing at all.

**Provenance is the server's to set.** `source` says where a record came from.
A client cannot supply it, so nothing can claim to have come from a clinician
import when a person typed it in.

**Nothing is interpreted.** Severity is what the user chose, not what the
reaction text suggests. "Currently taking" is a flag they set, not something
derived from an end date. No condition is suggested from typed text, no
interaction is computed, and no record change notifies anybody.

The authorization rule, the privacy rules and what later PRDs will need are in
[health-data.md](health-data.md).

### One screen for six record types

The app describes each section once -- its fields, its wording, how to
summarise a record -- and the list and form screens read that description.
Six near-identical CRUD screens written by hand would be six chances for a
delete confirmation, an empty state or a required-field message to drift
apart, on the part of the app that holds someone's medical history.

The backend does the opposite and writes its routes out per resource. That is
deliberate too: it is the authorization surface for medical records, and being
able to read each resource's four routes in full is worth more there than
brevity.

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

The health record is where this is most concrete. Nura stores what people tell
it and says so on the screens that show it: nothing is described as confirmed,
verified or checked. It does not infer a severity from a reaction, suggest a
condition from typed text, compute an interaction, or tell anyone to start,
stop or change a medication. PRD 4 stores and displays; it does not advise.

The daily check-in is the other place this bites. A `not_great` answer is
acknowledged -- "Thanks for checking in." -- and nothing more. It does not
suggest a cause, does not recommend an action, does not raise an alert, and
does not notify anybody. A test asserts the wording carries no such language.
Worsening-symptom logic belongs to a later PRD that has the clinical care to
present it responsibly.

Health and safety logic stays separable from general assistant functionality,
so the companion features can evolve without touching the safety path. The
escalation design is written up in
[safety-and-emergency.md](safety-and-emergency.md) and is documented only —
none of it is implemented.
