# System overview

Status: PRD 8 — Nura AI, voice, personality and memory.

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
| Caregivers     | Invitations, eight permission categories, suggestions a person approves, family messages, an emergency-contact chain nothing walks — none of it needs a robot |
| Dashboard      | Cards resolved from a server registry; show, hide and reorder from Customize Today |
| Health record  | Conditions, medications, allergies, doctors, procedures, notes and blood type — full CRUD, owned by a profile |
| Health setup   | Gradual, resumable, skippable; an equal-weight completeness figure that blocks nothing |
| Medications    | Schedules with their own time zone, generated doses, Taken / Snooze / Skip, missed-dose transition, history and adherence |
| Refills        | Opt-in supply counts, decremented only by Taken, with a threshold the user chooses |
| Reminders      | OS-scheduled local notifications, rebuilt from the server's doses; queued actions when offline |
| Symptoms       | Episodes and entries, a manual form and a deterministic guided conversation over one shared draft, severity and change tracking, history, resolution and recurrence |
| Symptom photos | Optional, private, served only through an authenticated route; never analysed |
| Safety-netting | One reviewed non-diagnostic sentence, shown only on a change the user recorded; the urgent rules are built, tested and disabled |
| Appointments   | Manual entry with its own time zone, three history lists, optional clinician link, cancel / complete / reopen, two local reminders |
| Questions      | The user's own words, in their own order, with deterministic neutral prompts they may accept |
| Doctor reports | A frozen one-page summary built from what the user ticked, an optional appendix, versioned, exported as a PDF through the share sheet |
| Database       | `users`, `user_settings`, `profiles`, `account_profile_roles`, `devices`, `provisioning_sessions`, `daily_checkins`, `dashboard_preferences`, `medical_conditions`, `medications`, `allergies`, `clinicians`, `procedures`, `medical_notes`, `medication_schedules`, `medication_schedule_times`, `medication_doses`, `medication_supply`, `symptom_episodes`, `symptom_entries`, `symptom_photos`, `appointments`, `appointment_questions`, `appointment_reports` |
| Endpoints      | `/health`, `/api/v1/version`, `/api/v1/me`, `/api/v1/onboarding`, `/api/v1/profiles`, `/api/v1/devices`, `/api/v1/today`, `/api/v1/daily-checkins`, `/api/v1/dashboard-preferences`, the health record, the medication, symptom and appointment routes under `/api/v1/profiles/{id}/…`, and `/api/v1/device-actions/…` for the robot |

Deliberately absent: AI or chat, caregiver permissions, emergency detection,
push notifications, calendar sync, a clinician portal, HealthKit and Health
Connect. The daily check-in is a wellbeing prompt with three answers and an
optional note -- it is not symptom tracking, and the symptom system is separate
from it. Medication reminders record what somebody did and interpret none of it:
no interaction checking, no dose advice, and nothing inferred from a skip reason.
Symptom records are the same: no diagnosis, no likelihood, no cause attributed to
a medication, and no analysis of a photograph. A doctor report restates what was
recorded and adds nothing: no impression, no probable cause, no treatment.

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
│   ├── medications/          Schedules, doses, history, supply, skip sheet
│   ├── symptoms/             Overview, log, Talk to Nura, review, history, detail
│   ├── appointments/         List, form, detail, prepare, questions, select,
│   │                         preview, report versions
│   └── +not-found.tsx
└── src/
    ├── components/           Screen, Card, Button, AppText, List, …
    │   └── today/            Today cards and the card registry
    ├── features/health/      Section specs, form logic, API, hooks, drafts
    ├── features/medications/ Schedule rules, dose wording, reminders, queue
    ├── features/symptoms/    Shared draft, conversation engine, photos, queue
    ├── features/appointments/ Form draft, report selection, reminders, export
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

Feature folders (`caregivers/`, `safety/`, …) are created when the PRD that needs
them arrives, not in advance.

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
│   │   ├── medications/      Schedules, doses, supply, adherence, summary
│   │   ├── symptoms/         Episodes, entries, photos, safety, summary
│   │   ├── appointments/     Visits, questions, periods, preparation,
│   │   │                     snapshot, PDF, report versions
│   │   └── storage.py        Private object storage: photos and report PDFs
│   └── main.py
├── alembic/                  Migrations
├── scripts/                  Development fixtures, plus the medication
│                             maintenance job (the only one for production)
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
repeated here. PRD 13's one table, ``data_exports``, is in
[privacy-security-reliability.md](privacy-security-reliability.md). So are the four feature areas built on top of it: medications in
[medication-system.md](medication-system.md), symptoms in
[symptom-system.md](symptom-system.md), and appointments and reports in
[appointment-and-report-system.md](appointment-and-report-system.md). PRD 12's
eight daily-life tables are in
[daily-life-assistant.md](daily-life-assistant.md), and nothing in them is
medical -- they belong to a profile the same way, and cascade the same way.

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
which is how `routines` and `hydration` reserve their keys now without anyone
seeing an empty card.

Two of the real cards draw *nothing at all* until they are relevant: medications
for somebody with no schedules, symptoms for somebody who has never logged one.
Appointments is deliberately different -- it draws "No upcoming appointments" and
a way to add one, because checking when the next visit is, or noting one down, is
a reason people open the app (PRD 7, section 9).

Important Today is the one part of Today the user cannot switch off. It carries
doses that are overdue, due or next up; an appointment today or tomorrow; and a
symptom the user recorded as worsening -- in that order, by how soon each needs
something. A reminder someone hid months ago is a reminder that failed.

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

## The medication system

PRD 5 turns a medication *record* into reminders. They are three different
things in three different tables, and keeping them apart is what stops a
record from quietly becoming an instruction:

```text
medications          what it is             (PRD 4, untouched)
    ├── medication_schedules        when to remind, and in which time zone
    │       └── medication_schedule_times
    ├── medication_doses            one moment, and what happened at it
    └── medication_supply           how many are left
```

**A reminder is a wall-clock time, not an instant.** The schedule carries an
IANA zone, and generation resolves local-date-plus-local-time in that zone
into a UTC instant, so 8am stays 8am across a daylight-saving change. The two
awkward days a year are decided rather than left to chance: a time that does
not exist produces one dose, and a time that happens twice produces one dose.

**Doses are rows, generated 14 days ahead**, so "what is due today", "what did
I miss" and the phone's notification schedule all read the same thing. Every
read of Today, the dose list and adherence replenishes first, which is why
PRD 5 needs no background worker to be correct; a cron-friendly script does
the same for people who have not opened the app.

**An action sets a state on one row** — Taken, Snooze and Skip never append an
event beside it. That is what makes a retried request harmless, what stops a
robot's confirmation from becoming a second entry in somebody's history, and
what lets an offline queue hold one final answer per dose.

**Editing the future never edits the past.** A schedule change rebuilds doses
from now forward and cannot reach one that has been recorded. Deleting a
schedule clears the link on its doses rather than cascading.

Adherence is one figure with its denominator written down —
`taken / (taken + skipped + missed)` — and it is never called adequate or
inadequate. Supply is the user's own count, decremented only by Taken, and
described as approximate because it is.

The whole model, including the status transitions, the offline conflict rule
and the robot action contract, is in
[the medication system](medication-system.md).

## The symptom system

PRD 6 records what somebody is *experiencing*, which is a different thing from
what a clinician has told them they have — and the two are kept in different
tables, in both directions (PRD 6, section 6):

```text
medical_conditions       what you have been told you have   (PRD 4, untouched)

symptom_episodes         one bout of one symptom
    +-- symptom_entries      one observation about it, at one moment
            +-- symptom_photos   metadata for a privately stored image
```

**An episode is a bout, not a name.** A headache in March and a headache in
October are two episodes, the second linked to the first and carrying the status
`recurring`. Each keeps its own onset and resolution, so nothing unrelated is
merged and "how many times has this happened?" has an answer
(PRD 6, section 38).

**Two entry flows, one record.** The manual form and the in-app guided
conversation fill the same draft, end on the same review screen and save through
the same endpoint. The only difference is the `source` recorded. The conversation
is deterministic — a vocabulary and a rule set, no model — and its hardest
requirement is that it never asks again for something volunteered
(PRD 6, sections 4, 27 and 28).

**Uncertainty is preserved.** "No nausea" and "I might have felt dizzy" are stored
as denied and uncertain rather than flattened, and the safety rules subtract both
before anything can fire (PRD 6, sections 24 and 46).

**Nothing is interpreted.** No diagnosis, no likelihood, no cause, and no analysis
of a photo. The one thing Nura says back is a reviewed sentence, shown when the
*user* recorded a change, and the urgent-care rules are built, tested and switched
off until a clinician has reviewed them (PRD 6, sections 32, 42, 44 and 81).

Symptom photos are the first thing Nura stores that is not a database row. They go
to private object storage and are served only by a route that re-checks the whole
ownership chain for every byte — there is no public URL and no signed one
(PRD 6, section 63).

The whole model, including the conversation engine, the offline queue and the
safety boundary, is in [the symptom system](symptom-system.md).

## The appointment and report system

PRD 7 is where the record points outward: appointments, the questions to ask at
them, and a one-page summary somebody hands a clinician.

```text
appointments                  a visit, entered by hand
    +-- appointment_questions     what the person wants to ask
    +-- appointment_reports       a frozen summary, and the PDF made from it
```

**A report is a snapshot, not a query.** The finished text is stored on the row
when it is generated, so a symptom entry corrected next week cannot change what a
document handed over last week says, and re-rendering an old version produces the
same file byte for byte (PRD 7, sections 30 and 72).

**One file writes prose.** `services/appointments/snapshot.py` is the only module
that turns a value into a sentence, which is what lets a test read *every* string
a report can contain and fail on a diagnosis, a likelihood, an attributed cause or
a graded adherence figure (sections 3, 18, 20 and 45).

**The user decides what is in it.** Symptoms are ticked one at a time -- there is
no single symptoms switch, because section 15 forbids Nura deciding which matters
more -- and a section that was not ticked is absent rather than empty.

**Regeneration adds a version and overwrites nothing** (section 31), and a
report's PDF is stored and served exactly like a symptom photo: private storage, a
server-built key, no URL in any response, and the whole ownership chain re-checked
for every byte (sections 35 and 52).

**Manual entry only.** No calendar sync, and no column that implies one
(section 4). Appointment times carry their own IANA zone, and the display strings
are rendered by the server because that is where the time-zone database is
(section 42).

The whole design, including the report period rules, the offline behaviour and
the export path, is in
[appointment-and-report-system.md](appointment-and-report-system.md).

## The Nura assistant

PRD 8 is where Nura starts answering. A conversation in the app, backed by a
model the app never talks to directly.

```text
app ──▶ /profiles/{id}/assistant/…  ──▶  NuraAssistantService
                                              │
              policy ─ prompts ─ context ─ tools ─ provider ─▶ the model
```

**The model is behind one method.** `AIModelProvider.complete()` is the whole
boundary, and `anthropic_provider.py` is the only file in the backend that
imports a provider SDK. Swapping provider means writing a sibling of it and
changing `AI_PROVIDER` (PRD 8, section 10).

**The guarantees are structural, not prompted.** Of ten tools, nine read and
one *proposes* adding a question for the user to confirm. There is no tool that
edits a dose, deletes a record or reaches another profile -- and no tool takes a
profile id at all, so the model has nowhere to put one (sections 15 and 90).

**What is deterministic does not depend on the model.** "Nura, emergency"
short-circuits to a fixed notice with no provider call; serious mode is decided
from the user's words; and the section 73 sentences are *placed* around a reply
rather than requested of the model. All of it behaves the same whichever
provider is configured, which is what makes the guardrail tests mean something
(section 74).

**Almost nothing about the record reaches the prompt.** The context block is a
date and three counts. Names, conditions, notes and appointment titles are read
through tools, when a question needs them (sections 12 and 51).

**Memory is a preference, not a record.** A short list of how somebody likes to
be spoken to, always agreed to before it is saved, with no category for anything
clinical and no foreign key into the health record (sections 40, 45 and 46).

**Nothing here needs the robot**, and `conversation_messages.source` is how the
robot becomes another input to the same service rather than a parallel one
(sections 4 and 70).

**PRD 9 gave every tool a permission.** `ToolContext` carries the granted
categories and both `specs` and `run` filter on them, so a caregiver-scoped
assistant is not shown a tool it lacks the category for and is refused if it asks
anyway (PRD 9, section 63). Three tools are owner-only: the two that span
categories a caregiver is granted separately, and the one that writes -- PRD 9
section 64 reserves a caregiver's changes for a suggestion a person approves.
There is no caregiver chat endpoint yet; the layer section 63 names is built and
tested, the surface that would use it is not.

The build is in [nura-assistant.md](nura-assistant.md); what Nura will and will
not say, and what is *not* enforced, is in
[assistant-safety.md](assistant-safety.md).

## Caregivers and family communication

PRD 9 is the first time somebody other than the account holder can see part of a
person's record. One decision shapes everything else about it.

**A caregiver is a second authorization path, not a third role.**

```text
account ──┬── account_profile_roles ──▶ profile     the owner path (PRD 0-8)
          │      self / setup_helper                 deps.get_owned_profile
          │
          └── caregiver_relationships ─▶ profile     the caregiver path (PRD 9)
                 + caregiver_permissions             deps.get_care_scope
```

`account_profile_roles` is what every profile-scoped route from PRD 0-8
authorizes through. Putting caregivers in it would have granted the complete
health record, every symptom photo and every doctor report **without changing a
single route**. So caregivers reach a separate, narrower surface, and a test
walks eight PRD 0-8 endpoints with every category granted and expects 404 from
each.

**A role grants nothing.** Eight permission categories, one row each, default
deny; `role` is a label that no code in the authorization path reads
(sections 10 and 54).

**A caregiver proposes; a person applies.** There is no caregiver route that
writes to a medication schedule or an appointment. The five changes they may
propose are the whole vocabulary -- `change_medication_dose` is not refused, it
does not exist (section 85) -- and approval re-checks the permission against the
*current* relationship before calling the ordinary service.

**A missing permission is indistinguishable from nothing recorded.** The
caregiver home omits a section that was not granted rather than returning it
empty, and the answer to both "not your profile" and "not your category" is 404
(section 18).

**Two things are named and not finished, each said out loud.** Audio calling
has a real interface and an implementation that refuses, because section 38
forbids simulating a call. Photo messages are reserved in the vocabulary and
cannot be sent. The third -- "nothing contacts an emergency contact" -- stopped
being true in PRD 10, which walks the chain PRD 9 built and orders.

The build is in [caregiver-and-family.md](caregiver-and-family.md); the
reasoning is in
[0012-caregiver-access-and-approval.md](../decisions/0012-caregiver-access-and-approval.md).

## Safety monitoring and SOS

PRD 10 is the first thing in this system that could matter to somebody who is
not holding their phone. Which means the governing constraint is not
completeness but honesty: **nothing may claim more than happened.**

```text
Start monitoring            explicit, time-boxed, server decides when it ends
    │
    ├── possible_* trigger (device token, monitoring on)
    │        └── check-in ──┬── "I'm okay"   ──▶ resolved, nobody contacted
    │                       ├── "I need help"──▶ escalate now
    │                       └── no answer    ──▶ [second prompt] ──▶ escalate
    │
    └── manual SOS / "Nura, emergency"  (works with monitoring off)
             └── escalate now

escalate = caregivers with `safety_alerts` get an in-app alert record,
           then the PRD 9 contact chain in priority order,
           then an outcome: complete / partial / failed /
           no_contacts / providers_not_configured
```

**Describe, never diagnose.** Every sensor-observed event type begins with
`possible_`; there is no confidence column on an event; one module writes all
safety prose and a test reads every string in it for the words section 52
forbids.

**Nura does not watch unless asked.** A passive trigger with no active session
is refused with `monitoring_not_active`. A caregiver cannot start monitoring --
not from a route, and not through the assistant.

**Every deadline is a column, not a timer.** `response_deadline_at` is a
timestamp, the worker's query is a comparison, and an app that was force-quit
mid-countdown changes nothing. That splits two claims section 80 wants kept
apart: *state correctness*, which every read provides, and *timely
escalation*, which needs `scripts/safety_maintenance.py` -- a script no
deployment here schedules, and whose absence is documented rather than papered
over.

**Nothing claims a delivery.** The only channel that works is an in-app alert
record, recorded as `attempted` and never `delivered`; `delivered` exists in
the vocabulary and no code path writes it. Push, SMS and calling report
`not_configured` with stable codes, and the capability endpoint says so in
words -- because hiding a control is not the same as saying it does not exist.

**No detector exists and none is validated.** `DETECTORS` is empty, which is
what makes `robot_detection: not_connected` derived rather than hard-coded.

The build is in [safety-monitoring.md](safety-monitoring.md); the reasoning is
in
[0013-safety-monitoring-and-escalation.md](../decisions/0013-safety-monitoring-and-escalation.md).

## The robot's display and companion experience

PRD 11 built the whole software layer that drives the robot's screen, and the
robot still does not exist. That is the shape of the stage rather than a gap in
it: nothing in the app or the backend depends on the robot, so the layer can be
complete and the hardware can arrive later and connect to it.

```text
       what is true now                           what the robot shows
  ┌───────────────────────┐                  ┌─────────────────────────┐
  │ PRD 5  a dose is due  │   presenter      │  one card at a time,    │
  │ PRD 7  a visit soon   │  ──refresh──▶    │  or the companion face  │
  │ PRD 9  unread message │                  │                         │
  │ PRD 10 live safety    │                  └─────────────────────────┘
  │ PRD 8  the chosen mode│                      device_presentations
  └───────────────────────┘

  robot: heartbeat ──▶ presentation_pending ──▶ GET next ──▶ render ──▶ ack
```

**Reconciliation, not notification.** No service in PRD 0-10 was modified to
call into the robot. `presenter.refresh` reads what is currently true and makes
the queue match, which is what makes the robot additive (no workflow can fail
because of it), makes a stale card impossible (there is no event that could
have been missed), and makes reconnecting unremarkable (a robot that comes back
gets what is true now, with no replay).

The one exception is the assistant, because a reply is an utterance rather than
a state. It goes through a two-function module that finds the profile's robots,
does nothing when there are none, and cannot raise.

**A presentation is a request, not a render.** `sent` means the backend handed
the envelope over; `displayed` means a device said it drew it. One function
writes `displayed_at` and a CHECK constraint means there cannot be another, so
the distinction survives into every screen and every log.

**A capability is what the device proved, not what it compiled.** Twelve keys
rather than one `robot_ready` boolean, and four states where `not_verified`
means "the driver is there and nothing physical has been shown to work". Only a
device can report that state: the backend has never seen a build, so it says
`not_connected` instead of guessing.

**The screen is in a room other people walk through**, which is why a
medication reminder defaults to "Medication / Reminder due" and the redaction
happens when the card is built rather than when it is drawn.

**Serious moments have no face.** A safety prompt, an emergency and a serious
reply are information, and the mode-to-face table maps them to nothing — so
section 28's rule that expression must never carry a health judgement is
structural rather than remembered.

Nothing has ever been drawn on a panel, nothing has ever been played, and no
physical robot has acknowledged anything. The build is in
[robot-companion-experience.md](robot-companion-experience.md), the wire
contract in
[the presentation protocol](../device/presentation-protocol.md), and the
reasoning in
[0014-robot-presentation-architecture.md](../decisions/0014-robot-presentation-architecture.md).


## Daily life: tasks, reminders, alarms and routines

PRD 12 is the stage where Nura stops being only a health product. Eight tables,
and the division is a boundary rather than a tidy-up: a task has no occurrence
rows and may have no time at all, a reminder generates concrete occurrences, an
alarm generates nothing because nobody asks about last Tuesday's seven o'clock,
and a routine generates runs with step completions against them.

Three things are worth knowing here; the rest is in
[daily-life-assistant.md](daily-life-assistant.md).

**The recurrence engine is PRD 5's, called rather than copied.** A reminder, an
alarm and a routine resolve a wall-clock time through
`services.medications.doses.occurrence_instant`, so the two daylight-saving
days a year behave identically across all four features and there is no second
policy to disagree with.

**A task carries two timestamps.** `content_updated_at` and
`status_changed_at`, because a completion must not be undone by an unrelated
title edit arriving from another device -- and a content edit cannot reach the
status at all, since `TaskUpdate` has no status field.

**The three external capabilities are `not_configured`, derived.** Weather,
news and an external calendar ask whether a provider is both named and
implemented; none is. A deployment that sets a provider name nothing implements
gets a warning and `not_configured`, not a feature that sometimes answers.

Nothing in the daily-life services knows the robot exists, and nothing in
PRD 0-11 changed shape to accommodate this stage -- the one exception is the
`routines` caregiver permission, which gained the data it was reserved for.

**What is not true:** the app has never been run on a physical phone, so no
notification and no alarm has ever fired.

## Privacy, security and reliability

PRD 13 is the stage that added almost no behaviour and found three things that
were already wrong. It is worth reading that way round, because the hub, the
export and the deletion path are the easy half.

**A profile switch left the previous person's data in the cache.** The list of
query-key prefixes cleared on a switch had stopped being maintained:
twenty-six keys were missing or wrong, from PRD 3, 5, 6, 7, 10 and 12 -- the
health record, dose history, adherence, symptom entries, appointment questions,
doctor reports, check-ins, safety status, tasks, routines. Two entries that were
present matched nothing, because the real keys are ``['health', 'summary', ...]``
and a prefix compares element by element.

**Signing out cleared the cache and nothing on disk.** Seventeen storage keys
and seven persisted stores survived it, so a second person signing in on the
same phone inherited the previous one's drafts, Today cache and offline queues.

**There was no deletion path at all**, and a naive one would have orphaned
every private file: 68 foreign keys cascade from a profile and none can reach
object storage.

Neither of the first two was found by reading the lists. Both were found by
tests that read the *source* -- every ``queryKey`` literal, every ``'nura...'``
storage key -- and require each one to be classified, in both directions. The
reverse direction is what caught the key that matched nothing.

Three things PRD 13 added:

**One security suite that enumerates routes from the application.** Every stage
from PRD 9 onwards wrote a denial test against a hand-typed list of paths; none
covered the next stage's routes. ``test_security_matrix.py`` walks the router
tree, classifies each route by which authorization dependency it reaches, and
requires 404 from every one of the 169 owner routes for a second owner and for
a caregiver holding every permission. A route PRD 14 adds is covered the day it
is written.

**An export whose contents are a declared list rather than a strip-list.**
``services/privacy/tables.py`` states for every table which columns are
exported and which are excluded and why, and a test compares that against the
live metadata: a column a later PRD adds is unclassified, and unclassified
fails.

**A deletion service that owns the files.** Keys are read before the rows go,
because afterwards there is no way to find them, and the files are deleted
after the transaction commits, because a file removed for a transaction that
rolled back cannot be undone.

Full detail in
[privacy-security-reliability.md](privacy-security-reliability.md); the data
classification and retention in [data-retention.md](data-retention.md).

**What is not true:** no penetration test and no compliance certification. The
security suite is evidence about the boundaries this code enforces, and nothing
more.

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

PRD 11 adds the robot's own view of the same idea rather than a second
framework (section 4). Four of its ten modes are this setting seen from the
robot's side — `normal` becomes `companion` — and the other six are facts about
the moment, derived on every read: `information` when a card is queued,
`safety` and `emergency` from PRD 10's live state, `offline` from heartbeats,
`setup` before setup is finished, and `error`, which only the robot ever says.

PRD 8 implements the first four for the assistant, stored on
`assistant_preferences.mode`: Focus shortens replies and raises nothing
unasked, Sleep quietens Nura without touching a reminder, and Privacy stops
memory suggestions, keeps the record out of the prompt and says so on screen
(sections 66-68).

`safety` and `emergency` are deliberately **not** stored values. A mode the app
can select but nothing acts on would be a promise Nura cannot keep, so they
wait for the PRD that gives them behaviour.

Serious mode is not in this list either. It is derived per message from what
was said and recorded on the message, because seriousness is a property of a
moment rather than of a person -- and a user who could switch it on could
switch it off (section 69).

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

**Medication reminders are where PRD 5 had to hold the same line while
handling something people genuinely want an answer about.** Nura records and
reminds; it does not recommend changing a dose, doubling after a missed one,
stopping anything, or deciding whether a late dose should still be taken. It
infers nothing from a skip reason and checks no interactions. A dose nobody
recorded reads "Wasn't marked as taken" -- the fact, not a reprimand -- and
the adherence figure is never called adequate or inadequate.

The one sentence in the product that approaches advice points at a person:

> If you're unsure what to do after missing a dose, follow the instructions
> from your clinician or pharmacist.

It is defined once and asserted by a test, as is the absence of guilt wording
around a missed dose.

**Symptoms are where PRD 6 had to hold the line hardest**, because describing a
symptom is the closest a person comes to asking what is wrong with them. Nura
records the description and never interprets it: no condition is named, no
likelihood is given, no cause is attributed — not even to a medication somebody
took just before feeling unwell (PRD 6, sections 81 and 82). No photograph is
analysed (section 32).

The one thing it says back is a reviewed sentence, shown only when the *user*
recorded a change they chose:

> You have recorded this as worsening. If it keeps getting worse, becomes severe,
> or is affecting what you can normally do, consider contacting a healthcare
> professional.

Severity alone never triggers it, whatever the number (section 78), and a phrase
somebody hedged or denied never triggers anything at all (sections 24 and 46). The
urgent-care rules PRD 6 section 44 describes are written down, tested and
**switched off**, because no clinician has reviewed them; enabling them is a
clinical decision rather than a deployment one. Every sentence Nura can say about a
symptom lives in one module so it can be reviewed without touching symptom code,
and a test reads all of them and fails on a named condition, a likelihood or an
attribution of cause.

Nothing in the symptom system acts on its own: no emergency service is called, no
caregiver is messaged, no monitoring is activated and no medication is changed
(section 43).

**PRD 8 is where the boundary stopped being only a matter of which sentences
were written**, because the sentences are generated. Three layers hold it:
capabilities that do not exist (no tool edits a dose or reaches another
profile), deterministic policy that runs on the user's own words whichever
model is configured, and the boundary stated in the prompt. Those are not
equally strong, and
[assistant-safety.md](assistant-safety.md) has a section headed **What is not
enforced** that says which is which -- including that nothing scrubs a model's
output, because a filter that half works is worse than one that is honestly
absent.

**The doctor report is where PRD 7 had to hold it in writing**, because a
report leaves the app. Everything in one restates what was recorded: counts, the
user's own change answers, their own words in quotation marks. No impression, no
probable cause, no treatment, no "this is consistent with" (section 45). The
adherence line is counts with the denominator beside them and is never called
good or bad (section 18); the wellbeing line is three counts and nothing read into
them (section 20); and a symptom the person hedged or denied appears as hedged or
denied (section 47).

Every sentence a report can contain is written in one module and frozen into the
stored snapshot, so a test reads all of it -- including the appendix -- and fails on
any of the above. Every page carries the same line:

> This is a summary of information recorded in the Nura app. It is not a
> diagnosis, an assessment or medical advice.

And the question prompts are held to the same rule. "Would you like to ask about
your worsening headaches?" restates the user's own answer; nothing offers a
hypothesis about why, because that would be a clinical opinion in the shape of a
helpful question (sections 3 and 24).

The daily check-in is the fifth place this bites. A `not_great` answer is
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
