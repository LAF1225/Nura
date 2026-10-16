# Nura

Nura is a desktop health companion: a small robot built around a Seeed Studio
XIAO ESP32-S3, a cross-platform mobile app, and a backend service.

This repository is at **PRD 13 — Privacy, security and offline reliability**. It is a real
everyday app rather than a setup utility: a branded five-tab app with
Light/Dark/System themes, account creation and onboarding, a Today screen with a
daily wellbeing check-in and configurable cards, a structured health record,
medication reminders with offline-safe Taken / Snooze / Skip, symptom tracking
with a guided conversation and private photos, appointments with a one-page
doctor summary you can export as a PDF, an in-app Nura assistant with health
guardrails, configurable personality and user-managed memory, caregivers with
per-category permissions who can suggest changes you approve, family messages
and an emergency-contact chain, Safety Monitoring with an explicit check-in and
an emergency request that walks that chain and tells you exactly what it
managed, the whole software layer for the robot's own screen — a presentation
queue, a canonical face, a serious information mode, privacy-aware reminders
and a simulator that exercises all of it without hardware — a task list,
general reminders, alarms and step-by-step routines that Nura can add for you,
one Privacy & Security screen with a data export and a deliberate deletion
flow, a FastAPI backend, and the firmware and app flow for connecting a robot.

> **Nothing in PRD 3 to PRD 13 needs the robot.** Today works with no robot
> linked, with one that is offline, and with one the backend has heard from — and
> a seeding script reaches all three states without hardware. The health record,
> the medication system, the whole symptom system, the whole appointment and
> report workflow, the whole Nura assistant, the whole caregiver and family
> layer and the whole safety layer work with no robot at all — none of them
> involves speech recognition or a microphone. PRD 11 is *about* the robot and
> still does not need one: every workflow it adds runs in a simulator, and the
> app and backend behave identically whether a robot is connected, offline or
> has never existed. PRD 12's tasks, reminders, alarms and routines are the
> same: every one of them works on the phone alone, and so does everything
> PRD 13 added. See sections 8 to 18.

> **The robot has not been built yet.** The pairing flow, the firmware and the
> backend are written and tested as far as software allows — the cryptography
> matches published test vectors on both sides — but no BLE connection, Wi-Fi
> provisioning or device registration has ever run on hardware.

> **Nura does not diagnose illness, prescribe treatment or change medication
> doses.** It reminds and records; it does not advise. It records symptoms so
> they can be described to a clinician, and it never works out what is causing
> them. The doctor summary it produces restates what you recorded and adds
> nothing — no impression, no probable cause, no treatment.

> **Nura cannot reach anybody outside the app.** PRD 10 built Safety
> Monitoring, the emergency request and the escalation that walks the
> emergency-contact chain — and what escalation can actually do today is create
> an in-app alert record for a caregiver and write down that calling and texting
> are not set up. **No push notification has ever been delivered, no text
> message sent and no call placed.** The app says so on the screen where it
> matters and lists it channel by channel after an emergency request; it never
> says anybody was contacted.

> **Nura has never shown you anything.** PRD 11 built the robot's whole
> presentation layer — the queue, the priorities, the face, the capability
> model and the acknowledgement contract — and no frame has ever been drawn on
> a panel, no sound has ever been played, and **no physical robot has ever
> acknowledged a presentation**. The app distinguishes "sent to Nura" from
> "shown" and a database constraint stops anything claiming the second without
> the robot having said so. What is verified is the contract and the
> simulator; simulator proof is not hardware proof.

> **Nura cannot look anything up on the internet.** PRD 12 added tasks,
> reminders, alarms and routines — and no weather provider, news provider or
> external calendar is configured in this build, so Nura says so instead of
> answering. **No forecast, headline or external calendar event has ever been
> fetched by this repository**, and there is no code path that could fetch one.
> A screen lists the whole map: four things Nura can do and three it cannot.

> **No alarm and no notification has ever fired.** Alarms and reminders are
> stored and scheduled, and the app has never been run on a physical phone, so
> whether the operating system wakes anybody is untested. The app says that
> beside the alarm list rather than in a release note, and the server sends the
> sentence with every alarm list so a client cannot forget it.

> **Nothing watches you.** There is no fall detection, no seizure-like
> detection, no vomiting detection and no immobility detection: no detector
> exists in this project, and none has been clinically validated. Safety
> Monitoring means Nura will ask whether you are okay *if something reports a
> possible event* — and the only thing that can report one today is a
> development harness. The monitoring screen says exactly that whenever
> monitoring is on.

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

## 12. Appointments and the doctor summary

**This is the workflow everything else has been building towards**, and none of
it needs the robot. You record an appointment, choose what to bring, and Nura
produces a one-page PDF you can hand to a clinician.

```text
Care -> Appointments -> [ Add appointment ]
                        [ an appointment ] -> Prepare for appointment
```

The Today card shows the next one, and there is a section on **Care** beside
medications.

### Adding one

Only three things are required: what it is, the date and the time. Everything
else -- the clinician, the place, the address, the phone number, a note to
yourself -- is optional, and the Save button turns on as soon as those three are
right.

Two fields are worth explaining:

**The clinician** is picked from your own list of doctors (the one in Health), and
linking one does something concrete: it lets Nura work out what has changed
*since you last saw them*. Without a link, the report falls back to the last 30
days and says why.

**The time zone** is your phone's, and it is stored with the appointment. An
appointment at 3:30 PM in London still reads 3:30 PM after the clocks change and
after you fly somewhere else. Nura shows it in the appointment's own zone, so
while you are travelling "Tomorrow" means tomorrow where the appointment is.

### Reminders

Two, if you leave them on: a day before, and two hours before. The day-before one
offers to prepare your summary. Changing the time, cancelling the appointment or
turning the switch off reschedules or removes them.

They are OS-scheduled local notifications, like medication reminders, so they do
not need the app to be running. As with those, **no notification has ever been
delivered by a phone** -- see Known issues.

### Prepare for Appointment

Four steps, and every one of them can be revisited:

```text
Review        what you have recorded, over a period you choose
Questions     what you want to ask, in your own words
Choose        which sections go in, and whether to add the appendix
Preview       exactly what the PDF will say -> Share
```

**The review shows and does not decide.** Every symptom you have recorded in the
period is listed with its counts, its severity range and the change you recorded
-- and every one is ticked, for you to untick. Nothing is highlighted, ordered by
severity or marked as significant: which symptom matters is your call, not Nura's.
The same goes for medications, the dose counts, the check-in counts and the
health background.

**The period** defaults to *since your last visit with this clinician*. When Nura
cannot work that out -- no clinician linked, or no earlier appointment with them
-- it uses the last 30 days and tells you that is what it did. You can also pick
7, 30 or 90 days.

**Questions are yours.** Nothing rewords them. Underneath the list, Nura may
offer a prompt or two built from what you recorded -- *"Would you like to ask
about your worsening headaches?"* -- and nothing is added until you press the
button. Once you do, it is an ordinary question, indistinguishable from one you
typed.

### The summary

One page, aiming to stay one page. If what you ticked is too long, Nura tightens
the summary and moves the detail to the appendix rather than shrinking the text;
if it is still too long, it runs onto a second page at a readable size.

What it contains is only what you ticked. A section you turned off is *absent*; a
section you asked for that has nothing in it says "Not recorded", which is worth
saying -- a doctor learning that no allergies are recorded is different from being
shown nothing.

What it never contains is an opinion. It restates what you wrote: counts, your own
change answers, your own words in quotation marks. Every page carries the line:

> This is a summary of information recorded in the Nura app. It is not a
> diagnosis, an assessment or medical advice.

**Preview, then export.** The preview shows the report's own text -- the same
text the PDF is made from -- so what you approve is what you send. Nothing is
exported until you press Share, which downloads the PDF and opens your phone's
own share sheet: Files, email, messaging, AirDrop, print. Nura does not send it
to anybody.

The file is called `Nura_Health_Summary_2026-10-02.pdf`: a date and nothing
medical, because a filename shows up in places you did not choose.

### Versions

Pressing Regenerate makes a **new version**. The old one keeps its text and its
PDF, because you may already have sent it. Every version is listed with when it
was made and what it covered, and deleting one removes only that document --
your health records are untouched.

### Offline

| What you do | What happens |
| --- | --- |
| Look at your appointments | Shown from the last copy |
| Add an appointment | Kept on this phone, marked as such, sent later |
| Add a question | The same |
| Make a summary | **Refused, and said so** |

The last row is deliberate. The PDF is built by the backend, so there is nothing
useful to keep on the phone -- and pretending it worked would be worse than
saying it did not. Your selections are saved, so you can press the button again
when you are back online.

### Seeing it filled in without booking anything

```bash
cd backend
python -m scripts.seed_dev --account latest --appointments demo
```

That gives you a prepared cardiology follow-up tomorrow with three questions, an
unprepared physiotherapy session today (the one Important Today raises), a blood
test next week, a completed annual review with two real generated report versions
-- one summary-only and one with the appendix -- and a cancelled dentist visit.
The reports are produced by the real pipeline, so the PDFs on disk are genuine.

`--appointments empty` clears them again, including the stored PDFs.

Pass `--timezone Europe/London` to place the fixtures in a zone other than UTC.

One state cannot be seeded: an **offline question draft** lives only on a phone,
in the app's own queue. Turn off Wi-Fi and add a question to see it.

### The Today card

Unlike the medication and symptom cards, this one always draws something. With
nothing upcoming it says "No upcoming appointments" and offers to add one, because
checking when the next visit is, or noting one down, is a reason people open the
app. With something upcoming it shows what, who, when and whether it has been
prepared for, with one button.

An appointment today or tomorrow also appears in Important Today. It is never
worded as an emergency.

The full design is in
[docs/architecture/appointment-and-report-system.md](docs/architecture/appointment-and-report-system.md).

## 13. Talking to Nura

**PRD 8 is where Nura starts answering.** A conversation in the app, with the
records you have already kept behind it — and, as with everything since PRD 3,
no robot involved.

```text
Nura tab -> [ Start a conversation ]
            Personality · Voice and language · What Nura remembers
            When Nura speaks first · Custom instructions
```

### Setting it up

The assistant needs a model provider, and it is entirely server-side. Add to
`backend/.env`:

```bash
AI_PROVIDER=anthropic
AI_API_KEY=your-key
```

`AI_MODEL` defaults to `claude-opus-5`; `AI_TIMEOUT_SECONDS`, `AI_EFFORT`,
`AI_MAX_OUTPUT_TOKENS` and `ASSISTANT_RATE_LIMIT_PER_HOUR` all have sensible
defaults. Every one of them is listed in `.env.example`.

**Leave `AI_PROVIDER` blank and everything still runs.** The Nura tab says the
assistant is not set up on this server, the settings screens work, and the rest
of the app is untouched. That is the state the whole test suite runs in.

> **The provider connection is unverified.** No request has reached Anthropic
> from this repository: there is no key in the development environment and the
> tests run against a scripted provider. The adapter's request and reply shapes
> are tested offline; the round trip is not. See
> [assistant-safety.md](docs/architecture/assistant-safety.md).

### What Nura will and will not do

It explains medical words, summarises what you have recorded, helps you write
questions for a clinician, and answers ordinary questions.

It does not diagnose, does not advise on medication, does not reassure you that
a symptom is harmless, and does not replace emergency services. Ask what is
wrong with you and it says plainly that it cannot tell you — and then helps
with what it can. Ask whether to stop a tablet and it points at your clinician
or pharmacist. Both of those sentences are put there by the *server*, not
requested of the model, so they are there whatever the model said.

Say "Nura, emergency" and no model is called at all: a fixed notice says
escalation is not set up yet and points at your local emergency services.

### What it can change

One thing, and only after you press Confirm: adding a question to an
appointment.

```text
You:  Add "ask about dizziness" to my doctor questions.
Nura: Add "Ask about dizziness" to your questions for Cardiology follow-up?
      [ Confirm ]  [ Cancel ]
```

Nothing else. There is no tool that edits a dose, stops a medication, changes a
diagnosis or deletes a record.

### What it remembers

A short list of how you like to be spoken to — "call me Baba", "keep morning
conversations short" — and nothing clinical. Your health records are kept
separately and are not copied into it.

Nura proposes; you press Remember. Removing one forgets that one thing and
touches nothing else, and pausing one stops it reaching the model while keeping
it on the list.

### Personality, voice and modes

Four presets and five three-step dials. A preset sets the dials and then stops
mattering — nudging one afterwards leaves the rest alone, and the screen says
"Gentle (Adjusted)" rather than claiming a preset you have moved away from.

Voice and speaking speed are stored for when there is something to speak with,
and the screen says so rather than offering a control that does nothing.

Modes are Normal, Focus, Sleep and Privacy. **None of them touches your
medication or appointment reminders** — those follow their own settings, and
the screen says that too.

### Offline

Your conversations stay readable and an unsent message is kept on the phone.
Nothing is queued: a reply needs a model the phone cannot reach, and Nura says
so rather than promising an answer later.

### Seeing it filled in without typing it all

```bash
cd backend
python -m scripts.seed_dev --account latest --assistant demo
```

Three conversations — an ordinary one, one with a tool call, and one answered
in serious mode — plus four memories and custom instructions. `--assistant
privacy` does the same in Privacy mode, and `--assistant empty` clears it.

No model is called by any of it, so it works with `AI_PROVIDER` unset.

The full design is in
[docs/architecture/nura-assistant.md](docs/architecture/nura-assistant.md), and
what is and is not enforced is in
[docs/architecture/assistant-safety.md](docs/architecture/assistant-safety.md).

## 14. Caregivers and family

**PRD 9 is where somebody else can help.** Invite a caregiver, choose exactly
what they see, and nothing they suggest happens until you approve it.

### Inviting somebody

Care → Caregivers → Invite someone. You choose their name, a relationship label
and which of eight categories they may see:

```text
Medication reminders   Appointments   Symptoms   Health reports
Family messages        Health summary Safety alerts   Routines
```

**Nothing is granted by default.** Every category starts off.

**Nura cannot send the invitation.** There is no mail or SMS infrastructure in
this backend, so what you get back is a link, shown once, for you to pass on
however you already talk to them. The app says so rather than offering a Send
button that quietly does nothing. The link expires after seven days, works once,
and is stored only as a hash.

They sign in, see exactly what they will and will not be able to access, and
accept or decline. **They do not need their own health profile** to help with
yours.

### What a caregiver sees

Only the categories you granted — and a category you did not grant is *absent*
from their screen rather than shown empty, so they cannot tell from the app
whether you record symptoms at all.

Even with everything granted, a caregiver sees deliberately less than you do:
medication names and reminder times but **no skip reasons**, symptom severities
but **no free text and no photos**, that a doctor report exists but **not its
contents**, and counts rather than names in the health summary.

A caregiver reaches **no screen or endpoint built before PRD 9**.

### Suggestions

A caregiver can propose five things, and nothing else:

```text
change a medication reminder time      pause a medication reminder
turn a medication reminder back on     add an appointment
change an appointment time
```

Changing a **dose**, a condition or a diagnosis is not on that list and is not
refusable-but-possible — there is no such action anywhere in the system.

You see the change spelled out — "Now 7:00 PM / Suggested 8:00 PM" — and press
Approve or Decline. Nothing is applied until you do, and a request waits in the
app whatever your notification settings say. A note you add when declining is
yours; the caregiver never sees it.

### Messages and check-ins

A conversation per caregiver, plus one-tap check-ins: *I'm okay*, *Not feeling
great*, *Can you call me?*, *I need help with something*. They can send *How are
you doing?* and *Thinking of you*.

These are messages, not alerts. Nura does not call anybody and does not decide
one of them is urgent. A message you have typed is kept on the phone if you go
offline — and the app says it has not been sent, because there is no send queue.

**Calling through Nura is not available.** The provider interface exists, the
authorization exists, and no provider is configured — so there is no Call button
rather than one that fails.

### Emergency contacts

Care → Emergency contacts. Names, phone numbers and the order you would want
them tried, reordered with Move up and Move down.

**Nura does not contact them.** This is the chain, built and ordered, for the
stage that will use it.

### Seeing it filled in without typing it all

```bash
cd backend
python -m scripts.seed_dev --account latest --caregivers demo
```

Two active caregivers with different permission sets, one pending invitation
(whose link is printed), one revoked, a pending suggestion and an approved one,
a thread with three messages, and three emergency contacts. `--caregivers multi`
also makes one caregiver support a second person, and `--caregivers empty` clears
it all — without touching your health record.

Sign in as a caregiver with the printed accounts (auth subject
`dev-caregiver-ayesha`, and so on).

The full design is in
[docs/architecture/caregiver-and-family.md](docs/architecture/caregiver-and-family.md).

## 15. Safety monitoring and SOS

**PRD 10 is the first part of Nura that could matter when you are not holding
your phone.** Which is exactly why its governing rule is honesty: nothing here
claims more than happened.

Care → Safety.

### Safety Monitoring

Monitoring is **off until you turn it on**, and it is never turned on quietly.
You choose how long:

```text
30 minutes      1 hour      Until bedtime      Until turned off
```

and how long Nura waits for an answer if something happens — 15, 30, 45, 60 or
90 seconds, 45 by default — and whether it asks a second time before
escalating. The second wait is always 20 seconds.

"Until bedtime" needs a bedtime, and Nura **does not work one out from your
behaviour**. The screen asks for one.

**While monitoring is on, the screen says that nothing is actually watching.**
There is no fall detector, no camera and no microphone in this project, so
monitoring means Nura will prompt you if something reports a possible event,
and records what happens. Saying "Safety Monitoring is on" without that
sentence would be the most misleading thing in the app.

### Asking for help

The **Ask for help** button takes two taps. The second one tells you what will
happen and what will not:

> Nura will record an emergency request and create an in-app alert for any
> caregiver who can see safety alerts. It cannot call or text anyone.

It works whether or not monitoring is on, and it skips any countdown.

Saying **"Nura, emergency"** to the assistant does the same thing, and it never
reaches a model: the phrase is matched before anything else happens.

### If something is reported

```text
Nura noticed something unusual. Are you okay?

[ I’m okay ]   [ I need help ]   [ Dismiss — false alarm ]
```

"I'm okay" ends it and contacts nobody. "I need help" escalates immediately.
No answer within your chosen wait escalates too — and that deadline lives on
the server, so it does not depend on the app staying open.

### What escalation actually does

Your caregivers with **Safety alerts** granted get an in-app alert record.
Then your emergency contacts, in the order you put them in. Then the facts:

```text
In-app alert created for Ayesha.
Phone call for Spouse: not set up in this build.
Text message for Spouse: not set up in this build.
Some steps were taken and some are not available
```

**An alert record is not a notification.** It means the alert exists for them
to find, not that they have seen it — and nothing in the app says otherwise.

You can say you are okay at any point, including after alerts already exist:
the answer is recorded, anything unsent stops, and what already happened stays
in the history.

### What Nura can do

Safety → What Nura can do lists it, with no diplomacy:

| | |
| --- | --- |
| Emergency request | Available |
| Safety check-in prompts | Available |
| In-app alerts for caregivers | Available |
| Push notifications | Not set up in this build |
| Text messages | Not set up in this build |
| Audio calling | Not set up in this build |
| Automatic detection by the robot | Not connected yet |

Every row is computed from what is actually wired up, so it cannot drift from
the truth.

### Safety history, and false alarms

Every event is kept with what was observed, whether you answered, and what
escalation managed. After one finishes you can mark it a false alarm — or
record that it was not one, which is a different answer from not being asked.
**Nothing is trained on these labels.**

### Fixtures, without hardware

```bash
cd backend
python -m scripts.seed_dev --account latest --safety monitoring
python -m scripts.seed_dev --account latest --safety possible-fall
python -m scripts.seed_dev --account latest --safety no-response
python -m scripts.seed_dev --account latest --safety sos
python -m scripts.seed_dev --account latest --safety history
python -m scripts.seed_dev --account latest --safety empty
```

`possible-fall` leaves a real check-in waiting with its real deadline;
`no-response` runs the timeout and the escalation the maintenance worker would
have run. To exercise the device-trigger contract, take a device token and post
to it — the script prints the `curl`. **There is no fake emergency button
anywhere in the app, and there never will be.**

### Timely escalation needs a scheduled job

A deadline that passes is acted on whenever anybody next reads the event, so the
state is always correct. Making it *timely* for somebody who is not looking
needs:

```bash
cd backend
python -m scripts.safety_maintenance
```

once a minute, from cron or whatever your deployment already has. It is
idempotent. **Nothing in this repository schedules it**, so in a default
deployment escalation happens on the next read rather than on time — which is
the honest limit, written down here rather than discovered later.

The full design is in
[docs/architecture/safety-monitoring.md](docs/architecture/safety-monitoring.md).

## 16. The robot's screen and companion behaviour

**PRD 11 built everything the robot needs to show you something, and the robot
still does not exist.** That is the whole shape of this stage: the presentation
queue, the priorities, the face, the capability model, the acknowledgement
contract, the firmware's side of the protocol and a simulator that drives all
of it — with no panel, no speaker and no frame ever drawn.

More → Nura Device.

### A companion first and a screen second

At rest Nura shows its face: two rounded eyes and a slow blink. When something
matters it switches to plain information and the face goes away entirely —
which is the point rather than a limitation. A medication reminder, a safety
check-in and an emergency are all information, and none of them is accompanied
by an expression.

```text
Medication                 Safety Monitoring          EMERGENCY MODE
Reminder due               ON until 10:30 PM          Nura is processing your
Use the Nura app                                      safety request.
to respond.                                           In-app alert created
                                                      for Ayesha.
                                                      Calling is not configured.
```

There are nine face states and **none of them carries a health judgement**.
There is no worried face, no alarmed face and no sad face, so there is nothing
for a screen to reach for because a symptom was severe.

### The screen is in a room other people walk through

Which is the reason the default medication reminder says as little as it can:

```text
Full details          Metformin / 500 mg · 8:00 PM
Medication name only  Metformin / 8:00 PM
Private reminder      Medication / Reminder due        ← the default
```

The redaction happens when the card is built, not when it is drawn, so the
app's own history cannot show more than the robot was sent. Privacy Mode
overrides the preference downwards: somebody who chose full details and then
switched Privacy Mode on gets the private card.

### Twelve capabilities, not one "robot ready"

Nura reports each part of itself separately, and the app shows all twelve
whatever they say:

```text
Screen              Working / Not tested yet / Not fitted / Not reported
Text on screen      Speaker        Microphone      Buttons
Animation           Spoken words   Listening       Touch screen
                    Sounds         Camera / Camera detection
```

**"Not tested yet" is a real state and the important one.** It means the
firmware has the driver and nothing physical has been proven — which is what a
real first build would honestly report, and what a hopeful screen would round
up to "working". Only the robot can report it; the backend has never seen a
build and does not guess.

A report also goes stale when the firmware version changes, because a display
proven two versions ago has not been proven by the version running now.

### Nothing is "shown" until the robot says so

The app's history distinguishes two things that are easy to blur:

```text
Medication reminder — sent to Nura
Medication reminder — shown
```

The first means the backend handed the card over. The second means a device
reported drawing it. **No physical robot has ever reported drawing anything**,
so nothing outside a test has ever read as shown — and a database constraint
means no code path can write it without an acknowledgement.

### Audio, which has never made a sound

The read-aloud settings exist and all default off. Their wording is what keeps
them honest: *"When Nura has a working speaker, read messages out loud."* No
speaker has ever been reported by anything, nothing has ever been played, and
there is no text-to-speech provider in this project.

Where there is no speaker, the Audio section is a sentence rather than a row of
dead switches — a greyed-out volume slider still implies there is a speaker to
be loud.

### Seeing all of it without a robot

```bash
cd backend
python -m scripts.seed_dev --account latest --robot online
python -m scripts.robot_simulator status
python -m scripts.robot_simulator poll --times 5
python -m scripts.robot_simulator plan
```

`--robot` takes `online`, `offline`, `unverified` (the display driver is there
and untested), `headless` (no screen at all), `speaker` (a working speaker,
which nothing in this project has ever produced) and `empty`.

`robot_simulator plan` walks the whole manual test plan and prints the lines a
person would read off the screen at each step. The simulator is a real device
as far as the backend is concerned: it reports capabilities, reconciles,
fetches and acknowledges through the same services the HTTP endpoints call.

**It is not in the app, and will not be.** A test asserts that nothing under
`app/api` imports it.

There is also a preview in the app — More → Nura Device → Preview Nura's
display — which draws each card layout with sample content and says *Preview
only* in a line a screen reader reaches before the cards.

### Housekeeping, which nothing depends on

```bash
cd backend
python -m scripts.robot_maintenance
```

Expiry is applied on every read, so a card is never handed over late whether or
not this has run. Unlike PRD 10's safety worker, **nothing depends on this
being scheduled** — it keeps the table tidy so the history screen and the
queue-depth diagnostic do not read as though something is waiting.

The full design is in
[docs/architecture/robot-companion-experience.md](docs/architecture/robot-companion-experience.md),
the wire contract in
[docs/device/presentation-protocol.md](docs/device/presentation-protocol.md).

## 17. Tasks, reminders, alarms and routines

**This is where Nura stops being only a health app.** A task list, general
reminders, alarms and routines — the ordinary daily-life things somebody uses a
companion for, kept in their own tables and touching nothing medical.

Where to find it: the **More** tab, then **Tasks & routines**. There is a Today
card and a Care-tab card as well, and both stay invisible until you have made
something.

### Four things that look alike and are not

```text
Task      "Call the physiotherapist"   may have no time at all
Reminder  "Stand up and stretch"       6:30 PM, every day
Alarm     "Morning"                    7:00 AM, weekdays
Routine   "Morning routine"            3 steps, 2 done
```

A task may have no time, because a thing to do is not a thing to do *at* a
time and forcing one would make the list lie about the commitment. A reminder
generates concrete occurrences you can complete, dismiss or snooze. An alarm
stores no occurrences at all — nobody asks whether last Tuesday's seven
o'clock alarm went off. A routine makes a run each day and you tick its steps
off as you go.

A routine's run covers the **whole day** rather than a moment: a morning
routine is still this morning's at eleven, and it counts as missed only when
the day has gone.

### What an alarm in this build actually is

```text
Alarms are scheduled as phone notifications. Nura has never been run on a
physical phone, so whether one actually wakes you has not been tested.
```

That sentence is beside the alarm list, it arrives from the server with every
alarm list, and **the app refuses a response that does not carry it**. Creating,
editing, enabling and scheduling an alarm all work; whether the operating system
wakes you is a different question and nobody has answered it.

### Nura cannot look anything up

Ask it about the weather, the news or your work calendar and it says so:

```text
Weather            Live weather is not configured in this build.
News               Live news access is not configured in this build.
External calendar  I can add that to Nura, but an external calendar is
                   not connected.
```

**No forecast, headline or external calendar event has ever been fetched by
this repository**, and there is no code path that could fetch one: the three
provider slots exist, nothing implements them, and a deployment that names a
provider gets a warning in the log and the same `not_configured` answer. A
screen shows the whole map — four things Nura can do, three it cannot — at
**More → Tasks & routines → See what Nura can reach**.

### Asking Nura instead of filling in a form

"Remind me to call the pharmacy at 4" adds the reminder and tells you. So do
"add a task", "mark that done" and "set an alarm for 7" — they are small, they
appear in a list and they are one tap to undo.

Changing a task's wording, creating a routine and pausing one are **proposed
rather than done**, and you approve them, because each one changes something
that already exists.

Two things it will not do. **"Remind me later" is a question, not a guess** —
there is no default time anywhere, so Nura asks which time you meant. And
**"remind me to double my dose" writes the note and says it cannot change a
medication**: no tool in Nura can alter a medication, a dose or a schedule.
"Pick up my medication" is an errand and is treated as one.

Nura has no clock and no location, so a reminder's time zone comes from zones
you have entered yourself — through a reminder, an alarm, a routine, a
medication schedule or an appointment. With none of those, it asks rather than
assuming UTC.

### A caregiver sees routines and nothing else

Granting the **Routines** permission shows somebody helping what your routines
are, when they run and how today is going — and lets them *suggest* a routine,
a different time, or pausing one, which you approve or decline like any other
suggestion. An approved one stays marked as theirs for as long as it exists.

**Tasks, alarms and personal reminders are not shareable at all.** There is no
permission for them, no route that returns them and no suggestion a caregiver
could send about them. The Care screens say so in a sentence rather than
showing a short list and leaving you to wonder.

### On the robot

Four more cards, through the same queue PRD 11 built: a task, a reminder, an
alarm and a routine's progress. An alarm ranks above an appointment and is the
one daily-life card Sleep and Privacy mode leave alone — an alarm silenced by
Sleep mode would be an alarm that does not work. The robot still **cannot sound
it**, so the card says so.

Daily-life cards have their own privacy level, separate from medication's, and
one switch turns all four off without touching a single task.

### Offline

Everything you do here queues. Creating a task, completing one, ticking a
routine step and completing a reminder are all held while there is no signal
and sent in order when there is, and a step completion carries its own id so a
retry cannot invent progress. The screens say what is waiting; nothing is shown
as saved until the server has it.

### Seeing it filled in without typing it all

```bash
cd backend
python -m scripts.seed_dev --account latest --daily-life demo
```

`--daily-life` takes `demo` (an overdue task, one due today, one with no due
date, a daily reminder, a weekday alarm and a three-step routine with two steps
ticked), `busy` (the same plus a second routine, a monthly reminder and a
one-off alarm) and `empty`. The terminal prints the Today sentence, the counts,
the next alarm and the limitation above.

The full design is in
[docs/architecture/daily-life-assistant.md](docs/architecture/daily-life-assistant.md).

### Housekeeping, which nothing depends on

```bash
cd backend
python -m scripts.productivity_maintenance
```

Occurrences and runs are replenished on every read and a missed one is computed
on read, so a list is correct whether or not this has ever run. Like PRD 11's
job and unlike PRD 10's, **nothing depends on it being scheduled.**

## 18. Privacy, your data, and deleting it

**One place for every privacy control, and two things you can do with your
data.** More -> Privacy & Security.

### What it shows you

Everything on it is read from the thing it describes rather than written into
the screen, which is the only way it can be trusted to stay true:

```text
Privacy Mode        Off            and: it is not a hardware switch
What Nura remembers 3 of 4 in use
Conversations       2
Caregiver access    1 person       Ayesha: medications, appointments
Safety Monitoring   Off            Push notifications: not set up in this build
Nura Device         Screen: not tested yet. Speaker: not connected
What Nura can reach Live weather is not configured in this build
```

Two sentences on it are there because nobody would think to ask for them. One
is that **Privacy Mode is not a hardware switch** -- it changes how Nura
behaves and cannot turn off a microphone. The other is that **Nura has not been
tested on a physical phone or robot**, and that where something is unverified
the app says so rather than assuming it works.

The camera and microphone rows say what Nura has *never asked for* rather than
what it turned off. There is no voice input anywhere in the app, so
"microphone: off" would be a claim about hardware nobody queried.

### Export

```text
Privacy & Security -> Export your data
```

One private file holding everything recorded on a profile, plus your symptom
photos and report documents. It says three things before offering to make one:
what is in it, that it is kept for a day and then deleted, and that it contains
no passwords, sign-in tokens, invitation links or device secrets.

```text
nura-export.zip
├── manifest.json
├── profile.json  health.json  medications.json  symptoms.json
├── appointments.json  assistant.json  caregivers.json
├── safety.json  daily-life.json  devices.json
└── files/photos/…  files/reports/…
```

It is not emailed anywhere, it is served only to you through an authenticated
request, and two exports of unchanged data are byte-identical -- so "has
anything changed" is a question you can answer by comparing them.

One at a time. Delete the one you have to make another.

### Deleting your data

```text
Privacy & Security -> Delete your data
```

Three steps, deliberately. First it shows what would go, counted from the
database -- how many records, how many files, how many people lose access.
Then you type a phrase exactly. Then it happens.

What goes: everything recorded on that profile, including every photo and
document. What stays: your sign-in, any other profile on the account, and a
robot you paired -- which stays yours and goes back to being set up for nobody.

Nura cannot ask for your password again, because it never receives one. The
screen says that, because anybody holding an unlocked phone with your session
could complete this, and the phrase is what stops a mis-tap rather than what
stops an intruder.

### Signing out now clears this phone

Signing out used to clear the in-memory cache and leave everything on disk.
It now also removes seventeen stored items -- every offline queue, the Today
cache, the notification mirrors, and every draft: a symptom being described, a
part-filled appointment, an unsent message to Nura or to a caregiver. A second
person signing in on the same phone starts from nothing.

### Switching between people clears the previous one

Caregiver Mode drops every cached answer about whoever was on screen before,
rather than refetching over it -- so the next screen starts from a loading
state instead of briefly showing the wrong person's data. PRD 13 found that
list badly out of date and added twenty-six keys to it.

### Housekeeping, which nothing depends on

```bash
cd backend
python -m scripts.privacy_maintenance
```

An export's expiry is compared on every read, so an expired archive cannot be
downloaded whether or not this has run. The script deletes the bytes and marks
the row. `--dry-run` counts without touching anything.

## 19. Run the tests

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
medication, symptom, appointment, Nura, caregiver, safety, Nura Device and
daily-life screens and drives them against a stubbed backend — a check-in, a dose recorded as taken, a skip with a reason, a symptom
described from scratch and saved, an appointment typed in and a summary generated,
previewed and shared — covers the pairing flow end to end against a simulated
robot that runs the real protocol, and checks the app's cryptography against
RFC 9382's test vectors. Two tests parse the firmware's headers and fail if the
app and the robot disagree — `protocol.h` for any UUID, message type or status
code, and `presentation_protocol.h` for any layout, face state,
acknowledgement, capability or text limit. The backend checks the second one
too, which makes that agreement three-way;
another reads every Today, Health, medication, symptom, appointment and
daily-life component and fails if a colour has been written into one instead of
coming from the theme.

A few tests are about *wording*, which is unusual and deliberate: PRD 5, PRD 6 and
PRD 7 ask for neutral, non-judgemental copy and forbid anything that reads as
medical advice, so those are asserted rather than left to whoever edits the
strings next. One reads every sentence Nura can say about a symptom, another
every sentence the appointment screens can say, and a third every string a
generated report can contain — including its appendix — and each fails on a named
condition, a likelihood, an attribution of cause, a treatment suggestion or a
graded adherence figure.

The guided symptom conversation is tested as a pure function, which is how PRD 6's
hardest requirement — never ask again for something the user already volunteered —
is asserted directly rather than inferred from a screenshot.

The report pipeline is tested the same way, end to end: a generated PDF is read
back with `pypdf` to confirm the summary starts on page 1, the appendix appears
only when it was asked for, the expected headings are there and an excluded
section is not. Two further tests are about immutability — editing a symptom
entry after generating leaves the report unchanged, and re-rendering a stored
snapshot produces the same file byte for byte.

The backend suite **does need PostgreSQL running**. It creates a separate
`nura_test` database on first run, applies the real migrations to it, and rolls
each test back afterwards — so the tests also prove the migrations produce a
schema the code works against. Your `nura_dev` data is never touched. Neither
suite needs a Supabase project or a network connection: tokens are signed with
a key pair generated inside the test run and verified by the real production
verifier.

## 20. Code quality

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
| `mobile/src/features/appointments/` | The form draft, the report selection, reminders, export |
| `mobile/app/appointments/` | List, form, detail, prepare, questions, select, preview, versions |
| `backend/app/services/appointments/` | Visits, questions, periods, preparation, snapshot, PDF, versions |
| `mobile/src/features/nura/` | Conversation state, composer drafts, personality, memory |
| `mobile/app/nura/`        | Conversation, history, personality, voice, memory, modes, instructions |
| `backend/app/services/assistant/` | The model boundary, prompts, guardrails, tools, memory, conversations |
| `mobile/src/features/caregivers/` | Care mode, permission helpers, message and suggestion drafts |
| `mobile/app/caregivers/`  | Caregiver list, invite, permissions, care requests |
| `mobile/app/care-mode/`   | Caregiver Mode: home, supported people, suggesting a change |
| `mobile/app/family/`      | Family messages and check-ins |
| `mobile/app/emergency-contacts/` | The emergency-contact chain and its order |
| `backend/app/services/caregivers/` | Permissions, invitations, suggestions, messaging, contacts, audit |
| `mobile/src/features/safety/` | Safety status, capabilities, SOS and check-in state |
| `mobile/app/safety/` | Safety Monitoring, the check-in, emergency mode, history, capabilities |
| `mobile/app/care-mode/safety-alerts.tsx` | A caregiver's safety alerts |
| `backend/app/services/safety/` | Monitoring, events, check-ins, escalation, providers, capabilities |
| `backend/scripts/safety_maintenance.py` | The durable timeout and retry worker |
| `mobile/src/features/robot/` | Robot capabilities, preferences, presentation history |
| `mobile/app/robot/`       | Nura Device: settings, capabilities, history, preview |
| `backend/app/services/robot/` | The presentation queue, priorities, builders, capabilities, simulator |
| `mobile/src/features/productivity/` | Task, reminder, alarm and routine state, validation, the offline queue |
| `mobile/src/features/notifications/` | The shared notification scheduler the daily-life reminders use |
| `mobile/app/daily/` | Tasks, reminders, alarms, routines, a run, and the capability map |
| `backend/app/services/productivity/` | Recurrence, tasks, reminders, alarms, routines, the capability map, providers |
| `mobile/src/features/privacy/` | The privacy hub's state, the export and deletion flows, the local-data inventory |
| `mobile/src/features/reliability/` | The one retry policy all five offline queues share |
| `mobile/app/privacy/` | Privacy & Security, the export screen, the delete flow |
| `backend/app/services/privacy/` | What an export contains, building one, deleting a profile, the hub, the wording |
| `backend/scripts/robot_simulator.py` | A robot you can drive from a terminal |
| `firmware/.../presentation_*` | The robot's side of the presentation protocol |
| `backend/app/services/storage.py` | Private object storage for symptom photos and report PDFs |
| `backend/scripts/`        | Development fixtures, and the medication, safety, robot and daily-life maintenance jobs |
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
- [The appointment and report system](docs/architecture/appointment-and-report-system.md)
  — appointments and their time zones, the preparation workflow, report-period
  rules, the frozen snapshot, versioning, PDF privacy and the export path
- [The Nura assistant](docs/architecture/nura-assistant.md) — the model
  boundary, the context builder, the tool layer, conversations, memory,
  personality, proactivity and cost controls
- [Assistant safety](docs/architecture/assistant-safety.md) — what Nura will
  and will not say, the three layers that hold it up, and **what is not
  enforced**
- [Safety monitoring, SOS and escalation](docs/architecture/safety-monitoring.md)
  — the state machine, the exact timings, the escalation policy, what is
  configured and **what has never been validated**
- [Caregivers and family](docs/architecture/caregiver-and-family.md) — the two
  authorization paths, category permissions, the suggestion-and-approval
  boundary, messaging, the emergency-contact chain, the audit trail and **what
  is not enforced**
- [The robot companion experience](docs/architecture/robot-companion-experience.md)
  — the face, serious information mode, the privacy rules for a screen in a
  room, capability truthfulness and **what has never been shown to anybody**
- [Privacy, security and reliability](docs/architecture/privacy-security-reliability.md)
  — the hub, the export format, the deletion order, the authorization matrix,
  the offline vocabulary and **the three things PRD 13 found already broken**
- [Data classification and retention](docs/architecture/data-retention.md) —
  nine categories, how long each lives, and what is never logged
- [Daily life and the general assistant](docs/architecture/daily-life-assistant.md)
  — the four records and why they are separate, the recurrence engine shared
  with medications, the low-risk write policy, the capability map and **what
  no provider in this build can reach**
- [Safety and emergency architecture](docs/architecture/safety-and-emergency.md)
- [API reference](docs/api/README.md)
- [Provisioning protocol](docs/device/provisioning-protocol.md) — UUIDs,
  messages, states and the security model for phone-to-robot setup
- [Presentation protocol](docs/device/presentation-protocol.md) — the envelope,
  the eight layouts, priorities, expiry, acknowledgement and the capability
  schema
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
  [Symptom tracking](docs/decisions/0009-symptom-tracking.md),
  [Appointments and the doctor report](docs/decisions/0010-appointments-and-reports.md),
  [The assistant and the model boundary](docs/decisions/0011-assistant-and-model-boundary.md),
  [Caregiver access and approval](docs/decisions/0012-caregiver-access-and-approval.md),
  [Safety monitoring and escalation](docs/decisions/0013-safety-monitoring-and-escalation.md),
  [Robot presentation architecture](docs/decisions/0014-robot-presentation-architecture.md),
  [Daily-life actions and external capabilities](docs/decisions/0015-daily-life-actions-and-external-capabilities.md),
  [Privacy, export, deletion and reliability](docs/decisions/0016-privacy-export-deletion-and-reliability.md)

## Known issues

**Nothing has ever reached a person outside this app.** No push notification
has been delivered, no text message sent, no call placed. PRD 10 built the
escalation engine, the provider interfaces and the capability model; the only
channel with anything behind it is an in-app alert record, and even that is
recorded as *attempted* rather than *delivered*, because a record is not a
reading.

**No detector exists, and none has been clinically validated.** There is no
fall model, no immobility model, no seizure-like classifier and no vomiting
detector. The detector registry is empty, which is what makes the capability
screen say "Automatic detection by the robot: not connected yet" rather than
somebody having typed that.

**Timely escalation depends on a job nothing schedules.** A passed deadline is
acted on whenever the event is next read, so the *state* is always right.
Making escalation *timely* for somebody who is not looking at their phone needs
`scripts/safety_maintenance.py` on a once-a-minute schedule, and this
repository does not set one up. The worker is real and tested against a real
database with a frozen clock; what is missing is the cron line.

**The safety screens have never run on a phone.** They are mounted and driven
in tests against a stubbed backend. Nobody has answered a real countdown on a
real device.

**No frame has ever been drawn on a panel, and no sound has ever been played.**
PRD 11 built the presentation queue, the layouts, the face geometry, the
capability model and the firmware's whole side of the protocol. The physical
display driver compiles — `pio run -e xiao_esp32s3_peripherals` — and reports
`not_verified` rather than `available`, because an SPI `init()` returning true
is not evidence a person saw a legible frame. `SilentAudioOutput` returns false
from every call, and there is no text-to-speech provider.

**No physical robot has ever acknowledged a presentation.** Every `displayed`
row in any database came from a simulated acknowledgement in a test. The app
says "sent to Nura" for a card the backend handed over, and a database
constraint stops anything writing `displayed_at` without a device having
reported a render.

**The firmware's presentation tests have never run.** They compile for the
target — `pio test -e xiao_esp32s3 -f test_presentation --without-uploading
--without-testing` — and PlatformIO's Unity tests execute on the board, so
without a board they cannot be executed. What *is* executed on a development
machine is the vocabulary agreement between the firmware header, the backend
and the app, plus the same dispatch implemented in the simulator.

**Nura Device has never run on a phone either.** The screens are mounted in
jest-expo and driven against a stubbed backend. Nobody has changed a brightness
setting on a real device for a robot that exists.

**No caregiver has ever used this on a phone, and nothing has ever been
delivered.** The authorization is tested against a real database with two real
accounts holding two genuinely signed tokens; the experience is not. No
invitation has been sent — Nura has no way to send one, and says so — no
notification has reached a phone, and no audio call has ever been placed.

**Audio calling is deliberately partial (PRD 9, section 38).** The provider
interface, the state model and the authorization are real; the only
implementation refuses with `calling_not_configured`. Section 38 forbids
simulating a successful call, so there is no Call control in the app rather than
one that always fails.

**One caregiver permission grants nothing yet.** `routines` has no record
anywhere in PRD 0–10 to point at. It can be granted, it is stored faithfully,
and the screens say plainly that it shares nothing — rather than showing an
empty section that reads as "nothing recorded". `safety_alerts` was the second
until PRD 10 built the event source it was waiting for.

**Photo messages are reserved, not built (section 33).** `photo` is in the
stored message vocabulary so the column and constraint are already right, and is
refused from a client: the private-storage half exists from PRD 6, the upload
route and picker flow do not.

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

**The symptom and appointment forms are the exceptions**, and deliberately so.
Every field on them writes into a Zustand store rather than into local component
state, and a store update does re-render under React 19 — so those forms are
driven the way a user drives them, typing included. That was one of the reasons
for putting the drafts in stores, and PRD 7 did the same for the report selection
and for which appointment list is on screen.

One consequence is worth recording, because it cost time: a press that arrives
before a store update has re-rendered reads the state as it was a moment ago. The
report generator therefore reads the selection at press time rather than from the
render closure, and the tests wait for the *control* to show its new state before
pressing the next thing.

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

**No notification has ever been delivered by a phone.** All four reminder
services — medication doses, appointments, general reminders and alarms — are
tested against a recording stub: which reminders they schedule, what they say,
what they cancel when a schedule, an appointment, a reminder or an alarm
changes, and how they behave when permission is refused. But
`expo-notifications` has never run on a device, so nothing here claims a
reminder has actually fired. **No alarm has fired, no vibration has been felt
and no background behaviour has been observed**, which is why the alarm screens
carry that sentence. That needs a development build on real hardware; see
section 5.

**Nothing external is configured, and nothing pretends to be.** There is no
weather provider, no news provider and no external calendar in this build. The
three slots exist in configuration, nothing implements them, and a deployment
that names one gets a warning in the log and the same `not_configured` answer —
so a misconfiguration produces an honest refusal rather than a feature that
sometimes answers. Gmail and email sending, smart-home control, shopping,
payments, maps and travel booking are not built at all, and Nura never browses
the web.

**Medication reminders and appointment reminders were deliberately left on
their own schedulers.** PRD 12 introduced a shared notification scheduler and
moved only its own two domains onto it. Migrating PRD 5's and PRD 7's reminders
would mean re-testing two working, offline-sensitive systems for no behaviour
change, so they stay where they are; the shared module is ready for them when
somebody wants that.

**No report PDF has ever been shared from a phone.** The backend genuinely
generates the document — the tests read the bytes back with `pypdf` and check its
pages, headings and text — but the download and the share sheet run through
`expo-file-system` and `expo-sharing`, neither of which has a real implementation
under Jest. What is proven is the authenticated download, the app-private cache
location, the cleanup, the filename and what happens when a platform offers no
share sheet. Actually opening the share sheet is on the by-hand list.

**A report PDF is typeset in the PDF standard fonts, which cover Latin-1 only.**
Typographic punctuation is folded to ASCII on the way in, and anything the font
cannot draw becomes `?` rather than vanishing — so a name in Arabic or Devanagari
will not render. The fix is one setting and no code: point `REPORT_FONT_PATH` at
a TrueType font and every glyph in it renders. Report text is also English only;
the date and count wording is hand-rolled to be locale-independent, which is what
makes the output reproducible, and translating it starts in
`backend/app/services/appointments/wording.py`.

**Symptom photos are not included in reports.** PRD 7 section 28 permits
deferring them and they are deferred: a photo is the one thing in Nura that never
leaves the backend without an authenticated check on every byte, and putting one
in a shareable PDF would remove that. The selection screen says how many exist so
nobody thinks they were lost.

**Nura has never spoken to a real model.** The Anthropic adapter is written
against the current SDK and type-checks against it, and its request shapes,
streaming call, error translation and reply parsing are all tested offline. But
there is no API key in this environment and the whole suite runs against a
scripted provider, so no request has reached Anthropic from this repository. The
deterministic half of the safety work — the emergency phrase short-circuit,
serious-mode detection, the placed guardrail sentences, instruction refusal — is
provider-independent and would behave identically against any model. The prompt
half has never been evaluated against one.

**Nothing scrubs what the model says, and that is deliberate.** There is no
filter that removes a diagnosis from a reply. A regular expression catching most
ways of saying "you have migraine" would let the rest through while making
everyone believe none got through, and a guarantee that half works is worse than
one that is honestly absent. What keeps Nura inside the boundary is the tools it
does not have, the deterministic policy, and the prompt — set out, with this
limitation, in
[assistant-safety.md](docs/architecture/assistant-safety.md#what-is-not-enforced).

**Nura speaks English, has no voice, and does not listen.** The voice and
speaking-speed settings are stored for a future that can speak; the screen says
so rather than offering a control that does nothing. There is no microphone, no
speech recognition and no text-to-speech anywhere in the app, and language offers
English only rather than faking translation.

**Serious-mode detection is high-precision and low-recall on purpose.** "Should
I stop taking my tablets?" triggers it; a vaguer version of the same question
does not, and is handled by the prompt instead. PRD 8 section 38 warns against
treating every health question as an emergency, so widening the patterns is a
trade rather than a free improvement.

**The app has not been run on a physical device or emulator.** The bundle
compiles and the suites pass, but no run on real hardware has happened yet.

**There is no penetration test and no compliance certification.** PRD 13 added
a cross-boundary security suite that walks every owner route in the application
with the wrong caller, plus regression tests for cache isolation, sensitive
logging and private media. That is evidence about the boundaries this code
enforces. It is not an audit, and nothing here claims HIPAA, FDA, ISO or SOC 2
anything.

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
