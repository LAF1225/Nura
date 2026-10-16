# Nura — implementation

How Nura is built, what exists today, and what is genuinely proven to work.

- **Date:** 13 October 2026
- **Stage:** PRD 13 — Privacy, security and offline reliability
- **Branch:** `prd-2-pairing` (not merged into `main`)

| Commit | Stage |
| ------ | ----- |
| `c11b25b` | PRD 0 — project foundation and architecture |
| `1d653f1` | PRD 1 — account creation, authentication, onboarding |
| `aae4243` | PRD 2 checkpoint (work in progress) |
| `f7417b4` | PRD 2 — robot pairing, BLE discovery, Wi-Fi provisioning |
| `1e74912` | PRD 3 — Today, daily check-in, dashboard cards |
| `db9967b` | PRD 4 — the health record foundation |
| `1ae3c37` | PRD 5 and PRD 6 — medication reminders and symptom tracking |
| *(uncommitted)* | PRD 7 — appointments and Prepare for Appointment |
| *(uncommitted)* | PRD 8 — the Nura assistant, personality and memory |
| *(uncommitted)* | PRD 9 — caregivers, family messaging, emergency contacts |
| *(uncommitted)* | PRD 10 — safety monitoring, SOS and escalation |
| *(uncommitted)* | PRD 11 — the robot's display and companion experience |
| *(uncommitted)* | PRD 12 — tasks, reminders, alarms and routines |
| *(uncommitted)* | PRD 13 — privacy, data export, deletion, reliability |

> PRD 5 and PRD 6 share one commit. Their edits to the files both touched —
> Today, the card registry, the health summary, the test helpers and the docs —
> are interleaved inside the same files, and this environment has no interactive
> `git add -p`, so splitting them by path was not possible; the commit message
> says so and describes each stage separately. PRD 7 through PRD 13 are all
> finished and green and all still in the working tree. The repository
> has no git remote, so nothing has been pushed anywhere. Everything below
> describes the code as it stands on disk.

> **Nura does not diagnose illness, prescribe treatment or change medication
> doses.** It reminds and records; it does not advise. It records symptoms so
> they can be described to a clinician, and never works out what is causing
> them. The doctor summary it produces restates what was recorded and adds
> nothing.

> **Nura cannot reach anybody outside the app.** PRD 10 built Safety
> Monitoring, the emergency request and the escalation that walks PRD 9's
> emergency-contact chain. What escalation can do today is create an in-app
> alert record for a caregiver and record, channel by channel, that calling and
> texting are not configured. **No push notification has ever been delivered,
> no text message sent and no call placed.**

> **Nura cannot look anything up.** PRD 12 added tasks, reminders, alarms and
> routines, and no weather provider, news provider or external calendar is
> configured -- `providers.IMPLEMENTED` is empty for all three keys and
> `build_provider` raises for every name, so **no forecast, headline or
> external calendar event has ever been fetched by this repository** and no
> configuration can make one appear. **No alarm and no notification has ever
> fired**, because the app has never run on a physical phone.

> **Nothing watches anybody.** There is no fall, seizure-like, vomiting or
> immobility detection: `services.safety.detectors.DETECTORS` is empty, no
> detector has ever produced a reading, and **no clinical validation of any
> kind has been performed.** Safety Monitoring means Nura asks whether somebody
> is okay when something reports a possible event, and the only thing that can
> report one today is a development harness.

---

## 1. Honest status

Three things are true at once, and mixing them up would be the easiest way to
misread this project.

**Verified by running it.** The backend, its database schema and its rules:
1227 tests against a real PostgreSQL database with the real migrations applied,
including both daylight-saving transitions, the robot's medication route driven
with a real device token, the symptom authorization chain walked at every depth,
a real PDF generated, stored, re-read and parsed back, a whole conversation with
Nura driven turn by turn against a scripted model, a caregiver invited,
accepted, permissioned, read, refused, proposed-to, approved and revoked across
two real accounts holding two genuinely signed tokens, and a safety event
triggered by a simulated device, checked, timed out through the real
maintenance worker on a frozen clock, escalated through a real contact chain and
answered late, and a whole robot presentation cycle driven by a simulated
device: capabilities reported, the queue reconciled from current state, a card
fetched, rendered to text and acknowledged, an emergency preempting a family
message, a render failure recorded as one, and a day of daily life driven
through: a task completed and a stale edit refused, a fortnight of reminder
occurrences generated and replenished, a routine run ticked step by step, and
every external capability asked for and refused, and -- PRD 13's
addition -- every owner route in the application requested by a second owner
and by a caregiver holding every permission, a profile deleted with its files
checked gone from storage, and eleven classes of sensitive content asserted
absent from the logs. The app: 1,454 tests, including
the real Today, Health, medication, symptom, appointment, Nura, caregiver,
safety and Nura Device screens mounted
and driven, a symptom described from scratch and saved, the guided conversation
driven turn by turn, an appointment typed in and a summary generated, previewed
and shared, a message sent to Nura and a failure retried, a permission changed
and the request body checked, a care request approved, monitoring started with
a chosen duration and timeout, an emergency request confirmed and cancelled,
the whole pairing flow against a simulated robot that speaks the real protocol,
and all five offline queues from submission to sync. Email sign-in was
exercised end to end during PRD 1.

None of Today, the health record, the medication system, the symptom system,
the appointment and report workflow, the Nura assistant, the caregiver and
family layer, the safety layer or PRD 12's daily-life features needs a robot,
and that is tested rather than asserted: the Health overview test runs on an account with no device at all and
checks the screen loads without a single device request, the medication, symptom
and appointment tests never touch a radio, and Today's three connection states
are produced by the same `last_seen_at` field a real robot writes, which a
development script writes directly.

**Two things became testable in PRD 6 and PRD 7 that were not before.** Every
field on the symptom form, and every field on the appointment form, writes into a
Zustand store rather than into local component state, and a store update does
re-render under React 19 — so those forms are driven the way a user drives them,
typing included. PRD 7 did the same for the report selection, which is why "tick
a symptom, go forward, come back, it is still ticked" is an assertion rather than
a hope. The health and schedule forms are still in the older position described
in section 7.

**Verified by construction, not by running.** The firmware compiles for three
build configurations, and its cryptography matches RFC 9382's published test
vectors plus a vector generated by the app. That proves the maths agrees; it
does not prove a radio works.

**Not verified at all.** Everything involving hardware. **The robot has not
been built.** No BLE connection, Wi-Fi provisioning, device claim or heartbeat
has ever happened between a real phone and a real board, and no robot has ever
confirmed a dose by voice — that route is a real, tested contract with nothing
on the other end of it. **No notification has ever been delivered by a phone:**
the reminder service is tested against a recording stub, and
`expo-notifications` has never run on a device. **No symptom photo has ever been
taken on a phone:** the picker and the compression step run through
`expo-image-picker` and `expo-image-manipulator`, neither of which has an
implementation under Jest, so what is proven is the upload contract, the type
sniffing, the authorization chain, the deletion of both object and row, and the
queue that holds a photo until it can be sent. **No report PDF has ever been
shared from a phone:** the document itself is genuinely generated and read back
by the backend tests, but the download and the share sheet run through
`expo-file-system` and `expo-sharing`, neither of which has an implementation
under Jest. **No frame has ever been drawn on a robot's panel and no sound has
ever been played:** PRD 11's physical display driver compiles and reports
`not_verified` rather than `available`, because an SPI `init()` returning true
is not evidence a person saw a legible frame, and the audio output returns
false from every call. **No physical robot has ever acknowledged a
presentation**, so every `displayed` row in any database came from a simulated
acknowledgement in a test. **No alarm has ever fired, no vibration has been
felt and no operating-system background behaviour has been observed**, and
**nothing external is configured** -- there is no weather provider, news
provider or external calendar, and no code path that could reach one. The app
has never run on a phone. Google, Apple and
phone sign-in are implemented but unexercised.

**Built, tested and deliberately switched off:** the symptom red-flag rules. PRD 6
section 44 permits urgent-care safety-netting only with a reviewed rule set, and
nothing here has been reviewed by a clinician, so
`symptom_red_flag_rules_enabled` defaults to False and the only thing a running
deployment says about a symptom is the generic worsening sentence. The rules are
written down and exercised by the tests so a later review has something real to
review.

Nothing in the product simulates success to cover a gap: an unconfigured auth
provider says so, and the app refuses to report a robot online until the
backend has actually heard from it.

---

## 2. The pieces

```text
┌──────────────────────┐
│   Nura mobile app    │  React Native + Expo, TypeScript
│   iOS and Android    │  Detail, control, setup
└──────────┬───────────┘
           │ HTTPS / JSON          ┌──────────────────────┐
           ▼                       │  Nura robot          │
┌──────────────────────┐           │  XIAO ESP32-S3       │
│   FastAPI backend    │◀──Wi-Fi───┤  C++ / PlatformIO    │
│   owns authorisation │           └──────────┬───────────┘
└──────────┬───────────┘                      │ BLE, setup only
           │ SQLAlchemy                       │
           ▼                                  ▼
┌──────────────────────┐            (the phone, during pairing)
│  PostgreSQL          │
└──────────────────────┘
```

The backend is the only component trusted with authorisation. BLE exists for
first contact and recovery; normal operation is Wi-Fi through the backend, so
the app keeps working when the phone is not in the room.

### Versions

| Component | Version |
| --------- | ------- |
| Node / Python / PostgreSQL | 24.19.0 / 3.12.10 / 17.11 |
| Expo SDK / React Native / React | 57 / 0.86.3 / 19.2.3 |
| expo-router, Zustand, TanStack Query | 57.0.21, 5.0.15, 5.102.8 |
| FastAPI, SQLAlchemy, Alembic, psycopg | 0.141.1, 2.0.52, 1.20.0, 3.3.5 |
| fpdf2 (report PDFs) / pypdf (tests only) | 2.8.8 / 6.19.0 |
| anthropic (the assistant's model provider) | 1.8.0 — **unverified**, see §7 |
| PlatformIO espressif32 → Arduino core | 7.1.3 → 2.0.17 |
| NimBLE-Arduino, ArduinoJson, LovyanGFX | 2.5.1, 7.4.3, 1.2.28 |

---

## 3. Backend

FastAPI, SQLAlchemy 2.0 (sync), Alembic, PostgreSQL. Routes live under
`/api/v1`; `GET /health` is deliberately unversioned and does not touch the
database, so a database blip cannot make the app's connection indicator lie.

### Endpoints

| Route | Caller | Purpose |
| ----- | ------ | ------- |
| `GET /health`, `GET /api/v1/version` | anyone | liveness, and minimum app version |
| `GET|PATCH /api/v1/me` | app | account, settings, linked profiles |
| `GET|PATCH /api/v1/onboarding` | app | progress through the state machine |
| `POST /api/v1/profiles`, `GET|PATCH /api/v1/profiles/{id}` | app | the people Nura is for |
| `POST /api/v1/devices/provisioning-sessions` | app | single-use token for one robot |
| `GET /api/v1/devices/provisioning-sessions/{id}` | app | has the robot claimed yet? |
| `GET /api/v1/devices`, `GET|PATCH /api/v1/devices/{id}` | app | the account's robots; rename |
| `GET /api/v1/devices/{id}/status` | app | online / offline / unknown |
| `POST /api/v1/devices/{id}/complete-setup` | app | request the introduction, advance onboarding |
| `POST /api/v1/devices/claim` | robot | provisioning token → device token |
| `POST /api/v1/devices/heartbeat` | robot | "I'm online"; returns pending actions |
| `GET /api/v1/today` | app | the whole Today screen in one request |
| `GET|PUT /api/v1/daily-checkins/today` | app | today's wellbeing answer |
| `GET /api/v1/daily-checkins/recent` | app | a short window, as a count |
| `GET|PUT /api/v1/dashboard-preferences` | app | which cards show, and in what order |
| `GET /api/v1/profiles/{id}/health-summary` | app | counts and completeness, never names |
| `GET|PATCH /api/v1/profiles/{id}/health-setup` | app | resume point, and blood type |
| `GET|POST|PATCH|DELETE /api/v1/profiles/{id}/{records}` | app | the six health record types |
| `GET|POST|PATCH|DELETE /api/v1/profiles/{id}/medication-schedules` | app | when to remind, and pausing |
| `GET /api/v1/profiles/{id}/medication-doses` | app | history, and today's doses |
| `POST .../medication-doses/{id}/taken|snooze|skip` | app | the three actions |
| `GET /api/v1/profiles/{id}/medication-adherence` | app | one figure, with its counts |
| `GET|PATCH|POST /api/v1/profiles/{id}/medication-supply` | app | counts, thresholds, refills |
| `GET|POST /api/v1/profiles/{id}/symptoms` | app | episodes, and creating one with its first entry |
| `GET /api/v1/profiles/{id}/symptoms/summary` | app | active, worsening and recent counts |
| `GET|PATCH|DELETE /api/v1/profiles/{id}/symptoms/{id}` | app | one episode with its history |
| `POST .../symptoms/{id}/resolve`, `.../recur` | app | ending a symptom, and one that came back |
| `GET|POST .../symptoms/{id}/entries` | app | observations, newest first |
| `PATCH|DELETE .../entries/{id}` | app | correcting or removing one |
| `POST .../entries/{id}/photos` | app | multipart upload, private |
| `GET .../photos/{id}/content` | app | the bytes, re-authorized per request |
| `DELETE .../photos/{id}` | app | removes the object and the row |
| `GET|POST /api/v1/profiles/{id}/appointments` | app | the three lists, and adding one |
| `GET /api/v1/profiles/{id}/appointments/summary` | app | counts for Care |
| `GET|PATCH|DELETE .../appointments/{id}` | app | one visit, with its questions and versions |
| `POST .../appointments/{id}/cancel|complete|reopen` | app | the three status moves |
| `GET|POST .../appointments/{id}/questions` | app | the user's own words, in their order |
| `PUT .../questions/order`, `PATCH|DELETE .../questions/{id}` | app | reorder, edit, answer, remove |
| `GET .../appointments/{id}/prepare` | app | the whole review, for one period |
| `GET|POST .../appointments/{id}/reports` | app | versions, and generating one |
| `GET|DELETE .../reports/{id}` | app | one version with its frozen content |
| `GET .../reports/{id}/pdf` | app | the document, re-authorized per request |
| `GET /api/v1/profiles/{id}/assistant/home` | app | the Nura tab in one request |
| `POST .../assistant/prompts/dismiss` | app | stops one proactive prompt returning |
| `GET|PATCH .../assistant/preferences` | app | personality, voice, verbosity, mode |
| `GET|POST .../assistant/memories` | app | what Nura remembers |
| `PATCH|DELETE .../assistant/memories/{id}` | app | edit, pause, forget one |
| `GET|POST .../assistant/conversations` | app | threads, and starting one |
| `GET|PATCH|DELETE .../conversations/{id}` | app | one thread; rename, archive, delete |
| `POST .../conversations/{id}/messages` | app | send one, and what came back |
| `POST .../messages/{id}/confirm` | app | the only path a suggested change takes |
| `GET|POST .../caregivers`, `.../caregivers/invitations` | app | the caregiver list, and minting an invitation |
| `PATCH|DELETE .../caregivers/{id}` | app | relabel (grants nothing), or revoke now |
| `GET|PATCH .../caregivers/{id}/permissions` | app | the eight categories, one at a time |
| `GET /api/v1/caregiver-permissions` | app | the category catalogue, with the server's words |
| `GET|POST /api/v1/caregiver-invitations/{token}[/accept|/decline]` | app | review and answer an invitation |
| `GET /api/v1/caregiver/profiles` | app | the only route returning profiles the caller does not own |
| `GET .../care/home` | caregiver | their Today, assembled permission by permission |
| `PATCH .../care/notifications` | caregiver | what they hear about, per supported person |
| `GET .../care-summary` | app | the Care screen's counts, in one request |
| `GET|POST .../caregiver-suggestions` | app | care requests; POST is the caregiver's |
| `POST .../caregiver-suggestions/{id}/approve|decline|cancel` | app | the owner decides; the caregiver may withdraw |
| `GET|POST .../family/threads[/{id}/messages]` | app | the care conversation |
| `POST .../family/calls` | app | 503 `calling_not_configured`, in every deployment |
| `GET|POST|PATCH|DELETE .../emergency-contacts[/{id}]` | app | the chain. Owner-only at every verb |
| `POST .../emergency-contacts/reorder` | app | the order as displayed; the server renumbers |
| `GET .../safety/status` | app | the whole Safety screen, with any passed deadline acted on |
| `GET .../safety/capabilities` | app | what this build can actually do (section 106) |
| `POST .../safety/monitoring/start|stop` | app | explicit, time-boxed, server decides when it ends |
| `GET .../safety/events[/{id}]` | app | safety history, and one event with every attempt |
| `POST .../safety/sos` | app | an emergency request. Escalates inside the request |
| `POST .../safety/events/{id}/respond` | app | "I'm okay" / "I need help" / "false alarm" |
| `POST .../safety/events/{id}/cancel|false-alarm` | app | stop what has not gone; label a finished one |
| `GET .../care/safety-alerts` | caregiver | their alerts. Reading one is what marks it read |
| `POST .../care/safety-alerts/{id}/acknowledge` | caregiver | "I'm checking on them". Resolves nothing |
| `GET .../devices/{id}/capabilities` | app | twelve capability states, never one boolean (section 10) |
| `GET|PATCH .../devices/{id}/presentation-preferences` | app | brightness, volume, privacy, read-aloud. `reduced_motion` has three states |
| `GET .../devices/{id}/presentation-history` | app | what Nura was asked to show, and what became of it (section 96) |
| `GET .../devices/{id}/robot-status` | app | the whole Nura Device screen: mode, queue depth, current card |
| `POST /api/v1/device-actions/medication-doses/{id}/taken` | robot | the future voice confirmation |
| `POST /api/v1/device-actions/safety-events` | robot | a future detector's trigger. No profile id in the body |
| `POST /api/v1/device-actions/capabilities` | robot | what this hardware is. The only writer of `not_verified` |
| `GET /api/v1/device-actions/presentations/next` | robot | the next thing to show, or 204. Reconciles first |
| `POST /api/v1/device-actions/presentations/{id}/ack` | robot | the only writer of `displayed_at`, anywhere |
| `GET .../daily-life/summary` | app | tasks, reminders, routines and the next alarm, in one request |
| `GET|POST .../tasks`, `GET|PATCH|DELETE .../tasks/{id}` | app | the list. `PATCH` cannot touch a status |
| `POST .../tasks/{id}/complete|reopen|archive|cancel` | app | the four transitions, each its own route |
| `GET|POST .../reminders`, `GET|PATCH|DELETE .../reminders/{id}` | app | general reminders, with their occurrences |
| `POST .../reminders/{id}/pause|resume|cancel` | app | stop, restart, or end one for good |
| `GET .../reminder-occurrences` | app | a range of local days. What the phone's scheduler mirrors |
| `POST .../reminder-occurrences/{id}/complete|dismiss|snooze` | app | done, seen, or put off (three times at most) |
| `GET|POST .../alarms`, `GET|PATCH|DELETE .../alarms/{id}` | app | alarms. Every list carries the limitation sentence |
| `GET|POST .../routines`, `GET|PATCH|DELETE .../routines/{id}` | app | routines and their steps |
| `POST .../routines/{id}/pause|resume|archive` | app | the three a routine has |
| `GET .../routine-runs/today`, `GET .../routine-runs/{id}` | app | today's runs, and one with its progress |
| `POST|DELETE .../routine-runs/{id}/steps/{step}/complete` | app | tick a step, and un-tick it |
| `POST .../routine-runs/{id}/complete|skip` | app | finished, or not a day for it |
| `GET .../assistant/external-capabilities` | app | the capability map. All three external keys read `not_configured` |
| `GET .../care/routines` | caregiver | routines only, and the only caregiver route PRD 12 adds |
| `GET .../privacy/summary` | app | the whole Privacy & Security screen, in one request |
| `POST .../privacy/conversations/delete-all` | app | every conversation, and nothing else |
| `GET|POST .../privacy/export` | app | the archives, and building one. Synchronous |
| `GET|DELETE .../privacy/export/{id}` | app | one archive, with its expiry already compared |
| `GET .../privacy/export/{id}/content` | app | the bytes. Authenticated, never a signed URL |
| `POST .../privacy/delete-request` | app | what deleting would remove. Changes nothing |
| `POST .../privacy/delete-confirm` | app | the irreversible one. Exact phrase, no defaults |

### Rules the server enforces

These are server-side because a client cannot be trusted to enforce them:

- **Identity comes from a verified token, never from a request body.** The
  backend verifies Supabase access tokens against the project's public JWKS
  endpoint and maps the `sub` claim to a local account, creating it on first
  sight. There is no `/users/{id}` route at all.
- **Onboarding requirements are cumulative**, so a client cannot jump to
  "ready" and skip the consent gate. Both consent acknowledgements are separate
  and both required. Progress never moves backwards.
- **`robot_connected` cannot be claimed by the app.** It requires a robot the
  account claimed that has since sent a heartbeat.
- **Another account's resource returns 404, not 403**, so ids are never
  confirmed to exist.
- **Online is derived, never stored** — computed from `last_seen_at` on every
  read, so it cannot go stale.
- **A check-in belongs to a profile, one per local day.** A unique constraint
  on `(profile_id, checkin_date)` makes a duplicate daily record impossible,
  including one arriving late from the offline queue.
- **The client's "today" is checked.** A date more than a day from the server's
  own is refused, so the "today" endpoints cannot write arbitrary history.
- **The latest explicit user edit wins.** A queued submission carries when the
  user made it; if the stored row is newer, the stored row stands and is
  returned so the client adopts it.
- **A card whose feature does not exist cannot be enabled**, so no preference
  row exists for a feature that is not there.
- **A health record is reachable only through a profile the caller owns**, and
  is fetched by profile and id together — so nothing is loaded first and
  authorized second. Anything else is 404.
- **Provenance is the server's.** A client cannot set a record's `source`, so
  nothing can claim to have come from a clinician import when a person typed
  it in.
- **A date keeps its precision.** A condition or procedure may carry an exact
  date *or* a year, never both; the database enforces it.
- **A reminder is a wall-clock time.** A schedule carries its own IANA zone, so
  8am stays 8am across a daylight-saving change. The two awkward days a year
  are decided, not left to chance: one dose either way.
- **An action sets a state on one row.** Taken, Snooze and Skip update the
  dose rather than appending an event, so a retried request leaves one taken
  dose and decrements supply once, and a late Taken keeps the same dose.
- **A robot never overrides a person.** A `robot_voice` confirmation on a dose
  somebody already recorded changes nothing and errors at nobody.
- **Editing the future never edits the past.** A schedule change rebuilds
  doses from now forward and cannot reach one already recorded; deleting a
  schedule clears the link on its doses rather than cascading.
- **A medication with dose history cannot be deleted**, only marked inactive —
  which pauses its schedules and keeps everything recorded.
- **A symptom is never a condition.** They are separate tables, nothing converts
  between them, and their counts are reported separately so a summary cannot
  imply a diagnosis.
- **Nothing infers that a symptom has ended.** A status changes because somebody
  changed it, and resolving records when — a CHECK constraint makes
  `status = 'resolved'` imply a `resolved_at`.
- **A symptom that comes back is a new linked episode**, not a reopened one, so
  each bout keeps its own onset and history. Asking for a recurrence of an
  ongoing episode is a 409.
- **A client cannot claim a reserved source.** Only `manual_app` and
  `guided_app` are writable; `robot_voice_future` and the rest are readable and
  refused on input.
- **A retry cannot create a second record.** Entries, episodes and photo uploads
  are all keyed by a client-generated id that is unique per scope in the
  database, so idempotency is a constraint rather than a convention. A replay
  returns the stored row **unchanged** — a retry is not an edit.
- **Worsening is recorded, never inferred.** It comes from the user choosing it,
  their own severity rising by two or more across two saved entries, or an
  associated symptom they added. There is no branch on an absolute severity
  anywhere: 10/10 alone is not an emergency.
- **A hedged or denied phrase suppresses a safety rule.** Matching subtracts
  `uncertain_items` and `negated_items` before anything can fire, so "I'm not
  sure if I'm short of breath" is not a report of breathlessness.
- **The urgent-care rules are off.** `symptom_red_flag_rules_enabled` defaults to
  False; with it off, the only thing said is the generic worsening sentence.
- **A symptom photo has no URL.** `storage_key` never appears in a response, and
  the bytes come only from a route that re-checks the account, the profile, the
  episode, the entry and the photo. A declared content type is checked against
  the file's own header.

### Data model

```text
users (the account: who signs in)          profiles (the person Nura is for)
  auth_provider_id  unique, from the token   preferred_name, age_range (a band,
  email / phone     either may be null       not a birth date), country, pronouns
  setup_mode        self | assisted
  onboarding_status the state machine      account_profile_roles
  terms_accepted_at                          joins the two, role self | setup_helper
  privacy_acknowledged_at

user_settings                              devices (a robot that reached us)
  theme, language                            hardware_id            unique
  larger_text, high_contrast,                claimed_by_account_id  nullable
  reduce_motion, voice_first_preference,     owner_profile_id
  simplified_interface                       display_name           a label only
                                             bootstrap_secret_hash  ┐ sha-256
provisioning_sessions                        device_token_hash      ┘ only
  account_id, profile_id, hardware_id        claimed_at, last_seen_at
  token_hash   sha-256 only                  setup_completed_at
  expires_at   10 minutes                    introduction_requested_at
  consumed_at  set by the claim              introduced_at

the health record (PRD 4)                  all owned by a profile, all
  medical_conditions  medications            cascading with it. Approximate
  allergies           clinicians             dates are a date *or* a year,
  procedures          medical_notes          never both. See
                                             docs/architecture/health-data.md

medication scheduling (PRD 5)              a record is what a medication *is*;
  medication_schedules    timezone, start   a schedule is when to remind. Doses
    medication_schedule_times  time,        are rows generated 14 days ahead;
                               weekday      schedule_id is SET NULL, not a
  medication_doses        scheduled_for,    cascade, so deleting a schedule
                          local_date,       keeps the history it produced.
                          status, source    See
  medication_supply       remaining,        docs/architecture/medication-system.md
                          threshold

symptom tracking (PRD 6)                   an episode is one *bout*: a symptom
  symptom_episodes   name, body_site,        that comes back is a new episode
                     status, three onset     linked through previous_episode_id
                     precisions, resolved_at and carrying status `recurring`.
    symptom_entries  recorded_at, severity,  Six list fields are jsonb defaulting
                     change_state, the       to [], including what was denied and
                     structured fields,      what was uncertain, so nothing reads
                     negated/uncertain/      as more certain than it was said.
                     context lists,          client_entry_id is unique per
                     client_entry_id         profile: the idempotency key.
      symptom_photos storage_key (unique,    The bytes are not in the database.
                     never returned),        See
                     content_type, byte_size docs/architecture/symptom-system.md

daily_checkins (one person, one day)       dashboard_preferences
  profile_id      not the account            profile_id
  checkin_date    a plain local date         card_key    no CHECK: the registry
  wellbeing_level good|okay|not_great                    validates it instead
  note            optional, ≤ 280 chars      visible, position
  unique (profile_id, checkin_date)          unique (profile_id, card_key)
  device_id
```

```text
appointments (a visit, entered by hand)    appointment_questions
  clinician_id   optional, SET NULL          text       exactly as typed
  scheduled_at   the instant                 position   the user's order
  timezone       the zone it was made in     is_answered, answer_note
  status         scheduled|completed|        client_question_id  idempotency key
                 cancelled|missed
  preparation_status  a cache of a          appointment_reports
                 derivation, server-only      version         never reused while stored
  cancelled_at / completed_at  implied by     period_start / period_end / preset
                 status, by CHECK             include_appendix
  reminders_enabled                           selection  jsonb: what the user chose
  visit_notes, follow_up_date                 snapshot   jsonb: the finished text
  client_appointment_id  idempotency key      file_storage_key  unique, never returned
                                              page_count, byte_size, status
```

Every value set — themes and onboarding statuses through to dose windows, symptom
statuses, appointment types and report presets — is enforced by a database CHECK
constraint generated from the same Python tuple the API validates against, with an
assertion at import time that the two still agree. They cannot drift.

**None of the account or device tables holds medical information**, and a test
asserts that. Medical data lives only in the health record, medication, symptom
and appointment tables, all of which belong to a profile and cascade with it.

Two absences in the PRD 7 tables are asserted by tests rather than left to
discipline: no calendar-sync field of any kind (no external id, no sync token, no
provider), and no cross-account field of any kind (no share token, no caregiver
id, no public URL). Adding either later is a deliberate schema change rather than
something that crept in.

PRD 8's five tables — `conversations`, `conversation_messages`,
`assistant_memories`, `assistant_preferences`, `assistant_prompt_dismissals` —
carry three asserted absences of their own. **No foreign key into the health
record**, the medications, the symptoms or the appointments, which is what makes
"deleting a conversation deletes a conversation" checkable by reading the schema
rather than by trying it. **No clinical field** anywhere in assistant memory: no
category for a condition, no diagnosis column, 300 characters of preference.
**No model, provider, key or prompt column** on `assistant_preferences`, because
a client that could choose the model could choose a cheaper one with different
safety behaviour.

Two more shapes worth noticing. `conversation_messages` has no `updated_at`: a
message is not edited, because correcting something means saying the next thing.
And its `position` is unique within a thread, so two messages written in the
same millisecond still have an unambiguous order.

PRD 9's seven tables — `caregiver_relationships`, `caregiver_permissions`,
`caregiver_suggestions`, `family_threads`, `family_messages`,
`emergency_contacts`, `caregiver_audit_events` — carry the most consequential
absence in the schema so far. **There is no caregiver row in
`account_profile_roles`.**

That table is what `deps.get_owned_profile` walks, and every profile-scoped route
from PRD 0-8 authorizes through it. A `caregiver` value in `PROFILE_ROLES` would
have granted the complete health record, every symptom photo and every doctor
report on the day PRD 9 shipped — without changing one route, so with nothing to
review and no test to fail. Caregiver access is therefore a *second* relationship
table with its own dependency, and `test_models.py` asserts `PROFILE_ROLES` is
still exactly `self` and `setup_helper`.

Three more asserted absences. **No foreign key from any PRD 9 table into the
health record**: a suggestion names its target as a type plus an id and the
service resolves it inside the profile at approval time, which is what makes
"verify the target still exists" a real check rather than a trusted reference.
**No global permission flag** — no `can_view_all`, no `full_access` — because
section 7 forbids one and the way to be sure is for no column to be able to act
as one. And **no read event in the audit vocabulary**: section 49 says not to
notify the user when a caregiver views something and section 50 not to build a
feed of it, so no event type contains `view`, `read`, `opened` or `accessed`.

Two constraints are load-bearing. `uq_caregiver_relationships_active` is
*partial* — unique on (profile, account) only `WHERE status = 'active'` — so
revoking somebody and inviting them back works while two simultaneous active
relationships cannot exist. And `ck_caregiver_suggestions_action_type` is built
from `CAREGIVER_SUGGESTION_ACTION_TYPES`, which is how section 85's forbidden
changes are forbidden: `change_medication_dose` is not validated away, it cannot
be stored.

PRD 10's five tables — `safety_monitoring_sessions`, `safety_events`,
`safety_escalation_attempts`, `safety_alerts`, `safety_audit_events` — carry
their own set of deliberate absences, and two of them are the whole design.

**No confidence column on `safety_events`.** PRD 10 section 54 calls confidence
engineering metadata about a detector's own output rather than a probability
that somebody is ill. It is carried on the detector interface and dropped before
an event is stored, because a column is a thing a screen eventually reads — and
a number beside "possible seizure-like activity" would be exactly the medical
claim section 52 forbids. `test_models.py` asserts its absence, along with
`severity`, `diagnosis` and every media column (section 92).

**No foreign key into the health record.** Safety data is about what happened
and who was tried; it is not a second route into somebody's medical history. The
only two references out of these tables are to `emergency_contacts` and
`caregiver_relationships`, both `ON DELETE SET NULL`, because an attempt that
records who was tried must outlive the contact it was tried on --
`recipient_label` is the snapshot that keeps it readable.

Three constraints are load-bearing. `uq_safety_monitoring_sessions_active` is
partial on `status = 'active'`, so one person is monitored once at a time while
every past session keeps its history.
`ck_safety_monitoring_sessions_ended` states that an active session has not
ended and an ended one has — "ended at some point but still active" is the one
state a monitoring system must never reach. And
`uq_safety_escalation_attempt_recipient` is unique on (event, `recipient_key`,
channel), where `recipient_key` is a single text column rather than three
nullable foreign keys: PostgreSQL treats NULLs as distinct, so a unique
constraint over nullable columns would never collide and a duplicated worker run
would contact somebody twice (section 75).

And one value set changed rather than grew.
`CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE` went from two entries to one:
`safety_alerts` left it, because PRD 9 section 94 allowed the key to exist
before its event source did and PRD 10 built the source. `routines` stayed, for
the reason it always had — and then left in PRD 12, below.

**PRD 11 adds three tables, all hanging off `devices`.**

```text
device_presentations                one thing for one robot to show
device_presentation_preferences     how that robot should behave
device_capabilities                 what that robot says it can do
```

Nothing in PRD 0-10 is reshaped: no column changes type, nullability or
default, and no constraint is replaced. Every foreign key points at `devices`
or `profiles`, so the robot is additive in the schema exactly as it is in the
code. There is **no foreign key from a presentation into a dose, an
appointment or a message** — only a `dedupe_key` naming the thing it came from
— which is what lets a card be expired, cancelled or never shown without any
effect on the health data it was built from. `test_models.py` asserts that, and
asserts the absence of any URL, media, attachment or asset column (section
108).

One constraint carries the whole of section 14:

```sql
CHECK (displayed_at IS NULL
       OR (ack_state IS NOT NULL
           AND ack_state IN ('render_started', 'render_completed')))
```

The backend handing a command to a robot is not the robot showing it, and with
this there is no code path — now or in a later release — that can mark a
presentation displayed without a device having said it rendered it. The
parenthesised half matters more than it looks: a SQL `CHECK` is satisfied when
it evaluates to TRUE *or null*, and `ack_state IN (…)` is null when `ack_state`
is, which is precisely the row the constraint exists to refuse. Written the
short way it accepted it, and the test that writes past the service is what
caught that.

Two more are worth reading. `uq_device_presentations_dedupe` is unique on
(device, `dedupe_key`) and partial over the four open statuses, so a retried
build folds into the card already waiting while tomorrow's dose still gets its
own (section 57). And `device_presentation_preferences.reduced_motion` is
**nullable with no default**, because null means *follow the account's
accessibility preference* (sections 30 and 105) — a plain boolean would have
had to pick a value and would then have stopped following that preference the
first time anybody opened the screen.

Section 119 invites a decision on where capabilities live, and it is one row
per capability rather than JSONB on `devices`: the key and the state get CHECK
constraints, `reported_at` is per capability so "the screen was proven last
Tuesday and the speaker has never been tested" is representable, and a device
reporting a subset does not erase the rest.

**PRD 12 adds eight tables, and the division between them is the design.**

```text
tasks                        no occurrence rows, and a time is optional
general_reminders            a pattern
general_reminder_occurrences the concrete rows it generates
alarms                       no occurrence rows at all
routines                     a standing commitment
routine_steps                its steps, numbered from their order
routine_runs                 one per day it runs
routine_step_completions     one per step ticked
```

**An alarm generates nothing**, because nobody asks whether last Tuesday's
seven o'clock alarm went off: "is it ringing" is the stored time compared with
the clock, and `next_fire_at` is derived on read. A task generates nothing
either, and may carry no time at all -- section 5's position, stated as a
nullable column rather than as a convention.

**A task carries two timestamps**, `content_updated_at` and
`status_changed_at`, and `TaskUpdate` has no `status` field. Section 40 names
the failure -- a title edit arriving late from another device undoing a
completion -- and the two columns plus the missing field make it
unrepresentable rather than tested for. `test_productivity_tasks.py` does
exactly what section 40 warns about and asserts the completion survives.

`weekdays` is `smallint[]` with 0 = Monday, and its CHECK constraints are
written `CASE WHEN weekdays IS NULL THEN … ELSE … END` rather than
`weekdays IS NULL OR …`, for the reason PRD 11's acknowledgement constraint
taught: a SQL `CHECK` passes when it evaluates to null, so the short form
accepts the row it exists to refuse.

`uq_routine_step_completion` is unique on (run, step), which is what makes a
retried offline tick idempotent -- an offline queue cannot invent progress.
`uq_task_client_id`, `uq_general_reminder_client_id`, `uq_alarm_client_id`,
`uq_routine_client_id` and `uq_routine_step_completion_client_id` do the same
for creates, the pattern PRD 7 set.

There is **no foreign key from any of these tables into the health record**, and
no medical column on any of them. A task list is not a medical record, which is
the whole reason PRD 12 keeps its own tables rather than reusing a note.

And the value set that has been shrinking since PRD 10 is now empty.
`CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE` went two → one → **none**: `routines`
was its last entry, and PRD 12 built the record it was reserved for. The tuple
and `CareScope.usable()` stay, because the next permission reserved before its
data exists goes there and the screens that render the sentence keep working.
`test_models.py` asserts the tuple is empty -- the honest record of two
permissions becoming real.

**PRD 13 adds one table, and nothing else at all.**

```text
data_exports    one archive of one profile, with its expiry
```

No existing table is touched -- no column added, no type changed, no CHECK
constraint replaced. That is possible because the stage's two features need
almost nothing of their own. An export needs a row because it has a file in
private storage and an expiry. **Deletion needs none**: it is synchronous, and
a table recording that somebody asked to be deleted, surviving after they were,
would be the single piece of their data that outlived the request.

`status` carries all five of section 20's values and this build produces three;
`requested` and `generating` belong to a worker nobody needs, kept so a later
one requires no migration. Two CHECK constraints make the honest states the
only representable ones: a row that says `ready` has a file *and* an expiry
behind it, and a row that says `failed` has no file. The first is the same shape
as `ck_appointment_reports_ready_file` and exists for the same reason -- an offer
to download something storage cannot find is worse than an honest failure.

Expiry is **applied on read**, as PRD 11 does it: the download route refuses a
row whose expiry has passed whatever the status says, and
`scripts/privacy_maintenance.py` then marks it and deletes the bytes. Both
agree because the route never trusts the status alone, which is what stops a
worker that has not run turning into a file served past its expiry.

Migrations: `098b6aa76259` (PRD 0), `cc6f6b33617e` (PRD 1), `8075d63c6b15`
(PRD 2), `4e26bcd716d6` (PRD 3), `26d6a128b39a` (PRD 4), `36e11e301614`
(PRD 5), `4e1eed8b939b` (PRD 6), `1d0b833773e8` (PRD 7), `309d67dad380`
(PRD 8), `0ff070fd606b` (PRD 9), `724cae2ee9c2` (PRD 10), `03ce36f69b39`
(PRD 11), `e40d2ad16353` (PRD 12), `1af52299dead` (PRD 13). The PRD 2 one was
written by hand because Alembic reads a column rename as a drop plus an add, and
the PRD 4 one was edited to add three CHECK constraints on an existing table that
autogenerate does not see; the rest are autogenerated and hand-documented. Every
one round-trips up, down and up, and `alembic check` reports no drift from the
models.

The PRD 6 and PRD 7 migrations each add three tables and alter nothing, and
PRD 8's adds five and alters nothing: `medical_conditions` in particular is
untouched, so no existing medical record can be affected by any of them. PRD 7's
only reference out into the older tables is `appointments.clinician_id`, which is
`ON DELETE SET NULL` — removing a doctor from somebody's list must not delete the
appointments that mention them. PRD 8 has no such reference at all; every one of
its foreign keys points at `profiles` or at another assistant table.

PRD 9's migration adds seven tables and is the **first since PRD 3 to alter an
existing one** — `user_settings` gains four notification booleans, each with
`server_default 'true'`, so every existing row has a value the moment it runs and
no backfill is needed. Nothing else changes: no column changes type, nullability
or default, and no medical record is touched. Every PRD 9 foreign key points at
`profiles`, at `users`, or at another caregiver table.

PRD 10's migration adds five tables, one nullable column
(`user_settings.safety_bedtime`, no default — section 6 wants a bedtime set
explicitly, so null is the correct starting state) and **one replaced CHECK
constraint**. `ck_conversation_messages_safety_mode` is dropped and recreated to
admit `emergency_active`: PRD 8 deliberately left that value out on the grounds
that a mode nothing acts on is a promise Nura cannot keep, and PRD 10 section 43
built the thing that acts on it. Replacing a CHECK constraint is exactly why
these value sets are tuples and CHECK constraints rather than PostgreSQL ENUMs
-- there is no `ALTER TYPE` anywhere in it, the downgrade puts the old
constraint back, and it first moves any `emergency_active` row to the value it
would have had before. No medical record is touched by any of it.

PRD 12's migration adds eight tables, two columns on
`device_presentation_preferences` (`daily_life_display_enabled` and
`daily_life_privacy_level`, both NOT NULL with server defaults, so every
existing row has a value the moment it runs and no backfill is needed) and **five replaced CHECK constraints** -- the
presentation type, priority and source sets gain PRD 12's four card types and
its `daily_life` source, and the caregiver suggestion action and target sets
gain `add_routine`, `change_routine_time`, `pause_routine` and `routine`.
Replacing five CHECK constraints in one migration without an `ALTER TYPE`
anywhere is the clearest demonstration yet of why these value sets are tuples
and CHECK constraints rather than PostgreSQL ENUMs; the downgrade puts all five
old constraints back. No medical record is touched.

---

## 4. Mobile app

expo-router with typed routes; Zustand for app-wide preferences, TanStack Query
for anything fetched. Two rules hold throughout: only
`src/services/api/client.ts` calls `fetch`, and only `src/constants/config.ts`
reads `process.env`.

```text
mobile/
├── app/                       routes (file-based)
│   ├── (tabs)/                Today, Health, Care, Nura, More
│   ├── (onboarding)/          welcome → auth → setup mode → profile →
│   │                          preferences → consent → ready
│   ├── pairing/               discover → verify → wifi → progress →
│   │                          name → success, plus help
│   ├── devices/[id].tsx       status, recovery, developer diagnostics
│   ├── customize-today.tsx    show, hide and reorder Today's cards
│   ├── health/                setup, sections, record forms, blood type
│   ├── medications/           schedules, doses, history, supply, skip sheet
│   ├── symptoms/              overview, log, Talk to Nura, review, history, detail
│   ├── appointments/          list, form, detail, prepare, questions, select,
│   │                          preview, report versions
│   ├── nura/                  conversation, history, personality, voice,
│   │                          memory, modes, custom instructions
│   ├── caregivers/            the caregiver list, invite, permissions,
│   │                          care requests, care notifications
│   ├── care-mode/             Caregiver Mode: home, supported people, suggest
│   ├── family/                family messages and check-ins
│   ├── emergency-contacts/    the chain, and its order
│   ├── safety/                Safety Monitoring, the check-in, emergency
│   │                          mode, history, what Nura can do
│   ├── robot/                 Nura Device: display, audio and companion
│   │                          settings, capabilities, history, preview
│   ├── daily/                 tasks, reminders, alarms, routines, a routine,
│   │                          a run, and what Nura can reach
│   ├── privacy/               Privacy & Security, the export, the delete flow
│   └── connect-device.tsx     entry: existing robots, or "Find my Nura"
└── src/
    ├── services/provisioning/ BLE transport, SPAKE2, payload, flow controller
    ├── services/checkins/     the offline check-in queue
    ├── services/dashboard/    card layout rules (pure functions)
    ├── features/health/       section specs, form logic, API, hooks, drafts
    ├── features/medications/  schedule rules, dose wording, reminders, queue
    ├── features/symptoms/     shared draft, conversation engine, photos, queue
    ├── features/appointments/ form draft, report selection, reminders, export
    ├── features/nura/        conversation state, composer drafts, memory, personality
    ├── features/caregivers/  care mode, permission helpers, message and suggestion drafts
    ├── features/safety/      safety status, capabilities, SOS and check-in state
    ├── features/robot/       robot capabilities, preferences, presentation history
    ├── features/productivity/ tasks, reminders, alarms, routines, validation, the queue
    ├── features/notifications/ the scheduler PRD 12's reminders and alarms share
    ├── features/privacy/     the hub's state, export and deletion, the local-data inventory
    ├── features/reliability/ the one retry policy all five offline queues share
    ├── services/auth/         Supabase, chunked secure-store session
    ├── services/api/          typed client and endpoints
    ├── components/            Screen, Card, Button, ProgressSteps, …
    ├── components/today/      Today's cards and the card registry
    └── theme/                 tokens, Light/Dark palettes
```

**Errors are typed, messages are human.** Every failure becomes an `ApiError`
with a `kind` (`offline`, `unavailable`, `timeout`, `unauthorized`, `notFound`,
`validation`, `conflict`, `server`, `configuration`) plus the server's stable
`code` when there is one. A raw exception is never shown to a user.

**Today is composition, not content.** The screen fetches the day in one
request, picks one of five states (loading, success, empty, offline, error),
and hands the rest to cards it looks up by key. Adding a card in a later PRD
means three edits — server registry, key union, renderer map — and no change to
the screen. A card whose feature does not exist is never drawn; a key the app
has no renderer for is skipped, so an app older than its backend degrades
rather than breaking.

**An outage does not empty the screen.** The last Today response is kept on
the device and rendered when the backend cannot be reached — but only for the
day it was fetched on, and never including the robot’s connection, which
offline we genuinely do not know. That card says "Status unavailable" rather
than repeating a stale "Online".

**A check-in made with no signal is not lost.** It is written to the device,
the card says so plainly, and it is sent when the connection returns or when
Today is next focused. Because the endpoint is a `PUT` keyed on person and
date, a late arrival updates the same row rather than creating a second one.

**Six health record types share one screen.** Each section declares its
fields, its wording and how to summarise a record; one list screen and one
form screen read that. Six hand-written CRUD screens would be six chances for
a delete confirmation or a required-field message to drift, on the part of the
app holding someone's medical history. The backend does the opposite and
writes its routes out per resource — there the risk is obscurity, not drift.

**Reminders are mirrored, not owned.** The backend holds the schedule and the
history; the phone copies the next 48 waiting doses into the OS scheduler and
reconciles that copy whenever anything changes. Unchanged reminders are left
alone, moved ones are cancelled and re-created, and an empty plan cancels
everything — which is how a pause, a deletion, an inactivated medication and a
time change all work without a special case each. There are deliberately no
notification action buttons: acting on one would need a background handler
this app cannot promise on both platforms, so tapping a reminder opens Nura
where the buttons are real.

**A dose action made with no signal is not lost either.** It is written to the
device and the row says so, and the queue holds one answer per dose rather
than a log of taps — pressing Taken then Skip sends one final answer, because
the server holds one row per dose.

**One draft serves both symptom flows.** The manual form and the guided
conversation write into the same `SymptomDraft`, validate through the same
function, build the same payload and end on the same review screen. The only
difference is the `source` recorded, which is an observation about how the data
arrived rather than a different kind of data — so there is nowhere for either flow
to put something the other cannot read.

That draft lives in a Zustand store persisted to AsyncStorage, which buys three
things: it survives navigating between the form, the conversation and the review
screen; it survives the app being closed, which is what PRD 6 section 59 asks for;
and it makes the form testable, because a store update re-renders under React 19
where a local `useState` update from a fired event does not.

**The guided conversation is a pure function.** `(state, draft, message) ->
(state, draft)`, with the vocabulary, the extraction rules and the next-question
logic in four files and no network, model or component state anywhere. That is
what lets PRD 6 section 28's hard requirement — never ask again for something
volunteered — be asserted in three lines rather than inferred from a screenshot.

What the rules miss is not lost: an answer matching no pattern is kept verbatim
for whatever question was asked, and everything is shown on a review screen where
any field can be corrected. Without that screen a rule-based extractor would not
be shippable; with it, the vocabulary makes the conversation shorter when it works
and harmless when it does not.

**A symptom saved with no signal keeps its photos.** One pending record holds the
episode body (or an episode id), the entry and the local photo files. Photos are
uploaded one at a time *after* the description lands, and any that fail stay in
the record with the now-known episode and entry ids — so the retry uploads rather
than creating anything twice. Nothing is reported as uploaded before the backend
confirms it.

**A symptom photo is fetched with a token, not a URL.** The image source is the
API route plus an `Authorization` header, so the backend re-checks the whole
ownership chain for every byte and a URL that leaked somewhere would be useless.

**Switching person clears before it changes.** PRD 9 section 58 forbids briefly
showing the previous profile's data, and `invalidateQueries` would do exactly
that -- an invalidated query keeps serving its old value while it refetches. So
`clearProfileScopedQueries` calls `removeQueries` over a named list of
profile-scoped prefixes, and only then is the context set. The next screen starts
from a loading state, which is the honest thing for a screen that does not yet
know anything about this person. The list is named rather than a wildcard because
`removeQueries()` with no filter would also drop the account and the
supported-profile list, which are what the switcher itself is built from.

**The mode store holds a choice, not a credential.** It is a profile id the
account has already been shown in `/caregiver/profiles`; setting it grants
nothing, because every request still resolves the relationship server-side.
`useCareMode` validates the stored choice against what the server currently
lists and falls back to self mode when the relationship has gone -- so a
caregiver revoked while the app was closed comes back to their own Nura rather
than to a screen full of 404s.

**`null` and `[]` are different things in a caregiver's home, deliberately.**
The backend omits a section the caregiver was not granted (PRD 9, section 18), so
`optionalList` in the API client keeps `null` as `null` instead of defaulting it
to `[]`. Collapsing the two would turn "you cannot see this" into "there is
nothing here", which is the same leak in the other direction, and the screens
draw no heading at all for an absent section.

**The safety screens are driven by what the build can do, not by what they
were written to assume.** PRD 10 section 64 gives the reason in one line --
*this prevents misleading UI* — so the capability map arrives with the status
and the screens read it. There is no Call control for a call that cannot
happen, and the capability screen says "Not set up in this build" in words
rather than leaving somebody to infer it from a missing button.

**The countdown is text, and it is the server's clock.** Section 118 rules out
an animation as the only indicator and section 28 puts the deadline on the
server, so `secondsUntil` subtracts a server timestamp from now and the screen
renders a sentence. It never decides time is up: the backend does that, and the
maintenance worker does it for somebody who is not looking at all.

**The SOS control is two taps rather than a press-and-hold.** Section 13 allows
either and section 118 asks for an accessible alternative to a hold; a hold has
no equivalent a screen reader can describe or a shaking hand can complete, so
the confirm step *is* the protection. It says what will happen and what will
not, because somebody deciding whether to press it needs to know nobody will be
called.

**Emergency mode minimises the Safety screen rather than navigating away from
it** (section 43). Pushing a route from an effect would mean a screen that
moves under somebody while they are reading it, which is the opposite of what
section 43 asks for.

**There is no offline queue for safety, deliberately.** Every other feature
queues an action taken with no signal. An emergency must not: a queued
emergency request is the one piece of queued work whose delay makes it
worthless, and showing it as sent would be the lie PRD 10 is written against.
Offline shows section 67's sentence and points at the phone's own dialler.

**A caregiver screen cannot grant anything.** `permissions.ts` has section 62's
`canView` / `canUse` helpers and they decide what to *draw*, never what is
allowed: a bug there can hide a section the caregiver may see and cannot reveal
one they may not. The server is authoritative on every request.

**The assistant screens hold no health data of their own.** Every one of them
reads through `features/nura/`, and what comes back is a conversation, a set of
preferences or a list of memories. There is no path from a Nura screen to a
medication row, and the one change Nura can propose is made by a separate
request that a person triggers with Confirm.

**An unsent message is kept; nothing is queued.** `composerStore` persists the
draft per conversation to AsyncStorage, because PRD 8 section 57 asks for a long
message to survive the app backgrounding and section 56 for it to survive being
offline. What is deliberately *not* built is a send queue: a reply comes from a
model the phone cannot reach, section 56 forbids a fake assistant reply, and a
queued message whose answer arrives an hour later out of context is a worse
version of the same problem. The banner says what is saved and what is not.

**A retry answers the question rather than asking it again.** The app mints a
`client_message_id` before the first attempt and keeps it in a ref until a send
comes back with a reply, so the second attempt carries the id the backend
already stored the question under.

**Two more interactive bits of state moved into a store, for the usual
reason.** The Remove confirmation and the suggestion composer's time and pause
both decide what is on screen, and under React 19 a local `useState` update from
a fired event does not re-render -- so neither was testable. Moving them made the
confirmation testable *and* exposed a design problem: two presses of a button
labelled "Remove" gave the user no sign that the first one had done anything. The
confirm step now names the person ("Yes, remove Ayesha") and offers a way out,
which is also what section 77 asks of an approval control.

**Three more small stores, for the reason that keeps recurring.** `composerStore`
(persisted), `editorStore` (the memory and instruction fields) and `listStore`
(whether history shows archived threads) all exist partly because a store update
re-renders under React 19 where a local `useState` update from a fired event does
not — which is what makes a Save button that enables when you type something
testable at all. It is written down in each file rather than rediscovered.

**Every personality control is a three-step choice, not a slider.** Section 23
allows either and asks for one consistent UI; the reason for choosing this one is
section 83. A three-way control has 48dp targets, announces its options and its
selection to a screen reader, works with a shaking hand and reads the same at
every type size. The extra precision of a slider would not change a word of the
prompt it feeds.

**An appointment carries its own time zone, and the server writes the label.**
`scheduled_at` is the instant and `timezone` is where it was arranged, for the
same reason a medication schedule keeps both. What is unusual is that
`when_label` — "Tomorrow at 3:30 PM" — is rendered by the *backend* and sent with
the appointment. Resolving an instant into a named zone needs the IANA database,
and `Intl` with full zone data is not something this app can rely on across both
platforms; doing it on the server also means one implementation of that sentence
rather than one per platform. The consequence is that the mobile app contains no
time-zone arithmetic for appointments at all.

**A report is a frozen snapshot, and the preview renders it.** The backend stores
the finished sentences on the report row, and `ReportPreviewCard` draws those
strings. So what somebody approves on screen and what they export cannot disagree
— and the preview is real text, which reflows at larger sizes, follows Light and
Dark, and can be read by a screen reader, none of which a rasterised PDF page can
do.

**Three more stores, for the two reasons that keep recurring.** The appointment
form draft and the report selection are persisted to AsyncStorage: preparing is
four routes editing one thing and PRD 7 section 32 requires Back to work, and
section 53 asks for drafts to be preserved. Which history list is on screen is a
third, unpersisted, so opening an appointment and coming back does not throw you
out of Past. All three also make their screens testable, because a store update
re-renders under React 19 where a local `useState` update from a fired event does
not.

That last point came with a lesson worth writing down: a press arriving before a
store update has re-rendered reads the state as it was a moment ago. The report
generator therefore reads the selection at press time rather than from the render
closure, and the tests wait for the *control* to show its new state before
pressing the next thing.

**A report is never generated offline, and the app says so.** Everything else in
PRD 7 queues — an appointment typed on a train, a question written in a waiting
room — but a PDF is built by the backend, so there is nothing useful to keep on
the phone. PRD 7 section 53 says plainly not to pretend generation succeeded, so
the screen says Nura needs a connection and that the selections are saved, which
they are.

**A report PDF is downloaded with a token, not a URL.** The same pattern as a
symptom photo: the file comes from the API route with an `Authorization` header,
lands in app-private cache storage, and is handed to the platform's own share
sheet. Each export clears the directory first, so the phone never accumulates a
folder of doctor summaries.

**The provisioning flow is a controller, not a screen.** `ProvisioningFlow`
owns the BLE connection, the verified session and the polling, with Bluetooth
and the API injected — which is what lets the whole flow be tested against a
simulated robot. Screens render its state and call its methods.

**Accessibility** (PRD 2 §57): 48 dp touch targets, labels on every control,
status conveyed by icon and text as well as colour, live regions on progress
and errors, and text that scales with the system setting.

---

## 5. Firmware

`firmware/xiao_esp32s3`, C++ on the Arduino core via PlatformIO.

```text
main.cpp              boot, state machine, button, heartbeat timing
protocol.h            UUIDs, message types, enums, limits  ← shared with the app
board_config.h        which hardware is fitted, and on which pins
device_identity.*     hardware id, prototype bootstrap credential
settings_store.*      NVS: Wi-Fi, backend URL, device token
spake2.*              RFC 9382 role B, over mbedTLS
secure_channel.*      AES-128-GCM Wi-Fi payload
ble_provisioning.*    the GATT service and pairing session
wifi_manager.*        joining, and why it failed
backend_client.*      claim, heartbeat, and PRD 11's three device calls
display.* / audio.*   screen and speaker, or serial when neither is fitted

presentation_protocol.*  the presentation vocabulary  ← shared with app + backend
presentation_manager.*   IDLE → FETCHING → RENDERING → WAITING → ACKING
card_renderer.*          JSON → Card, then dispatch on layout
face_renderer.*          a face state → geometry. Pure, and the one testable piece
display_driver.*         DisplayDriver: Simulated, and Physical behind a flag
audio_output.*           AudioOutput: Silent, and I2S behind a flag
```

Three explicit state machines rather than a pile of booleans: connectivity
(`UNPROVISIONED → CREDENTIALS_RECEIVED → WIFI_CONNECTING → WIFI_CONNECTED →
BACKEND_REGISTERING → ONLINE`, plus `ERROR`), pairing mode, which is orthogonal
— a robot can be online *and* pairing, which is how Wi-Fi is changed — and PRD
11's presentation machine, which section 88 asks to be kept separate from both.
What the robot is *showing* and whether it is *online* are different questions,
and one machine covering both is how a robot ends up stuck on a card because
Wi-Fi dropped.

PRD 11 reused `display.*`, `audio.*` and `backend_client.*` rather than
replacing them, which is section 89: `display.cpp` still owns the panel and
gained `drawEyes`, `drawLines`, `blank` and `setBrightness`, and
`I2SAudioOutput` reuses the I2S driver `audio.cpp` already installs rather than
installing a second one on the same port.

PRD 12 changed the firmware by **one header and one test file**, which was
the point of dispatching on layout rather than on type: its four new card types
reuse `REMINDER` and `STATUS`, so `card_renderer.cpp` needed no edit at all.
`presentation_protocol.h` gained the type names as `TYPE_*` constants -- for a
log line that says what kind of card was handled without quoting its content,
and for the drift test the backend and the app both run against this header --
and `test/test_presentation` gained three tests that parse one of each.

| Build | Purpose | Size |
| ----- | ------- | ---- |
| `xiao_esp32s3` | development; allows a LAN `http://` backend | 32.8% flash, 16.2% RAM |
| `xiao_esp32s3_release` | refuses `http://`, quiet logs | 32.7% flash |
| `xiao_esp32s3_peripherals` | adds the display and audio drivers | 35.2% flash, 16.6% RAM |

**Because the robot does not exist**, the default build assumes a bare XIAO
with nothing attached, and the pairing code goes to the serial log — a
developer fallback, never something a user should be asked to do. The display
driver chip, the amplifier and every pin in `board_config.h` are assumptions
to check against real hardware.

Behaviour worth knowing: first boot advertises until setup completes; a set-up
robot never advertises unless BOOT is held for 3 seconds; BOOT for 10 seconds
is a local factory reset that keeps the device identity and touches nothing in
the cloud; losing Wi-Fi retries every 30 seconds and never unlinks the account.

---

## 6. How a robot joins an account

```text
App ──BLE──▶ Robot     code on the robot's screen proves the right physical unit
App ──HTTPS─▶ Backend  short-lived, single-use provisioning token
App ──BLE──▶ Robot     Wi-Fi details + token, encrypted to the verified session
             Robot ──▶ Backend   claim: token + the robot's own secret
             Robot ──▶ Backend   heartbeat
App ──HTTPS─▶ Backend  "is it online?" ← the only thing that decides success
```

The full wire format is in
[docs/device/provisioning-protocol.md](docs/device/provisioning-protocol.md).
Summary: one GATT service (`3326ea00-822c-4b86-884f-74b2d9c77b2f`) with
characteristics for device info, pairing, Wi-Fi config, commands and status;
the Wi-Fi and command characteristics refuse everything until the session is
verified.

### Why a PAKE, and not just "type the code"

A six-digit code is about 20 bits. Used to derive a key, or to authenticate an
ordinary key exchange, anyone who recorded the exchange could try all million
codes offline in seconds and decrypt the Wi-Fi password.

So the code drives **SPAKE2** (RFC 9382, P256-SHA256-HKDF-HMAC) instead: a
password-authenticated key exchange gives an attacker one guess per online
attempt and nothing to test offline. Matter uses the same approach for
commissioning. The resulting session key encrypts the Wi-Fi payload with
AES-128-GCM, with the hardware id as associated data so a captured payload
cannot be replayed at another robot.

No cryptography is invented. Both implementations are checked against the
RFC's own vectors, and a shared vector pins the TypeScript and C++ sides to
each other. Attempt limits do the rest of the work: three tries per
connection, ten per pairing window, then the robot stops advertising.

Full reasoning, including why Bluetooth's own pairing was rejected, is in
[ADR 0005](docs/decisions/0005-ble-pairing.md).

### Credentials

| Token | Lifetime | Stored as |
| ----- | -------- | --------- |
| Provisioning token | 10 minutes, single use | SHA-256 hash |
| Device token | until the next claim | SHA-256 hash |
| Bootstrap secret | made on first boot, survives factory reset | SHA-256 hash |

The user's own access token never leaves the phone. Nothing in the database
can be turned back into a credential. Never logged anywhere: Wi-Fi passwords,
the pairing code (outside the no-display fallback), SPAKE2 values, any token,
the bootstrap secret.

The bootstrap secret is **trust on first claim** — a prototype stand-in for a
credential written at manufacture. It stops a second board copying a hardware
id from taking over an existing record; it does not prove a never-seen board is
genuine Nura hardware. That needs manufacturing provisioning, which is
deferred.

---

## 7. Testing

| Suite | Count | Runs against |
| ----- | ----- | ------------ |
| Backend (`pytest`) | 1227 | real PostgreSQL, real migrations, genuinely signed ES256 tokens, real PDFs parsed back, a scripted model provider, two real accounts for every caregiver test, the real maintenance worker on a frozen clock |
| Mobile (`jest`) | 1,454 in 130 suites | pure logic, the real Today, Health, medication, symptom, appointment, Nura, caregiver, safety, Nura Device, daily-life and privacy screens, and the flow against a simulated robot |
| Firmware (`pio test`) | 28 in two suites, **never executed** | the ESP32 itself — needs a board |

What the tests actually pin down:

- **Authentication is real.** Tests sign ES256 tokens with a key pair made
  during the run, and the production verifier checks them — covering forged
  signatures, `alg:none`, wrong issuer, wrong audience and expiry.
- **The pairing rules hold.** A claimed robot cannot be silently re-claimed; a
  consumed token cannot be reused by another board; an expired session is
  refused; a copied hardware id is refused; re-provisioning Wi-Fi keeps one
  device record.
- **Success requires evidence.** The flow reports online only after the backend
  confirms a heartbeat since the claim — a test makes the robot claim and then
  go quiet, and the app must not report success.
- **Nothing sensitive goes out early.** The simulated robot counts any Wi-Fi
  payload it receives before verification; the test asserts zero.
- **The two implementations agree.** RFC vectors on both sides, a shared
  cross-implementation vector, and a test that parses the firmware's
  `protocol.h` and fails if any UUID, message type or status code differs from
  the app's.
- **Today works in every state it has to.** Mounted for real: an offline robot
  with its last-seen time, no robot at all, a backend that will not answer, and
  a check-in submitted and shown as recorded. The three connection states are
  produced by the same `last_seen_at` a real robot writes.
- **A check-in cannot be lost or duplicated.** Submitting with no network
  queues it; reconnecting sends it; a stale queued answer does not overwrite a
  newer one; an answer the server would always refuse is dropped rather than
  retried forever. Server-side, one account cannot read or change another
  profile's check-in or layout.
- **Nothing hard-codes a colour.** A test reads every Today, Health and
  medication component and fails on a hex literal, so Dark mode cannot be
  broken by a stray value.
- **Medical records belong to the right person.** Every one of the six record
  types is checked, in both directions: full CRUD for the owner, and 404 on
  every verb for anyone else — including on `POST`, so a stranger cannot even
  add to someone else's profile.
- **A half-remembered date stays half remembered.** "2015" round-trips as a
  year through the form, the request and the database, and sending both a date
  and a year is refused by the API and by a database constraint.
- **The summary leaks nothing.** A test fills a profile with real-looking
  values and asserts none of them appears in the health-summary response.
- **Nothing is deleted silently.** The delete confirmation is asserted: its
  wording, its two buttons, and that no request is made until it is confirmed.
- **8am stays 8am.** The recurrence rules are tested across a real
  daylight-saving change, and both awkward days — a local time that does not
  exist, and one that happens twice — produce exactly one dose. Changing a
  schedule's time zone is asserted not to duplicate a day.
- **A dose cannot be doubled or lost.** Taken twice leaves one taken dose and
  one supply decrement; a dose taken hours late keeps the same row; an offline
  action is queued, replayed, and refused if a newer answer exists.
- **A robot cannot reach what is not its own.** The device route is exercised
  with a real device token: it records `robot_voice`, it never overrides what
  the person recorded, another account's device gets 404, a device with no
  profile gets 404, and a user's token gets 401.
- **The copy is asserted, not just written.** Missed-dose wording carries no
  guilt language, the adherence sentence never grades the figure, and the only
  sentence approaching advice points at a clinician. For symptoms, a test reads
  every sentence Nura can say and fails on a named condition, a likelihood, an
  attribution of cause or an instruction about medication. For appointments there
  are two more of these: one over every sentence the screens can say, and one over
  every string a *generated report* can contain, appendix included — both failing
  on a diagnosis, a likelihood, a cause, a treatment suggestion, a graded
  adherence figure or an emergency framing.
- **A report is immutable, and that is checked two ways.** A symptom entry is
  edited after a report is generated, and the stored report is re-read unchanged.
  Then the stored snapshot is re-rendered and the bytes are compared with the
  stored PDF: identical. That is what makes "regenerate v1" mean the file that was
  already sent rather than a new one that says the same thing.
- **The PDF is read back, not assumed.** `pypdf` extracts the text: the summary
  starts on page 1, the appendix appears only when it was enabled and begins on
  page 2, the expected headings are there, an excluded section is not, an unticked
  symptom is not, and accented characters survive while an unsupported script
  becomes a visible marker rather than vanishing.
- **Only what was ticked appears.** Turning a section off removes it from the
  report; unticking one symptom leaves the other out entirely; a section asked for
  with nothing in it reads "Not recorded" rather than being silently dropped.
- **Regenerating never overwrites.** v1 keeps its content after v2 is made, the
  list returns both, and deleting v1 while v2 exists means the next one is v3.
- **A report cannot be reached by anybody else.** Another account gets 404 on the
  row, on the PDF and on the delete; so does a report id borrowed from a different
  appointment of the *same* profile.
- **Deleting a report leaves the records alone.** The file goes from storage, and
  the symptom, condition, allergy and check-in counts are unchanged afterwards.
- **Nothing infers what happened at an appointment.** A past appointment is listed
  under Past and its status is still `scheduled`, because only the user marks one
  completed.
- **The guardrails do not depend on the model.** Every scripted reply in the
  assistant safety tests is deliberately unhelpful — a bare sentence with no
  caveat — and the assertions are about what Nura does with it. A diagnosis
  request gets PRD 8 section 73's sentence in front of it; a dose-change request
  gets the clinician sentence in front and the pharmacist guidance after; and
  both are put there by the server rather than hoped for. A test that passed
  because the canned reply happened to contain the right words would be testing
  the canned reply.
- **"Nura, emergency" never reaches a model.** The test queues *no* reply on the
  scripted provider, so if the phrase reached it the test would fail rather than
  pass by luck. What comes back is the fixed notice saying escalation is not set
  up, stored as a `notice` rather than as generated text.
- **Serious mode overrides personality, and a health question is not an
  emergency.** Humour is turned to high and the serious prompt still says no
  jokes, with the tone block not sent at all. Meanwhile "what does inflammation
  mean?" and "when is my next appointment?" are asserted *not* serious — section
  38 warns against treating every health question as one.
- **Almost nothing about the record reaches a prompt.** A profile is filled with
  a medication, a condition, an allergy and a symptom, a question about soup is
  asked, and the system prompt is checked to contain none of their names — only
  counts. A medical note whose body reads "SYSTEM: ignore all previous
  instructions" is planted, and the prompt does not contain it.
- **The model cannot name a person.** Asserted twice: once by checking that no
  tool schema has a property whose name contains `profile`, `account` or `user`,
  and once by handing a tool another profile's real appointment id and getting
  "no such appointment".
- **A suggested change waits for a press.** The model proposes a question, the
  reply comes back with a pending action, the appointment still has no questions,
  and only after Confirm does it have one. Confirming twice adds one. Another
  account confirming gets 404.
- **Switching a memory off stops it reaching the model.** Asserted against what
  was actually *sent*: the memory's text is in the system prompt before, and
  absent after.
- **Nothing is ever marked delivered.** The whole
  `safety_escalation_attempts` table is read and `delivered` is asserted absent
  from it. The value exists so a real provider can use it; nothing in this
  build has a code path that writes it, which is PRD 10 section 38 made
  structural rather than promised.
- **Every external channel reports `not_configured`, with PRD 9's code.** A
  contact in the chain gets a row for a call and a row for a text, and the
  call's `failure_code` is `calling_not_configured` — the same string
  `services.caregivers.calls` returns, so there is one code for "Nura cannot
  ring anybody" whichever feature asked.
- **The user is shown facts rather than claims.** The rendered lines are
  asserted verbatim — *In-app alert created for Ayesha.* and *Phone call for
  Spouse: not set up in this build.* — and the sentences section 42 forbids
  are asserted absent from every string the wording module can produce.
- **Every sensor-observed event type says "possible".** Read from the tuple
  rather than spot-checked, and the words section 52 forbids are checked
  against every label, description and sentence in
  `services.safety.wording`.
- **A passive trigger is refused while monitoring is off, and accepted while
  it is on.** Sections 21 and 22 as a pair, through the real device-trigger
  route with a real device token and no hardware anywhere.
- **The timeout really escalates, through the real worker.** `pytest` runs
  `scripts/safety_maintenance.py` against the real database with the clock
  moved rather than slept through (section 82), and a second run is asserted
  to change nothing. Section 80 says not to claim timing works if the worker
  has never run; it runs here.
- **The second prompt costs exactly twenty seconds.** 45 seconds, a second
  prompt, 20 more, then escalation — asserted step by step, because section 8
  asks for the timing to be documented and a document can drift from code.
- **Answering first stops escalation entirely**, and answering late does not
  rewrite history: the alerts stay, the unsent attempts become `skipped`, and
  the trail records that the answer was late (sections 76 and 126).
- **A revoked permission stops new alerts and keeps the old ones.** Both
  halves of section 86, because deleting evidence of what the system did is
  not a retention policy.
- **A caregiver with every category granted still gets 404 from every safety
  route the owner uses.** Their whole view is the alert list (section 50).
- **An alert carries no health data**, checked with a real medication and a
  real symptom on the record — so it is not passing because the record is
  empty.
- **No assistant tool can invent a sensor event.** Every argument model in the
  registry is checked for `event_type`, `trigger_source` and `confidence`, and
  none has any (section 57).
- **A caregiver cannot start monitoring through the assistant** — not in the
  tool list, and refused if named anyway (section 58).
- **The recording provider is unreachable from configuration.** Section 110
  allows one in tests and forbids representing it as production delivery, so
  every plausible setting value (`recording`, `mock`, `test`, `log`, `fake`) is
  asserted to be refused by `build_notification_provider`.
- **Fetching a presentation does not mark it displayed**, and the *database*
  refuses one that tries. One test takes the service's word for it; another
  writes straight past the service with raw SQL and asserts an
  `IntegrityError`. That second test is what found the constraint accepting
  exactly the row it exists to refuse, because a SQL `CHECK` passes when it
  evaluates to null (PRD 11, sections 14 and 141).
- **Only safety preempts, and a queued card is never thrown away.** Section
  17's own example is a test — a family message on the screen, an SOS, the
  message cancelled as `preempted` — and so is its converse: a medication
  reminder arriving does *not* cancel a message nobody has read.
- **An acknowledgement cannot go backwards, and repeating one is free.**
  Section 123's valid and invalid transitions, including a device reporting a
  render for something it was never sent (409) and a free-text failure reason
  (422, because section 67 allows a stable code or nothing).
- **A device can only touch its own presentations.** A second real account with
  a second real robot gets the same 404 a non-existent id gets, so a robot
  trying ids learns nothing.
- **A taken dose loses its card, and a snoozed one gets a new one.** Nothing
  notified the robot: the next reconciliation asked the dose again. The snooze
  case is in the dedupe key, and the test that found the flaw is the one that
  caught two cards for one tablet.
- **The private medication preview is the default, and Privacy Mode overrides
  a full one.** Both through the real preference endpoint and the real dose,
  with the tablet's name asserted absent from the stored payload — so the
  app's own history cannot show it either (sections 22 and 33).
- **A withdrawn `communication` permission stops new message cards and
  withdraws waiting ones, and the message survives.** PRD 10 section 86's
  lesson applied to PRD 9's permissions, with PRD 9's own route doing the
  revoking.
- **An emergency card is PRD 10's answer, not a summary of it.** The caregiver
  is named because an alert record exists, calling is reported as not
  configured because no provider does, and "help is on the way" is asserted
  absent — over every string in the wording module and every sentence it can
  generate at its edges.
- **Drawing a screen never advances a safety deadline.** The robot's
  reconciliation uses `monitoring.peek_session`, and a test moves the clock
  past a session's end, reconciles, and asserts the session is still active —
  because a display request that expired somebody's monitoring would make the
  presentation path load-bearing for safety (section 100).
- **No assistant reply is queued during an emergency**, and the priority table
  says it could not have outranked one anyway (sections 72 and 128).
- **Nothing in PRD 5 to PRD 10 imports the robot package.** A test walks every
  file under `app/services` and asserts exactly one exception — the assistant,
  because a reply is an utterance rather than a state. That is the
  architectural claim of PRD 11 checked rather than asserted in prose.
- **A completion cannot be undone by an edit.** A task is completed, then a
  stale title edit arrives from another device carrying an older
  `client_updated_at`, and the task is still complete -- section 40's named
  failure, done rather than described. The route has no way to send a status
  with an edit, so the test is about the clock rather than about validation.
- **The recurrence engine is PRD 5's, and that is asserted by identity.** A
  test compares `services.productivity.recurrence`'s resolver with
  `services.medications.doses.occurrence_instant` and fails if they are not the
  *same function object* -- so a reminder and a dose cannot drift apart on the
  two awkward days a year, and nobody can "fix" one of them in isolation.
- **A missing time is a question.** `CreateReminderArgs.time` is required, so
  "remind me later" fails validation before the function runs and the model is
  told why. A test asserts no default time, date or weekday exists anywhere.
- **The three external capabilities cannot be switched on by configuration.** A
  test sets `WEATHER_PROVIDER=openweather`, `NEWS_PROVIDER` and
  `CALENDAR_PROVIDER`, and all three still read `not_configured` -- with a
  warning logged. `build_provider` raises for every name, and `IMPLEMENTED` is
  empty, so a misconfigured deployment gets an honest refusal rather than a
  feature that sometimes answers.
- **The medical boundary is not reachable through a daily-life tool.** "Remind
  me to double my dose tomorrow" writes the reminder *and* returns
  `MEDICATION_CHANGE_BOUNDARY`; "pick up my medication" does not, because the
  check needs a change verb as well as a medication noun and `up` is
  deliberately not a change verb. The person's own active medication names
  count as the noun, since no fixed list holds every drug name.
- **Section 42 is walked rather than argued.** A caregiver is granted every
  category, including `routines`, and then every owner daily-life route is
  requested: 404 from each. The suggestion registry is asserted to have no
  action type for a task, an alarm or a personal reminder, and the caregiver's
  assistant is asserted to see exactly two routine read tools and no write.
- **An alarm list without its limitation is refused by the client.** The server
  sends section 11's sentence with every list and the parser requires it, so a
  response that drops it is an error rather than a quietly silent screen.
- **Monthly on the 31st lands on the last day of a short month**, and a routine
  whose time has already passed still gets today's run -- the one place PRD 12
  departs from PRD 5's generator deliberately, because a run covers a day and a
  dose covers a moment.
- **The firmware needed no parser change, and that is checked three ways.** The
  backend and the app both compare PRD 12's four type names against
  `presentation_protocol.h`, and the firmware's own Unity tests parse a task
  card as a `REMINDER`, a routine card as a `STATUS`, and assert an alarm card
  carries no chime -- because the robot cannot sound one.
- **Every owner route is walked with the wrong caller.** Not a list of paths --
  the application is asked. `test_security_matrix.py` walks the router tree,
  resolves each route's dependency graph, classifies it by which authorization
  dependency it reaches, and then requests all 169 owner routes as a second
  owner and as a caregiver holding every permission. 404 from every one. A
  route PRD 14 adds is in those loops the day it is written, which is the whole
  reason the file exists: PRD 9 walked eight hand-typed paths, and PRD 10 and
  PRD 12 each had to add their own because the first could not know about them.
- **And the walk is checked against the published schema.** The assertion that
  makes the rest mean anything. A path the walk gets wrong does not exist, so
  every request against it answers 404, and a suite asserting "the wrong caller
  gets 404" passes for routes it never reached. That was true for nine
  health-record routes nested two routers deep until the check was added.
- **The caregiver-reachable surface is thirteen routes of 218, asserted by
  equality.** Each with a stated purpose, so a fourteenth fails the suite until
  somebody writes down what it is for -- and a route that stops being reachable
  fails too.
- **Deletion is asserted on the files, not the rows.** 68 foreign keys cascade
  from a profile and none can reach object storage, so the test stores a photo
  and an export archive, deletes the profile, and asserts `store.get` raises
  for both. PRD 14 section 56 lists "deletion leaves accessible private files"
  as a release blocker; this is the test that would catch it.
- **An export's contents are classified column by column, against the live
  metadata.** For every table: exported plus excluded is exactly the column
  set. A column a later PRD adds is unclassified, and unclassified fails -- so
  a schema change cannot ship until somebody has decided which side of the line
  each column falls on.
- **Eleven classes of sensitive content are asserted absent from the logs.** A
  capture handler on the whole `app` logger tree at `DEBUG`, one write per
  domain driven through the real HTTP routes. Two traps were worth recording:
  Alembic's `fileConfig` disables every application logger for the session, and
  `disabled` is set per logger object -- so clearing it on `app` leaves the
  children silent, a capture handler records nothing, and every "this is
  absent" assertion passes while proving nothing. The suite asserts something
  *was* logged alongside what was not.
- **Both hand-maintained lists have a drift test that reads the source.**
  Every `queryKey` literal and every `'nura...'` storage key in the mobile
  source must be classified -- and the reverse, that every key in a list is
  actually declared somewhere. The reverse direction is what caught
  `health-summary`, which had been in the clear list for four PRDs and matched
  nothing.
- **The whole manual test plan runs without hardware.** Section 132's eighteen
  steps, in order, driven by a simulated robot that reports capabilities,
  reconciles, fetches, renders to text and acknowledges through the same
  services the HTTP endpoints call. Section 140 asks whether every workflow can
  run in the simulator; this test is the evidence.
- **The three sides agree on the protocol.** The backend and the app both parse
  `presentation_protocol.h` and compare every layout, face state,
  acknowledgement, capability, state, failure code and text limit against their
  own. A drift fails on a laptop rather than on a bench.
- **The robot's copy claims nothing.** Two exhaustive audits — one over the
  server's wording module, one over the app's — assert that nothing says help
  is coming, nothing describes a detector, nothing claims the robot showed,
  spoke or played anything, and every future-capability sentence says *when*
  rather than *now* (sections 8, 9, 20 and 49).
- **A caregiver cannot reach a single route written before PRD 9.** The most
  important test in the suite: a caregiver is granted *every* category and then
  eight PRD 0-8 endpoints are walked -- the health summary, medications,
  conditions, symptoms, appointments, schedules, assistant conversations and
  assistant memories -- expecting 404 from each. Those routes authorize through
  `account_profile_roles`, which a caregiver has no row in.
- **A hidden category is absent, not empty, with real data behind it.** A symptom
  is recorded and the caregiver's home is asserted *byte-identical* to the one
  they got before it existed. PRD 9 section 18 is about metadata as much as
  records: a count is information.
- **A role grants nothing.** `family` becomes `primary_caregiver` -- the most
  senior-sounding value there is -- and the granted set is identical before and
  after. `emergency_contact` as a role is tested separately, because the name
  invites the opposite assumption.
- **Revocation is immediate, and the word is taken literally.** The same GET that
  worked on one line answers 404 on the next, with nothing invalidated in
  between, because `granted_keys` returns an empty set for a relationship that is
  not active and every request reads the row.
- **A forbidden change cannot be asked for.** `change_medication_dose`,
  `delete_condition` and `change_diagnosis` are each posted and each refused at
  422 by the schema's Literal, before any caregiver code runs.
- **Approval re-checks the permission against the present.** The caregiver is
  revoked *between* proposing and approving, and the approval is refused with the
  schedule unchanged. A second test withdraws only the category, leaving the
  relationship active, and gets the same answer.
- **Approving twice applies once**, proved with `add_appointment` where a second
  application would be visible as a second appointment.
- **A caregiver sees only their own suggestions**, and cannot cancel another's.
- **Emergency contacts are owner-only at every verb.** A caregiver with every
  category granted gets 404 on get, post, patch, delete and reorder, and a
  follow-up test confirms the owner's contact survived every attempt.
- **Nothing contacts anybody.** `contacts.py`'s public surface is asserted to be
  six read-and-write functions and nothing else, and it is checked to import no
  module that could reach a phone or an inbox.
- **Calling is refused, never simulated.** The route answers 503, the provider's
  abstract methods are asserted to be exactly section 39's five, their parameters
  are asserted to be Nura concepts only, and no model name contains `Call`.
- **No assistant tool can read a family message.** Checked across the whole tool
  layer by absence: no tool name or argument contains `thread`, `message`,
  `family` or `check_in`, so section 65 has nothing to opt out of.
- **Every provider failure becomes one sentence.** Timeout, rate limit,
  authentication, 5xx, connection error and a refusal are each translated and
  checked, and no failure sentence anywhere names a provider, a model, a status
  code or a token.
- **The guided conversation does not repeat itself.** PRD 6 section 28's own
  example sentence is fed to the engine, and the test asserts that the symptom,
  the site, the character, the onset and the severity are all captured and none of
  them is asked about. A separate test drives the whole flow skipping every
  question and asserts no question is offered twice.
- **A hedge is not a fact, and a denial is not a symptom.** "No nausea" lands in
  `negated_items`; "I might have felt dizzy" lands in `uncertain_items`; "I'm not
  sure if it spreads" is not read as a denial. Both suppress a safety rule even
  when the rules are switched on for the test.
- **Severity 10 on its own is not an emergency.** Asserted directly, because PRD 6
  section 78 rules it out and it would be an easy thing to add later by accident.
- **The urgent rules are off, and work when turned on.** One test asserts a
  confirmed red-flag phrase produces only the generic notice in the shipped
  configuration; another enables the setting and asserts the rule fires. So the
  architecture is real and the default is inert.
- **A symptom cannot be duplicated by a retry.** The same `client_entry_id` sent
  twice produces one entry and a `created: false`, and a replay does not overwrite
  the stored values. The same is asserted for creating an episode and for
  uploading a photo.
- **A symptom saved offline keeps everything.** The description, the structured
  fields and the local photo files are all still on the device, and a photo that
  fails after the description landed is kept against the entry it belongs to
  rather than re-creating the episode.
- **A photo is private, and is really deleted.** The upload response carries no
  storage key; the content route serves the bytes to the owner and 404s for
  everybody else; deleting removes the file from storage as well as the row, and
  deleting an entry or an episode purges the objects under it.
- **A mislabelled upload is refused.** A text file declared as a PNG, and a PNG
  declared as a JPEG, are both rejected on the bytes rather than the label.
- **Symptoms do not move the completeness figure.** Logging one leaves the health
  profile's percentage and its seven sections exactly as they were.
- **A symptom that came back is a separate bout.** The recurrence is a new episode
  with a link to the old one, the old one keeps its own resolution and entries, and
  asking for a recurrence of an ongoing symptom is refused.

Also clean: `tsc`, ESLint, Prettier, Ruff, mypy.

**Known gap:** no notification has ever been delivered by a phone —
`expo-notifications` is replaced by a recording stub, so what is proven is
which reminders the service decides to schedule and cancel, not that the OS
fires them.

**Known gap:** no symptom photo has ever been chosen on a phone.
`expo-image-picker` and `expo-image-manipulator` have no implementation under
Jest, so the picking, the compression and the permission prompts are untested.
Everything downstream of them — the upload, the type sniffing, the authorization,
the deletion, the offline queue — is tested with real bytes.

**Known gap:** nothing has ever reached a person outside the app, and no
detector has ever produced a reading. PRD 10's authorization, state machine,
deadlines, escalation policy and capability model are tested against a real
database, and the maintenance worker runs for real on a frozen clock. What none
of that covers: no push notification has been delivered, no text message sent
and no call placed, because no provider exists; no fall, immobility,
seizure-like or vomiting detector exists and **none has been clinically
validated**; no hardware has called the device-trigger route; the safety screens
have never run on a phone; and timely escalation depends on
`scripts/safety_maintenance.py` being scheduled, which nothing in this
repository does.

**Known gap:** no caregiver has ever used this on a phone, and nothing has ever
been delivered. The authorization is tested against a real database with two real
accounts holding two genuinely signed tokens, and a full flow -- invite, accept,
read, propose, approve, message, reorder, revoke -- was printed and read line by
line against the dev database. What none of that covers: no invitation has been
*sent*, because Nura has no way to send one and says so; no notification has
reached a phone, because there is no push for a family message or a care request;
and no audio call has been placed, because no provider is configured and section
38 forbids pretending otherwise.

**Known gap:** Nura has never spoken to a real model. The Anthropic adapter is
exercised offline in `tests/test_assistant_provider.py` with its HTTP client
replaced by a recorder: the request it builds, the beta and fallback parameters,
that the streaming helper is used, how each SDK exception is translated, and how
a reply — including a refusal and a malformed tool call — is read back. What that
cannot prove is that Anthropic accepts any of it. There is no API key in this
environment and the whole suite runs against `ScriptedProvider`, which is what
PRD 8 section 101 asks for. The deterministic half of the safety work is
provider-independent and would behave identically against any model; the prompt
half has never been evaluated against one.

**Known gap:** no report PDF has ever been shared from a phone. The document is
genuinely generated and parsed back by the backend tests, but `expo-file-system`
and `expo-sharing` have no implementation under Jest, so the download and the
share sheet are exercised against recording stubs. What those do prove is the
decisions: the authenticated URL and header, the app-private cache location, the
cleanup of earlier exports, the safe filename, and that a platform with no share
sheet is reported as "saved to this phone" rather than as a failure.

**Known gap:** no notification and no alarm has ever fired. PRD 12's reminder
and alarm scheduling is tested against a recording stub -- what it schedules,
what it says, what it cancels when a reminder, an alarm or a routine changes,
and what it does when permission is refused -- and `expo-notifications` has
never run on a device. **No alarm has fired, no vibration has been felt and no
operating-system background behaviour has been observed.** That is why the
server sends section 11's limitation sentence with every alarm list and the app
refuses a list without it: the honest sentence is in the product rather than
only in this file.

**Known gap:** nothing external is configured, and the code cannot be
configured into pretending otherwise. No weather provider, no news provider, no
external calendar. The three settings exist, `providers.IMPLEMENTED` is empty
for all three keys, `build_provider` raises for every name, and a deployment
that names one logs a warning and still answers `not_configured`. A test proves
that by setting all three. **No forecast, headline or external calendar event
has ever been fetched by this repository.**

**Known gap:** there is no penetration test and no compliance certification.
PRD 13 added a cross-boundary security suite, cache-isolation and
sensitive-logging regressions, and a private-media denial walk. All of that is
evidence about the boundaries this code enforces, checked against a real
database with real tokens. None of it is an audit, and nothing in this
repository claims HIPAA, FDA, ISO or SOC 2 anything.

**Known gap:** deletion cannot re-authenticate, and says so. Nura verifies
Supabase tokens against a JWKS endpoint and never receives a password, so there
is nothing to check one against. The flow uses three deliberate steps and an
exact phrase instead, and the screen states the limitation: anybody holding an
unlocked phone with a live session can complete it. PRD 13 section 44
anticipates this and asks for exactly that -- strong explicit confirmation plus
a documented limitation.

**Known gap:** interactions that only move a screen's *local* state have no
tests. Under React 19 + RNTL 14, a local `useState` does not re-render in Jest
— a three-line component with no router behaves the same way. So: submitting a
check-in is tested (it travels through TanStack Query, which does re-render),
but pressing **Change** to reopen the chooser, typing a note, and the show/hide
and reorder controls on Customize Today are not. The logic behind each of them
is tested directly, and every rule they depend on is covered server-side.

PRD 6 works around this rather than living with it: the symptom draft and the
conversation are in a Zustand store, which does re-render, so **the symptom form
is driven the way a user drives it — typing included** and the conversation is
advanced turn by turn on a real screen. The one thing still out of reach there is
the conversation's own text box, which holds its draft message in local state; the
function the Send button calls is exercised directly instead.

The same limitation also caught a genuine bug worth recording: a press that
arrives before a store update has re-rendered lands on a button still drawn as
disabled and correctly does nothing. Tests now wait for the *button* to become
enabled rather than for the store, which is what a person does anyway.

**A note on component-level tests.** React Native Testing Library's bare `render`
does not return usable queries under this project's React 19 pairing, and its
`screen` is not populated by it either. Everything is therefore driven through
`renderRouter`, on real screens — which is a better test, and the reason the
accessibility assertions for the severity and change-state controls live on
`/symptoms/log` rather than in isolation.

---

## 8. Running it

Full instructions are in the [README](README.md); the short version:

```bash
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd mobile && npm start
```

```bash
cd firmware/xiao_esp32s3 && ../.venv/Scripts/pio run -e xiao_esp32s3
```

One job a deployment has to schedule itself:

```bash
cd backend && python -m scripts.safety_maintenance
```

Once a minute, from cron or whatever the deployment already has. It is
idempotent, and it is what makes a safety timeout *timely* for somebody who is
not looking at their phone. Without it the state is still correct — every read
acts on a passed deadline — but escalation happens on the next read rather than
on time. **Nothing in this repository schedules it**, which is PRD 10 section
80's distinction stated as a limit rather than discovered later. The medication
job (`python -m scripts.medication_maintenance`, hourly) is the other one.

A third exists and is **optional**, which is worth saying because the first two
are not:

```bash
cd backend && python -m scripts.robot_maintenance
```

Presentation expiry is applied on every read path — the robot's fetch, the
heartbeat, the app's status read, the history endpoint — so a card is never
handed over late whether or not this has run. It keeps the table tidy, so a
robot unplugged a month ago does not leave the history screen and the
queue-depth diagnostic reading as though something is waiting.

Two things that catch people out:

- **Bluetooth does not work in Expo Go.** Pairing needs a development build:
  `npx expo run:android`, which first needs the Android SDK installed through
  Android Studio's setup wizard (a GUI step that cannot be scripted).
- **Sign-in needs Supabase credentials**, which are still blank in
  `mobile/.env` and `backend/.env`. Without them the app says authentication is
  not configured rather than pretending.

---

## 9. What is left

**Blocked on hardware that does not exist**

1. Build the robot, then confirm the display driver chip, the amplifier and the
   wiring, and correct `board_config.h` before the first flash.
2. Flash it, run the firmware tests on the board — both suites; PRD 11's
   presentation tests compile for the target and have never executed, because
   PlatformIO's Unity tests run on the device — and follow the pairing
   procedure in README section 7: discovery, verification, Wi-Fi, claim,
   heartbeat, reboot persistence, Wi-Fi change.
3. Then validate the display and the audio *separately*, which PRD 11 sections
   93 and 94 ask for and which nothing in software can stand in for: panel
   init, text rendering, a frame update, brightness, then the amplifier, the
   speaker, volume and a chime. Only after a person has seen a legible frame
   may the firmware report `display: available` instead of `not_verified`.

**Blocked on a phone, not on the robot**

4. Build the Android development build (`npx expo run:android`), which first
   needs the Android SDK from Android Studio’s setup wizard.
5. Walk through Today by hand: each wellbeing option, editing an answer, adding
   and clearing a note, a restart, airplane mode and back, Light/Dark/System,
   larger text, a screen reader on the check-in controls, reordering and hiding
   cards, and pull-to-refresh. None of this needs the robot — the connection
   states come from `scripts/seed_dev.py`.
6. Walk through Health by hand: start setup, skip sections, come back to the
   resume point, add and edit and remove a record of each type, set and change
   a blood type, turn airplane mode on mid-form and confirm what you typed
   survives, then check the screen reader on the form fields and the delete
   confirmation.
7. Walk through medications by hand, which is the one area with something a
   simulator cannot prove: create a daily schedule and a multiple-time one,
   confirm a real notification arrives, mark Taken from the notification's
   screen, Snooze, Skip with and without a reason, go offline and record a
   dose then reconnect, edit a schedule and confirm history survives, pause
   and resume, mark a medication inactive, enable refill tracking and watch
   the count fall only on Taken, restart the app and confirm the reminders
   rebuild, then check Light/Dark/System, larger text and the screen reader on
   the dose buttons. `scripts/seed_dev.py --medications demo` sets up every
   state worth looking at.
8. Walk through symptoms by hand: log one manually and one through Talk to Nura,
   volunteer several fields in the first message and confirm nothing is asked
   again, leave the irrelevant fields blank, edit something on the review screen,
   save, add a follow-up, mark worsening and then improving, resolve it, record a
   recurrence, attach a photo from the camera and from the library, confirm the
   permission prompts read sensibly and that declining still lets the symptom
   save, remove a photo, go offline and create a symptom with a photo then
   reconnect, and check Light/Dark/System, larger text and the screen reader on the
   severity scale and the conversation bubbles.
   `scripts/seed_dev.py --symptoms demo` sets up every state worth looking at
   except the offline one, which only exists on a phone.
9. Walk through appointments by hand: add one with only a name, a date and a
   time, then one with a clinician and a place; confirm the time reads correctly
   after changing the phone's zone; edit it and confirm a real reminder arrives a
   day and two hours before; cancel one and confirm the reminders stop; mark one
   completed with a note and a follow-up date; add and reorder and delete
   questions; accept a suggested one; go offline and add an appointment and a
   question, then reconnect and watch both sync; run Prepare, move the period,
   untick a symptom and a medication, tick a note, turn the appendix on, generate,
   read the preview, share the PDF and open it somewhere else; regenerate and
   confirm the earlier version is still there; delete a version and confirm the
   records are not; and check Light/Dark/System, larger text and the screen reader
   on the selection checkboxes and the preview.
   `scripts/seed_dev.py --appointments demo` sets up every state worth looking at
   except the offline one.
10. Walk through Nura by hand, which needs a real `AI_API_KEY` and is the one
   area where nothing in this repository has ever touched the real thing: open
   the Nura tab, start a conversation, ask a general health question, ask for a
   diagnosis and read the boundary, ask to change a medication and read the
   boundary, ask for a Today summary, ask for recent symptoms, ask for the next
   appointment, ask to add a question and confirm the write, change the
   personality preset, move a dial, add a custom instruction, try one that
   should be refused, create and remove a memory, switch Privacy mode on, say
   something that should trigger serious mode, say "Nura, emergency" and check
   the notice, go offline and confirm the draft survives, then check
   Light/Dark/System, larger text and the screen reader on the chat bubbles and
   the Confirm card. `scripts/seed_dev.py --assistant demo` fills the history
   without a model call.

11. Walk through caregivers by hand, which needs two accounts and is the one
    area where the thing being tested is whether a *person* understands what they
    are granting: invite somebody, read the link sentence and notice Nura does
    not send it, pass the link to the second account, read both lists on the
    acceptance screen and accept; switch into Caregiver Mode and confirm the
    categories you did not grant are not merely empty but absent; grant symptoms
    and watch them appear; suggest a reminder change and approve it from the
    first account, then check the schedule really moved; decline one with a note
    and confirm the caregiver never sees the note; exchange messages and
    check-ins both ways and confirm the read marks behave; go offline mid-message
    and confirm the draft is kept and the app says it has not been sent; add
    three emergency contacts and reorder them; press whatever would be a Call
    control and confirm there is not one; revoke the caregiver and confirm the
    second account's screens stop working immediately while the conversation
    survives; and check Light/Dark/System, larger text and the screen reader on
    the permission toggles and the Approve control.
    `scripts/seed_dev.py --caregivers demo` sets up everything except the offline
    part and prints the invitation links; `--caregivers multi` adds a second
    supported person.

12. Walk through safety by hand, which is the one area where the thing being
    tested is whether somebody *believes the right thing*: start monitoring for
    thirty minutes and read the sentence saying nothing is actually watching;
    simulate a possible fall with the harness and answer "I'm okay", then
    confirm nothing was sent; simulate again and answer "I need help", then
    read the escalation list line by line and check that the ones saying a
    channel is not set up are as prominent as the one that worked; let a third
    one run out without answering and confirm escalation happened anyway; press
    Ask for help with monitoring off and confirm the second tap is what sends
    it; cancel one and confirm the alert that already exists is still there;
    mark a finished event a false alarm and then not a false alarm; grant a
    caregiver safety alerts on a second account and read the alert from their
    side, then acknowledge it and confirm the first account's event is
    unchanged; revoke the permission and confirm the next event produces no
    alert; turn airplane mode on and press Ask for help, and confirm the app
    says it cannot record one rather than appearing to; and check
    Light/Dark/System, larger text and the screen reader on the countdown, the
    SOS confirm step and the capability list.
    `scripts/seed_dev.py --safety …` reaches every state except the offline
    one, and prints the `curl` for the device-trigger contract.

13. Walk through Nura Device by hand, where the thing being tested is again
    whether somebody *believes the right thing*: open More → Nura Device with
    no robot and confirm it explains itself rather than showing dead controls;
    seed one with `--robot online` and confirm the mode, the queue depth and
    the hardware note; change the brightness and confirm it is the server's
    answer that moves, not the screen; set reduced motion to On, then Off, then
    back to Follow, and confirm the third is a distinct state and says so; set
    the medication preview to Full details, then put Nura in Privacy Mode and
    confirm a reminder goes back to "Reminder due"; open the capability list and
    confirm all twelve parts are named with a state in words; seed
    `--robot unverified` and confirm the screen says "Not tested yet" rather
    than rounding it up; seed `--robot headless` and confirm a reminder is
    recorded as not supported rather than vanishing; open the history and
    confirm a card the backend sent reads "sent to Nura" and not "shown"; open
    the preview and confirm it says Preview only before the cards; and check
    Light/Dark/System, larger text and a screen reader on the level controls,
    the three reduced-motion options and the capability rows.
    `scripts/robot_simulator.py plan` walks the same ground from a terminal and
    prints the lines a person would read off the screen at each step.
14. Walk through daily life by hand, which is the one area with two things no
    test in this repository can stand in for — whether an alarm wakes anybody,
    and whether a notification arrives at all. Open More → Tasks & routines on
    an empty account and confirm it reads as calm rather than broken; add a task
    with no due date, one due today and one overdue, complete one and undo it;
    set a daily reminder and confirm the notification arrives, then complete it
    from the app and confirm the next one is still scheduled; snooze one three
    times and confirm the fourth is refused while Done and Dismiss stay; set an
    alarm for two minutes away, **lock the phone**, and see whether it sounds —
    this is the step everything in this PRD's completion report defers to;
    turn Nura's notifications off at the OS level and confirm the banner
    appears and the reminder still exists; build a three-step routine, tick two
    steps, kill the app, reopen it and confirm the progress is there; go
    offline, complete a task and tick a step, reconnect and confirm neither
    duplicated; ask Nura "remind me to call the pharmacy at four" and confirm it
    happens, "remind me later" and confirm it asks which time, "remind me to
    double my dose" and confirm it writes the note and says it cannot change a
    medication, and "what is the weather" and confirm it says weather is not
    configured in this build; open What Nura can reach and confirm the three
    external rows say so in words. `scripts/seed_dev.py --daily-life demo`
    sets up every state worth looking at, and `--daily-life busy` fills Today.

**Deferred by choice** (documented, not started): delivering the daily
check-in reminder — the preference is recorded, and the notification service
PRD 5 built is where it will eventually be scheduled; every-N-hours medication
schedules, which PRD 5 permits only if the recurrence is reliable and well
tested; the privacy option that hides medication names on a lock screen — the
reminder body is built so it is a flag rather than a rewrite; filtering
history by medication in the UI, which the API already supports; the spoken
introduction clip — a chime stands in for "Hi. I'm Nura."; a CA bundle so the
robot can use HTTPS; ownership transfer and release; QR-code pairing fallback;
profile photo upload; account-linking UI; the animated face; translations.

PRD 6 adds three of its own. **The urgent-care safety rules are written, tested
and switched off** until a clinician has reviewed the rule set and its wording;
PRD 6 section 44 asks for exactly that, and turning them on is a clinical decision.
**Flagging a symptom for follow-up** is the one Important Today input from section
40 not implemented — the other two, an explicit worsening and a confirmed severity
increase, are — because there is no flagging control in PRD 6's screen list and an
episode marked worsening already surfaces. And **the Health timeline** that section
79 offers as optional is not started: symptom history lives on the symptom screens,
and a cross-feature timeline is its own piece of work.

PRD 7 adds four. **Symptom photos are not put in reports** — section 28 permits
deferring them, and a photo is the one thing in Nura that never leaves the backend
without an authenticated check on every byte, which embedding one in a shareable
PDF would remove. **A custom report period is not offered in the app**: the API
accepts one and validates it, but the screens offer the four presets, because a
date-range picker is its own accessible-control problem and section 14's presets
cover what people actually ask for. **Report text is English only**, and the date
and count wording is hand-rolled precisely so the output is reproducible;
translating it starts in `wording.py`. And **a report is typeset in the PDF
standard fonts** until `REPORT_FONT_PATH` points at a TrueType font, so a
non-Latin script does not render — the fix is a setting, not code.

PRD 8 adds five. **Mobile voice input and text-to-speech are not built** —
section 32 and section 33 both make them optional, and building either would
mean a microphone permission and a speech pipeline for a feature the PRD does
not require; the settings that would drive them are stored and the screen says
what they are for. **The assistant speaks English only**, stated rather than
faked, per section 31. **Memory extraction is deterministic**, not a second
model call: section 93's shapes are matched by pattern, because a model asked
"was that a preference?" would cost a request per message and answer "sometimes
yes" on "I'm tired today" — precisely what section 42 warns against. **Response
streaming to the app is not implemented**, which section 54 permits, because
the guardrails run after the model and a sentence shown and then withdrawn is
worse than a short wait. And **nothing scrubs the model's output** — see the
known gap above and
[assistant-safety.md](docs/architecture/assistant-safety.md#what-is-not-enforced).

PRD 9 adds five, and the first two are the ones somebody could be hurt by
assuming otherwise about.

**Nothing contacts an emergency contact.** Section 47 is explicit that PRD 9
builds the records, the order and the permissions and that escalation belongs to
PRD 10. No function reads `priority` to decide who to reach, and the screens say
so where somebody is typing a phone number — because that is the one assumption
a person is most likely to make about a list called "emergency contacts".

**Audio calling is partial, and documented as such** (section 38).
`AudioCallProvider` is real and complete — five methods, no vendor concept in any
signature — the state model is real, and the authorization is real. The only
implementation refuses with `calling_not_configured`, because section 38 forbids
simulating a successful call, and the app shows a sentence instead of a Call
button rather than one that always fails.

**Two permissions granted nothing at the time, and both now do.**
`safety_alerts` had no event source until PRD 10, which section 94 anticipates
and says not to fabricate; `routines` had no record anywhere in PRD 0–11 to
point at. Both were stored faithfully, both appeared in
`granted_without_data`, and the screens said plainly that they shared nothing
rather than showing an empty section that reads as "nothing recorded". PRD 10
built the first source and PRD 12 built the second, so
`CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE` is now empty — kept, with its check,
for the next permission reserved before its data exists.

**Routines had no suggestion type, and PRD 12 added three.** Section 85 lists
`add_routine` and `change_routine` and section 27 says a caregiver may suggest
one — but nothing in PRD 0–9 defined what a routine *is*: no table, no fields,
no screen in section 83. Inventing one was not that PRD's call. PRD 12 defined
the record, and the registry took `add_routine`, `change_routine_time` and
`pause_routine` in the one place this paragraph promised it would.

**Photo messages are reserved, not built** (section 33). Optional, and requiring
private storage, signed access and size limits; the private-storage half exists
from PRD 6, the upload route and picker flow do not. `photo` stays in
`FAMILY_MESSAGE_TYPES` so the column and constraint are already right, and is
absent from `FAMILY_MESSAGE_TYPES_ALLOWED` — the approach PRD 6 took to future
symptom sources.

And **no notification is delivered for any of it.** All eight preferences in
section 48 are recorded and nothing is sent. An approval request stays visible
in-app regardless, which is what section 48 actually requires.

PRD 10 adds four, and the first is the one somebody could be hurt by assuming
otherwise about.

**Nothing reaches a person outside the app.** No push provider, no SMS
provider, no calling provider. PRD 10 built the interfaces, the escalation
policy, the attempt records and the capability model; what escalation can do
today is create an in-app alert record for a caregiver and write down, channel
by channel, that calling and texting are not configured. `delivered` exists in
the attempt vocabulary and **no code path writes it**. Section 39 forbids
simulating success, and a provider that logged and returned success would have
been the single most dangerous thing this project could contain.

**No detector exists, and none is clinically validated.** No fall model, no
immobility model, no seizure-like classifier, no vomiting detector.
`services.safety.detectors.DETECTORS` is an empty tuple — and the emptiness is
load-bearing, because it is what makes `robot_detection: not_connected` derived
rather than hard-coded. Section 117 forbids claiming any validation, and none
has been performed.

**Timely escalation depends on a job nothing schedules.** See section 8 above.
Section 80 asks for state correctness and timely escalation to be
distinguished, and they are: the first needs nothing, the second needs
`scripts/safety_maintenance.py` on a schedule this repository does not create.

**Photo and video are not stored at all** (section 92), and that is a decision
rather than a gap: a future detector should emit events rather than continuous
raw media, so there is no media column on any safety table and the detector
interface carries scalars only.

PRD 11 adds four of its own, and the first is the one somebody could be
misled by assuming otherwise about.

**Nothing has ever been shown on a screen.** PRD 11 built the queue, the eight
layouts, the face geometry, the capability model, the acknowledgement contract
and the firmware's whole side of the protocol. The physical display driver
compiles and reports `not_verified`; `SilentAudioOutput` returns false from
every call; there is no text-to-speech provider; and **no physical
acknowledgement has ever reached the backend**, so every `displayed` row in any
database came from a simulated acknowledgement in a test. Section 141 asks the
question directly, and the answer is no.

**The robot's own unit tests have never run.** They compile for the target, and
PlatformIO's Unity tests execute on the board. What runs on a development
machine is the vocabulary agreement across the firmware header, the backend and
the app — three-way, so a drift fails on a laptop — plus the same dispatch
implemented in the simulator.

**There is no on-robot input.** Section 85's `taken`, `snooze` and `skip`
actions are in the protocol and travel on a payload only when a device reports
buttons or touch. Nothing ever has, so every card says "Use the Nura app to
respond" (section 86), and the routing is exercised by the simulator rather
than by a finger.

**A presentation's housekeeping job is optional, unlike PRD 10's.** Expiry is
applied on every read path, so a card is never handed over late whether or not
`scripts/robot_maintenance.py` has run. It is the difference between a worker
that is load-bearing and one that keeps a table tidy, and it is worth stating
because PRD 10's is the other kind.

PRD 12 adds three, and none of them is about the robot.

**No notification and no alarm has ever fired, and nothing has verified the
operating system's behaviour.** Creating, editing, enabling and scheduling all
work and are tested; whether a phone wakes somebody at seven is untested, and
the product says so beside the switch rather than in a release note. Vibration
is stored as a choice and has never been felt. Sections 71 to 73 ask for
exactly this statement.

**Nura cannot look anything up, and that is structural.** Weather, news and an
external calendar are `not_configured` in every deployment because nothing
implements them -- not because a flag is off. Section 12 forbids fabricating
live information, and the strongest version of that is code with no path to
fabricate: there is no HTTP client, no API key and no parser for any of the
three. A deployment that sets a provider name gets a warning and the same
answer.

**PRD 5's and PRD 7's reminders were deliberately not migrated.** PRD 12 built
`features/notifications/scheduler.ts` and moved only its own two domains onto
it. Section 62 asks for integration without destabilising what works, and
re-testing two working, offline-sensitive reminder systems for no behaviour
change is destabilising for nothing. The shared module is ready when somebody
wants them moved.

**Out of scope, and stated so nobody assumes otherwise** (section 76): live
weather, live news, external calendar sync, email sending, smart-home control,
shopping, payments, maps and navigation, travel booking, autonomous web
browsing, full project management, shared family task boards, caregiver access
to general tasks, a physical wake-word engine, microphone input, speaker
alarms, production speech recognition or text-to-speech, HealthKit, Health
Connect and wearables.

PRD 13 adds two, and neither is about a feature.

**No penetration test, no compliance certification.** See above. The suite is
evidence about this code's boundaries.

**No re-authentication before deletion.** The identity provider would have to
offer one. Until then: three steps, an exact phrase, and the limitation said
where it applies.

**What PRD 13 found rather than added, recorded because it is the useful part
of the stage.** A profile switch left twenty-six keys' worth of the previous
person's data in the cache -- health record, dose history, adherence, symptom
entries, appointment questions, doctor reports, check-ins, safety status, tasks,
routines -- and two of the entries that were present matched nothing at all.
Signing out cleared the cache and left seventeen storage keys and seven
persisted stores on disk. Neither was found by reading the lists; both were
found by tests that read the source and require every key to be classified in
both directions.

**Out of scope until later PRDs:** real fall, seizure-like, vomiting and
immobility detection, production delivery providers, automatic ambulance
dispatch, jurisdiction-specific emergency-service calling (PRD 10, section 69),
video calling, calendar sync, a clinician portal, HealthKit and Health Connect,
AI analysis of family messages or safety events, custom avatar packs or
multiple robot characters, a wake-word engine, production speech recognition or
text-to-speech, physical camera or microphone monitoring, robot locomotion, and
games.

---

## 10. Decision records

| ADR | Decision |
| --- | -------- |
| [0001](docs/decisions/0001-react-native-expo.md) | React Native + Expo for the app |
| [0002](docs/decisions/0002-fastapi-postgresql.md) | FastAPI + PostgreSQL for the backend |
| [0003](docs/decisions/0003-device-connectivity.md) | BLE for setup and recovery, Wi-Fi for everything else |
| [0004](docs/decisions/0004-supabase-auth.md) | Supabase issues identities; Nura verifies them and owns the data |
| [0005](docs/decisions/0005-ble-pairing.md) | react-native-ble-manager, and SPAKE2 for the pairing code |
| [0006](docs/decisions/0006-today-and-offline-checkins.md) | One Today endpoint, a card registry, and how an offline check-in is settled |
| [0007](docs/decisions/0007-health-record-foundation.md) | Health records belong to a profile, dates keep their precision, provenance is the server's |
| [0008](docs/decisions/0008-medication-scheduling.md) | A schedule carries its zone, doses are rows, an action sets a state, and editing never touches the past |
| [0009](docs/decisions/0009-symptom-tracking.md) | An episode is a bout, both flows share one draft, uncertainty suppresses escalation, and the urgent rules ship disabled |
| [0010](docs/decisions/0010-appointments-and-reports.md) | A report is a stored snapshot of finished text, one file writes prose, the user picks symptoms one at a time, and regeneration never overwrites |
| [0011](docs/decisions/0011-assistant-and-model-boundary.md) | One method at the model boundary, deterministic guardrails rather than a scrubber, counts rather than records in the prompt, and one write that waits for a person |
| [0012](docs/decisions/0012-caregiver-access-and-approval.md) | Caregivers on a second authorization path rather than a third role, a role that grants nothing, forbidden changes that are unrepresentable rather than refused, and three features built only as far as they could be honest |
| [0013](docs/decisions/0013-safety-monitoring-and-escalation.md) | Sensor events that describe rather than diagnose, monitoring that is explicitly activated and server-bounded, deadlines as columns rather than timers, PRD 9's authorization and contact chain reused, and unconfigured providers that fail explicitly rather than simulating success |
| [0014](docs/decisions/0014-robot-presentation-architecture.md) | A robot that is additive and never called into, capabilities reported by the device with `not_verified` only from it, predefined layouts rather than markup, a backend-owned queue where only safety preempts, the idle face as a queued presentation, command delivery distinguished from physical render by a database constraint, and simulator-first verification |

| [0015](docs/decisions/0015-daily-life-actions-and-external-capabilities.md) | Four separate records rather than one flexible item, PRD 5's recurrence engine called rather than copied, a low-risk write that executes and everything else proposed, external capabilities derived from whether a provider is implemented rather than configured, and a limitation the server sends with every alarm list |

| [0016](docs/decisions/0016-privacy-export-deletion-and-reliability.md) | Synchronous export and deletion with one table and no worker, an export whose contents are declared column by column rather than stripped, a deletion service that reads storage keys before it deletes rows, one security suite that enumerates routes from the application, and a drift test on every hand-maintained list |

Further reading: [system overview](docs/architecture/system-overview.md),
[health data](docs/architecture/health-data.md),
[the medication system](docs/architecture/medication-system.md),
[the symptom system](docs/architecture/symptom-system.md),
[the Nura assistant](docs/architecture/nura-assistant.md),
[assistant safety](docs/architecture/assistant-safety.md),
[the appointment and report system](docs/architecture/appointment-and-report-system.md),
[API reference](docs/api/README.md),
[provisioning protocol](docs/device/provisioning-protocol.md),
[firmware](firmware/xiao_esp32s3/README.md),
[safety monitoring, SOS and escalation](docs/architecture/safety-monitoring.md),
[safety and emergency architecture](docs/architecture/safety-and-emergency.md),
[caregivers and family](docs/architecture/caregiver-and-family.md),
[the robot companion experience](docs/architecture/robot-companion-experience.md),
[presentation protocol](docs/device/presentation-protocol.md),
[daily life and the general assistant](docs/architecture/daily-life-assistant.md),
[privacy, security and reliability](docs/architecture/privacy-security-reliability.md),
[data classification and retention](docs/architecture/data-retention.md).
