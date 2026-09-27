# Nura

Nura is a desktop health companion: a small robot built around a Seeed Studio
XIAO ESP32-S3, a cross-platform mobile app, and a backend service.

This repository is at **PRD 6 — Symptom Tracking & Structured Symptom
Communication**. It is a real everyday app rather than a setup utility: a branded
five-tab app with Light/Dark/System themes, account creation and onboarding, a
Today screen with a daily wellbeing check-in and configurable cards, a structured
health record, medication reminders with offline-safe Taken / Snooze / Skip,
symptom tracking with a guided conversation and private photos, a FastAPI
backend, and the firmware and app flow for connecting a robot.

> **Nothing in PRD 3 to PRD 6 needs the robot.** Today works with no robot
> linked, with one that is offline, and with one the backend has heard from — and
> a seeding script reaches all three states without hardware. The health record,
> the medication system and the whole symptom system work with no robot at all,
> and none of them involves speech recognition. See sections 8 to 11.

> **The robot has not been built yet.** The pairing flow, the firmware and the
> backend are written and tested as far as software allows — the cryptography
> matches published test vectors on both sides — but no BLE connection, Wi-Fi
> provisioning or device registration has ever run on hardware.

> **Nura does not diagnose illness, prescribe treatment or change medication
> doses.** It reminds and records; it does not advise. It records symptoms so
> they can be described to a clinician, and it never works out what is causing
> them. No AI assistant, caregiver or emergency functionality exists at this
> stage.

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

## 8. Today, check-ins and the development fixtures

Once onboarding is finished the app lands on **Today**: a greeting, the daily
wellbeing check-in, what needs attention today, and whether Nura is connected.
Cards are looked up by key from a registry, so the user can show, hide and
reorder them from **More → Customize Today**.

### Which day is "today"

The phone sends the date on its own clock (`?local_date=YYYY-MM-DD`) and the
backend stores it as a plain date. Someone checking in at 11pm in Karachi means
that day, not the following one in UTC. The server accepts any date within one
day of its own — enough for every real time zone, and narrow enough that the
"today" endpoint cannot be used to write arbitrary history.

### A check-in made with no signal

Answering while offline saves the check-in on the phone and says so on the
card. It is sent when the connection returns, or when Today is next focused.
Because the endpoint is a `PUT` keyed on person and date, a queued answer that
arrives late updates the same row rather than creating a second one. If the
server has a *newer* edit than the queued one, the server's answer wins and the
app adopts it (`applied: false` in the response).

### Today with no signal

The last successful Today response is kept on the device, so an outage shows
the saved day rather than an error page. It is only used for the day it was
fetched on, and the robot’s connection is deliberately left out of it: offline,
the card says "Status unavailable" rather than repeating a status that may be
hours old.

### Seeing the connected states without a robot

A robot is online if `devices.last_seen_at` is within 90 seconds. That one
field is the whole story, so writing it directly produces the genuine article.
From `backend/`, with the virtualenv active:

```bash
python -m scripts.seed_dev --list
```

```bash
python -m scripts.seed_dev --account latest --device online --keep-online 300
```

```bash
python -m scripts.seed_dev --account latest --device offline --minutes-ago 42
```

```bash
python -m scripts.seed_dev --account latest --device none
```

`--account latest` means the most recently created account, which during
development is the one signed in on the phone. `--device online` is a single
heartbeat and goes stale after 90 seconds exactly as an unplugged robot would;
`--keep-online` holds it up for as long as you need to walk through the screen.
The script also seeds check-ins:

```bash
python -m scripts.seed_dev --account latest --checkin not_great --note "tired"
```

```bash
python -m scripts.seed_dev --account latest --checkin none
```

It refuses to run unless `APP_ENV=development`, and it is not reachable from
the app: there is no "pretend the robot is online" button anywhere in the UI.
The seeded device uses the hardware id `NURA-DEADBEEF0001`, which is not a real
MAC address, so it can never collide with a board you later build.

## 9. The health record

Health holds what someone tells Nura about their health: conditions,
medications, allergies, doctors, surgeries and procedures, medical notes and
blood type. **None of it needs the robot** — no health endpoint touches the
device tables, and no health data is ever sent over BLE.

It is built to be filled in gradually. Only a name is ever required, setup can
be stopped at any point and resumed, and a partly-filled profile is a normal
state rather than a warning. The completeness figure is informational and
blocks nothing.

### Dates people only half remember

A condition diagnosed "in 2015" is stored as a year, not as the 1st of January
2015. Each approximate date is a date *or* a year, never both, and "I don't
remember" stays exactly that. The form asks which kind of answer someone has.

### What Nura does not do with it

It does not check, verify or confirm anything; every record is what a person
said, and the screens say so. It does not infer severity from a reaction, work
out whether a medication is current from its end date, suggest a condition
from typed text, compute an interaction risk, or tell anyone to start, stop or
change a medication. PRD 4 stores and displays.

Record values are never logged: health logs name the resource and the action
and stop. See
[docs/architecture/health-data.md](docs/architecture/health-data.md).

### Seeing it filled in without typing it all

From `backend/`, with the virtualenv active:

```bash
python -m scripts.seed_dev --account latest --health partial
```

```bash
python -m scripts.seed_dev --account latest --health complete
```

```bash
python -m scripts.seed_dev --account latest --health empty
```

`partial` leaves the profile part-way through setup with a resume point;
`complete` fills every section including blood type; `empty` clears it back to
nothing. As with the device fixtures, the script refuses to run unless
`APP_ENV=development` and nothing in the app can reach it.

### The optional Today card

PRD 4 registers a **Health profile** card for Today. It is **off by default**:
the Health tab is where people look for this, and Today stays calm unless
asked. Turn it on in **More → Customize Today**. It shows a percentage and a
way in, never a condition or medication name.

## 10. Medication reminders

Care is where medication *management* lives: schedules, what is due today,
Taken / Snooze / Skip, history, adherence and refills. Health keeps the
medication record itself — what the medication is — and links across to here.

```text
Health = what the medication is
Care   = when to be reminded about it
```

**None of it needs the robot.** Reminders are local notifications from the
phone, and every feature works with no robot linked. The one robot-facing
route is described at the end of this section.

### Setting one up

Add a medication in **Health → Medications**, then **Care → Medications → Set
up reminders** and choose it. A schedule is "every day" or "on selected days",
with one or more times, a start date and an optional end date. There is
deliberately nowhere to express a taper, a sliding scale or a calculated
dose — those belong to a clinician.

Notification permission is asked for at that moment and nowhere earlier, so
the prompt arrives with an obvious reason. Declining is handled honestly: the
schedule still exists and the app still shows what is due; only the phone's
alert is off.

### What happens at a dose

Every scheduled dose offers **Taken**, **Snooze** (10, 30 or 60 minutes, up to
three times) and **Skip** (with an optional reason, which Nura records and
never interprets). Two hours after it was due, an unrecorded dose becomes
*missed* — which reads as "Wasn't marked as taken", because it is a fact and
not a reprimand. Taking it afterwards keeps the same dose and records when it
actually happened.

Sending an action twice is harmless. A dose is one row and an action sets its
state, so a retried request leaves one Taken and takes one off the supply
count, not two.

### Time zones

A schedule carries the time zone it was made in, so 8am stays 8am across a
daylight-saving change. The two awkward days a year are decided rather than
left to chance: a local time that does not exist produces one dose, and one
that happens twice produces one dose. Changing a schedule's zone regenerates
its future doses, so travelling cannot double a day.

### Offline

If the phone cannot reach the backend, the action is saved on the device and
the row says so. It is sent when a medication screen is focused or the
connection returns. The queue holds one answer per dose — pressing Taken then
Skip sends one final answer — and the most recent explicit action wins if the
same dose was recorded somewhere else meanwhile.

### Refills

Supply tracking is off until you turn it on per medication. Nura takes one off
the count when a dose is marked Taken, never on Snooze or Skip, and warns at a
threshold you choose. The number is yours: Nura shows it back with "about",
never estimates how long it will last, and never suggests ordering anything.

### Seeing it filled in without waiting a week

From `backend/`, with the virtualenv active:

```bash
python -m scripts.seed_dev --account latest --medications demo
```

```bash
python -m scripts.seed_dev --account latest --medications empty
```

`demo` builds every state worth looking at: a dose due now, an overdue one,
taken, skipped and missed doses behind them, a paused schedule, an inactive
medication, a medication with no schedule at all, and a supply that is running
low. `--timezone Europe/London` puts the fixture times in a chosen zone. As
with the other fixtures, the script refuses to run unless `APP_ENV=development`
and nothing in the app can reach it.

If a schedule is left running for days, this keeps everybody's doses current
the way a deployment's cron would:

```bash
python -m scripts.medication_maintenance
```

Nothing depends on it: opening the app replenishes that person's doses anyway.

### The Today card

PRD 5 makes the **Medications** card real, and it is **on by default** — a
dose that is due is the single most useful thing Today can show. It draws
nothing at all for anybody with no schedules, so it is invisible until it is
relevant. An overdue dose also appears in Important Today, worded plainly and
never as an emergency.

### The future robot action

When the robot eventually hears "I took it", it will call:

```http
POST /api/v1/device-actions/medication-doses/{dose_id}/taken
Authorization: Bearer <device token>
```

That contract exists now and is tested with a seeded device token. It is
authenticated by the robot's own device token — the robot never holds a user's
credentials — the dose must belong to the profile the device is linked to, and
it can never override what the person recorded themselves. **No part of it has
run on hardware, and no voice recognition exists.**

To exercise it during development:

```bash
python -m scripts.seed_dev --account latest --device-token
```

There is no pretend-robot button anywhere in the app, and there never will be.
The full design is in
[docs/architecture/medication-system.md](docs/architecture/medication-system.md).

## 11. Symptoms

Health is where symptoms live: what you are experiencing, in your own words, over
time. It is kept firmly apart from Conditions, which is what a clinician has told
you you have.

```text
Conditions = what you have been told you have
Symptoms   = what you are experiencing, and how it changes
```

**None of it needs the robot, and none of it involves speech.** The
"Talk to Nura" flow is a text conversation in the app.

### Two ways to describe something

Health → Symptoms offers two equal options:

```text
[ Talk to Nura ]   [ Log manually ]
```

Both fill the same draft, end on the same review screen, and save the same
record. The only difference is which one you find easier to use.

**Talk to Nura** is a short guided conversation. It is deterministic — a
vocabulary and a set of rules, with no model behind it — and it reads everything
a message says rather than only the answer to the question it asked. So this:

> I have a sharp pain in my left knee that started yesterday and is 6/10

fills the symptom, the location, the character, the onset and the severity, and
Nura asks about none of them. It asks what is still missing, skips what makes no
sense for the symptom — radiation for nausea, a location for a fever — and offers
tap answers alongside the text box so the whole thing can be done without typing.

**Log manually** is the same questions as one scrollable form. Only the first
field is required; everything else says (optional) and means it.

Either way you see everything before it is saved, and you can change any of it.
That review screen is the reason a rule-based conversation is safe to ship:
whatever the rules made of what you typed, you read it back in plain words first.

### What gets recorded

A **symptom** is an episode — one bout — and each time you write about it is an
entry:

```text
Headache
  25 Sep  3/10   started, throbbing, behind both eyes
  26 Sep  4/10   about the same
  27 Sep  6/10   getting worse, nausea, no vomiting
```

Adding an update asks only what can have changed: how bad it is, which way it is
going, anything new alongside it, a note, a photo. It never makes you re-enter
the description.

Severity is 0 to 10, anchored as "no symptom" and "the worst you can imagine".
Nura never turns your number into a word — "moderate" would be its judgement of
your answer, not your answer.

"No nausea" and "I might have felt dizzy" are kept as what they are. A summary
that quietly dropped them, or read them as symptoms you have, would say more than
you did.

### When something ends, and when it comes back

**Mark as ended** takes a symptom out of your active list and keeps everything you
logged. It is not deletion, and Nura never decides on its own that a symptom is
over — one nobody has updated for six weeks is still active.

If it comes back, Nura starts a **new** record for this time round and links it to
the old one. Each bout keeps its own start and its own history, so "how many times
has this happened?" has an answer.

Delete is there too, for something logged by mistake. The confirmation says what
goes and points at the other option.

### Photos

Optional, for a rash, a swelling, a wound healing. They are private: stored on the
backend behind a route that checks it is you on every single request, with no
public link and no shareable URL anywhere. The app compresses them and strips the
location metadata before uploading.

**Nura does not look at them.** It does not classify a rash, assess a wound or
identify an infection, and it says so on screen every time you attach one.

### What Nura says back

One sentence, and only when you have recorded a change yourself:

> You have recorded this as worsening. If it keeps getting worse, becomes severe,
> or is affecting what you can normally do, consider contacting a healthcare
> professional.

That is triggered by something you did — you chose "worsening", your own number
went up by two or more, or you added a new symptom alongside it. A high number on
its own is never enough.

Nura does not diagnose, does not name a condition, does not guess a cause, does
not call anybody and does not change anything about your medication. If you say
something concerning and Nura is unsure it understood, it asks:

> Just to confirm: are you saying you have severe difficulty breathing right now?

Your answer is recorded as what it is — yes, no, or not sure. **The urgent-care
rules that would act on a "yes" are written and tested but switched off**, because
no clinician has reviewed them. Turning them on is a clinical decision, not a
deployment one. Everything in this section that Nura can say lives in one file so
it can be reviewed without touching any symptom code.

### Offline

Describe a symptom with no signal and it is saved on the phone, photos included,
and sent when you are back online. The row says so until it has synced. Nothing
is reported as uploaded before the backend confirms it, and a retry can never
produce two copies.

### Seeing it filled in without waiting a week

From `backend/`, with the virtualenv active:

```bash
python -m scripts.seed_dev --account latest --symptoms demo
```

```bash
python -m scripts.seed_dev --account latest --symptoms empty
```

`demo` builds a worsening headache with three entries, an improving knee with a
photo, a resolved sore throat, and lower back pain that has recurred — which
between them cover every state worth looking at. One thing it cannot build is an
*offline pending* symptom: that only exists on a phone, so reach it by turning
Wi-Fi off and saving one.

### On Today

The **Symptoms** card is on by default, and draws nothing at all until you have
used the feature — most people have nothing to report most of the time. After
that it shows what you most recently wrote about, with a way to add an update. A
symptom you marked as worsening also appears in Today, worded plainly and never
as an emergency.

The full design, including the conversation engine and the safety boundary, is in
[docs/architecture/symptom-system.md](docs/architecture/symptom-system.md).

## 12. Run the tests

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

The mobile suite needs nothing running. It mounts the real Today, Health,
medication and symptom screens and drives them against a stubbed backend — a
check-in, a dose recorded as taken, a skip with a reason, a symptom described
from scratch and saved — covers the pairing flow end to end against a simulated
robot that runs the real protocol, and checks the app's cryptography against
RFC 9382's test vectors. One test parses the firmware's `protocol.h` and fails if
the app and the robot disagree about any UUID, message type or status code;
another reads every Today, Health, medication and symptom component and fails if
a colour has been written into one instead of coming from the theme.

A few tests are about *wording*, which is unusual and deliberate: PRD 5 and PRD 6
ask for neutral, non-judgemental copy and forbid anything that reads as medical
advice, so those are asserted rather than left to whoever edits the strings next.
One of them reads every sentence Nura can say about a symptom and fails on a
named condition, a likelihood or an attribution of cause.

The guided symptom conversation is tested as a pure function, which is how PRD 6's
hardest requirement — never ask again for something the user already volunteered —
is asserted directly rather than inferred from a screenshot.

The backend suite **does need PostgreSQL running**. It creates a separate
`nura_test` database on first run, applies the real migrations to it, and rolls
each test back afterwards — so the tests also prove the migrations produce a
schema the code works against. Your `nura_dev` data is never touched. Neither
suite needs a Supabase project or a network connection: tokens are signed with
a key pair generated inside the test run and verified by the real production
verifier.

## 13. Code quality

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
mypy app alembic scripts
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
| `mobile/src/components/today/` | Today cards and the card registry            |
| `mobile/src/services/checkins/` | The offline check-in queue                  |
| `mobile/src/services/today/` | The saved copy of the last Today response       |
| `mobile/src/features/health/` | Health section specs, form logic, API, drafts  |
| `mobile/app/health/`      | Health setup, sections and record forms         |
| `mobile/src/features/medications/` | Schedule rules, dose wording, reminders, offline queue |
| `mobile/app/medications/` | Schedules, doses, history, supply and the skip sheet |
| `backend/app/services/medications/` | Recurrence, dose actions, supply, adherence |
| `mobile/src/features/symptoms/` | The shared draft, the guided conversation, photos, offline queue |
| `mobile/app/symptoms/`    | Overview, manual log, Talk to Nura, review, history, detail |
| `backend/app/services/symptoms/` | Episodes, entries, photos, safety-netting, summary |
| `backend/app/services/storage.py` | Private object storage for symptom photos |
| `backend/scripts/`        | Development fixtures, and the medication maintenance job |
| `backend/app/api/`        | HTTP routes (`/health`, `/api/v1/*`)            |
| `backend/app/models/`     | SQLAlchemy models                               |
| `backend/alembic/`        | Migrations                                      |
| `firmware/xiao_esp32s3/`  | Robot firmware (PlatformIO)                     |
| `docs/device/`            | The phone-to-robot provisioning protocol        |
| `docs/`                   | Architecture overview and decision records      |

## Documentation

- [System overview](docs/architecture/system-overview.md)
- [Health data](docs/architecture/health-data.md) — who health records belong
  to, the authorization rule, and the privacy rules
- [The medication system](docs/architecture/medication-system.md) — schedules,
  time zones, dose generation, status transitions, reminders, offline
  behaviour and the robot action contract
- [The symptom system](docs/architecture/symptom-system.md) — episodes and
  entries, the shared draft, the guided conversation, uncertainty handling,
  photo privacy, offline behaviour and the safety boundary
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
  [BLE pairing](docs/decisions/0005-ble-pairing.md),
  [Today and offline check-ins](docs/decisions/0006-today-and-offline-checkins.md),
  [Health record foundation](docs/decisions/0007-health-record-foundation.md),
  [Medication scheduling](docs/decisions/0008-medication-scheduling.md),
  [Symptom tracking](docs/decisions/0009-symptom-tracking.md)

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

The same limitation applies to Today: submitting a check-in *is* covered
(it travels through TanStack Query, which does re-render), but pressing
**Change** to reopen the chooser, typing a note, and the show/hide and reorder
controls on **Customize Today** only move local state, so they are not
asserted. The logic behind them — card visibility, ordering, the layout sent to
the server, the greeting buckets, the local-date rule and the offline queue —
is covered directly in `mobile/tests/`, and every server-side rule is covered
against a real database in `backend/tests/`.

The health and schedule forms are in the same position: what a form *means* —
the defaults a new record starts with, what is refused, what is actually sent,
how a year-only date survives the round trip, how "9am on Mon, Wed and Fri"
becomes three rows and reads back as a sentence — is tested directly and
thoroughly, while typing into a field and watching it re-render is not. The
delete confirmations *are* asserted, because they go through a native alert
rather than local state.

**The symptom form is the exception**, and deliberately so. Every field on it
writes into a Zustand store rather than into local component state, and a store
update does re-render under React 19 — so that form is driven the way a user
drives it, typing included. That was one of the reasons for putting the draft in
a store.

**Only email sign-in has been verified end to end.** Google, Apple and phone
are implemented against the Supabase SDK and documented above, but marked
unverified: Apple needs macOS or an iOS device plus a paid developer account,
and phone needs a paid SMS provider. None of them simulate success — an
unconfigured provider is reported as unavailable.

**No symptom photo has ever been taken on a phone.** The picker and the
compression step run through `expo-image-picker` and `expo-image-manipulator`,
neither of which has a real implementation under Jest, so what is proven is the
upload contract, the type sniffing, the authorization chain, the deletion of both
object and row, and the offline queue that holds a photo until it can be sent.
Choosing an image from a real camera roll, and the permission prompts around it,
are on the by-hand list below.

**No notification has ever been delivered by a phone.** The reminder service
is tested against a recording stub — which doses it schedules, what they say,
what it cancels when a schedule changes, and how it behaves when permission is
refused — but `expo-notifications` has never run on a device, so nothing here
claims a reminder has actually fired. That needs a development build on real
hardware; see section 5.

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
