# Privacy, security and reliability

One layer over the features PRD 0–12 built. PRD 13 added almost no behaviour:
it added a hub, an export, a deletion path, and — more valuably — it found and
fixed three things that were already wrong.

This document is the reference for all four. The data classification is in
[data-retention.md](data-retention.md); the decisions are in
[ADR 0016](../decisions/0016-privacy-export-deletion-and-reliability.md).

---

## 1. What this stage actually found

Worth putting first, because it is the part that mattered.

**A profile switch left the previous person's data in the cache.**
`PROFILE_SCOPED_KEY_PREFIXES` is the list of TanStack Query key prefixes
removed when the app switches which person is on screen. It had stopped being
maintained: **twenty-six keys were missing or wrong**, from PRD 3, 5, 6, 7, 10
and 12. Switching from one supported person to another left the previous
person's health record, dose history, adherence figures, symptom entries,
appointment questions, doctor reports, check-in, safety status, tasks and
routines rendered from cache. Two of the entries that *were* present —
`health-summary` and `health-records` — matched nothing at all, because the real
keys are `['health', 'summary', …]` and a prefix is compared element by element.

**Signing out cleared the cache and nothing on disk.** Seventeen AsyncStorage
keys and seven persisted stores survived a sign-out: symptom drafts,
appointment forms, caregiver message drafts, the assistant composer, the Today
cache and every offline queue. A second person signing in on the same phone
inherited all of it.

**There was no deletion path at all**, and a naive one would have orphaned
every private file. 68 foreign keys cascade from a profile and not one can
reach object storage.

None of the first two was found by reading the lists. They were found by
writing tests that read the *source* and required every key to be classified —
which is why those tests exist and why they assert in both directions.

---

## 2. The Privacy & Security hub

`More → Privacy & Security`, reading `GET /privacy/summary`.

**It owns no settings.** Every control is a link to the screen that already
owns it — caregiver permissions, memory, conversation history, Nura Device,
Safety Monitoring, Nura's modes — and every claim is a sentence the server
sent. A hub that kept its own copy of what a caregiver can see would eventually
disagree with the permissions that actually apply.

Capability rows come from the three maps that already exist: PRD 10's seven
safety capabilities, PRD 11's twelve device capabilities, PRD 12's three
external ones. Each row carries the machine state *and* the words, so a client
can style it without parsing prose — which is what keeps the prose free to
change.

Two sentences on it are there because nobody would think to ask for them:

> Privacy Mode changes how Nura behaves in the app. It is not a hardware
> switch, and it does not claim to turn off a microphone or a camera.

> Nura has not yet been tested on a physical phone or a physical robot. Where
> something has not been verified, the app says so rather than assuming it
> works.

The camera and microphone rows say what Nura has **never asked for** rather
than what it has turned off. There is no voice input anywhere in the app, so
"microphone: off" would be a claim about hardware nobody queried.

**The hub does not import the robot package.** PRD 11's architectural rule is
that nothing under `app/services` outside `services/robot` reaches into it, and
a test enforces it. So the robot's capability states and preview levels are
read in `api/v1/privacy.py` — the layer that already reads them for the Nura
Device screen — and handed to `services.privacy.summary` as an argument.

---

## 3. Export

`POST /privacy/export` builds an archive and returns the finished row.

**Synchronous, deliberately.** §20 allows it and §48 asks for no unnecessary
worker. An archive is a few dozen kilobytes of JSON plus whatever photos and
report PDFs exist, assembled from queries the backend already runs on every
screen. A worker would add a queue, a state machine, a poll loop and a failure
mode to a job that finishes inside a request. `requested` and `generating` stay
in the status vocabulary so a later build needs no migration.

```text
nura-export.zip
├── manifest.json
├── profile.json        account, settings, profile, roles, Today cards, check-ins
├── health.json         conditions, allergies, procedures, notes, clinicians
├── medications.json    medications, schedules, times, doses, supply
├── symptoms.json       episodes, entries, photo metadata
├── appointments.json   appointments, questions, reports
├── assistant.json      preferences, memories, conversations, messages
├── caregivers.json     caregivers, permissions, suggestions, threads, messages, contacts
├── safety.json         sessions, events, escalation attempts, alerts
├── daily-life.json     tasks, reminders, occurrences, alarms, routines, runs, completions
├── devices.json        devices, capabilities, presentation preferences
└── files/
    ├── photos/<id>.png
    └── reports/<id>.pdf
```

### What makes it free of secrets

Not a strip-list. `services/privacy/tables.py` states, for **every table**,
which columns are exported and which are excluded *and why* — and
`test_privacy_export.py` walks the live metadata and asserts that for each
table, exported plus excluded is exactly the column set. A column a later PRD
adds is unclassified, and unclassified fails. A future PRD cannot ship a table
change without someone deciding which side of the line each column falls on.

Three kinds of thing are excluded:

| kind | examples | why |
|---|---|---|
| secrets | `invite_token_hash`, `device_token_hash`, `bootstrap_secret_hash`, `auth_provider_id` | A hash in a file somebody emails themselves is a hash somebody can attack offline. |
| internal addresses | `storage_key`, `file_storage_key`, `attachment_key` | Meaningless outside Nura's storage, and an invitation to try requesting it. The media itself *is* exported, under `files/`, and the row carries its archive-relative path instead. |
| other people's identifiers | `caregiver_account_id`, `sender_account_id`, `recipient_account_id`, `actor_account_id` | A caregiver is a person with their own account, and this archive belongs to somebody else. What goes in is the name the user typed and which side a message came from. |

Three tables are exported as nothing, with the decision written down:
`device_presentations` (Nura's working state, every card built from data that is
in the archive in full), `provisioning_sessions` (a single-use token with an
expiry, consumed in minutes), and `data_exports` itself. The two audit tables
are excluded as a *category*, and the manifest says so with a reason rather
than leaving it to be inferred.

### Deterministic, private, temporary

**Deterministic** (§18): every table ordered explicitly, JSON keys in the order
`tables.py` declares, datetimes ISO-8601 in UTC, decimals as strings, and zip
members with a fixed timestamp. Two exports of unchanged data are byte-identical
apart from the manifest's generation time — which is what makes "has my data
changed" answerable by comparing two archives.

**Private** (§18, §27): served by an authenticated route, never a signed URL.
There are **no signed URLs anywhere in Nura** — PRD 6 chose authenticated
routes for symptom photos on the grounds that a signed URL is a bearer token in
a query string that lands in logs and share sheets and stays valid whoever ends
up holding it, and PRD 7 followed for report PDFs. An export would be a bearer
token for somebody's entire record, so the same choice is the obvious one. The
profile is re-checked for every byte, and the response carries
`Cache-Control: private, no-store`.

**Temporary** (§18, §25): 24 hours, and the expiry is compared **on every
read** rather than relying on a sweep. `scripts/privacy_maintenance.py` marks
expired rows and deletes their bytes; nothing depends on it running, which puts
it in the same category as `robot_maintenance.py` and the opposite of
`safety_maintenance.py`.

**One at a time** (§41, §53): an export is a full copy of somebody's record,
and a screen that can produce them faster than they expire is a way to fill a
disk. Asking again while one is ready is refused with the id of the one that
exists, rather than silently replacing a download somebody may be part way
through.

---

## 4. Deletion

`POST /privacy/delete-request` then `POST /privacy/delete-confirm`.

**The first step changes nothing.** It returns what would go, counted from the
database table by table, plus the phrase the second request must carry. The
warning somebody reads is therefore the scope the service actually has rather
than a paragraph written once and left behind.

**The order is fixed, and it is the reason this service exists:**

```text
enumerate → read the storage keys → delete the rows → delete the files
```

68 foreign keys cascade from a profile and **not one of them can reach a file**.
Symptom photos, report PDFs and export archives live in private object storage;
the database knows their keys and nothing else. A delete that let PostgreSQL do
the work would leave every photo and every PDF on disk with nothing pointing at
it — unreachable through the API, and still there. So the keys are collected
*before* the rows go, because afterwards there is no way to find them, and the
files are deleted *after* the transaction commits, because a file removed for a
transaction that then rolled back cannot be undone.

### What goes, and what stays

| goes | stays |
|---|---|
| the profile and everything cascading from it: health record, medications, symptoms, appointments, reports, conversations, memories, caregiver relationships and permissions, suggestions, threads and messages, emergency contacts, safety sessions and events, tasks, reminders, alarms, routines, exports | the **account**, so somebody can still open Nura |
| every private file: symptom photos, report PDFs, export archives | **other profiles on the same account**, untouched |
| caregiver access, immediately — the relationship cascades, so their routes stop resolving a scope | a **claimed robot**, which stays claimed by the account and goes back to being set up for nobody |

The account surviving its last profile is deliberate: an account with no
profile is exactly where a new sign-up starts, and signing somebody out of a
session whose token is valid for another hour is not a deletion's business.

A robot is **unlinked, not unclaimed**. The robot on the shelf still belongs to
the person who bought it, and PRD 2's claim is what says so.
`owner_profile_id` is nullable precisely for the "claimed but set up for
nobody" state.

### Re-authentication, and the documented limitation

§21 asks for re-authentication "if already supported". It is not. Nura verifies
Supabase access tokens against a JWKS endpoint and never receives a password,
so there is nothing here to check one against. §44 anticipates this and asks
for strong explicit confirmation plus a documented limitation.

The confirmation is two required fields with no defaults — the exact phrase
`DELETE MY NURA DATA`, compared with no trimming and no case folding, and a
separate `acknowledged` boolean — so an empty body or a replayed request cannot
delete anything. The limitation is said **on the screen**, not only here:

> Nura cannot ask you for your password again: it never receives one. Anyone
> holding this phone while you are signed in can complete this, which is why it
> asks you to type the phrase exactly.

That is the honest statement of what the phrase does: it stops a mis-tap, not
an intruder.

---

## 5. Authorization

### The three paths, unmerged

Classifiable straight off the dependency tree, which is how
`test_security_matrix.py` enumerates them:

| path | dependency | count |
|---|---|---|
| owner | `get_owned_profile` | 169 |
| caregiver only | `get_caregiver_scope` | 5 |
| owner **or** caregiver | `get_care_scope` | 8 |
| device | `get_current_device` | 6 |
| account level | `get_current_user` | 27 |
| open | — | 3 |

218 routes. The three open ones are the version endpoint, the device claim and
the permission-category catalogue.

**Every route carrying `{profile_id}` resolves one of the three profile
dependencies.** A route that took a profile id and only required a signed-in
account would let any account read any profile by guessing a UUID; such a route
cannot exist without failing a test, whichever PRD writes it.

PRD 13 moved `GET` and `PATCH /profiles/{profile_id}` onto `OwnedProfile`. They
were safe — a local helper walked the same join table — but two
implementations of one authorization rule is what §13 is about, and the shared
dependency is the one the security suite can *see*.

### The one load-bearing suite

Every stage from PRD 9 onwards wrote its own denial test against a hand-typed
list of paths. Each was correct and none covered the next stage's routes. §51
asks for one suite, and the way to make one load-bearing is to stop typing the
list: `owner_routes()` asks the application, and the cross-profile and
caregiver walks request **every owner route** with the wrong caller and require
404 from each. A route PRD 14 adds is in those loops the day it is written.

One assertion makes the rest mean anything: `test_every_route_in_the_walk_exists`
compares the walked paths against the OpenAPI schema. A path the walk got wrong
does not exist, every request against it answers 404, and a suite asserting
"the wrong caller gets 404" would then pass for routes it never reached. It
did, for nine health-record routes nested two routers deep, until that check
was added.

The matrix, as §14 asks for it:

| case | result | where |
|---|---|---|
| owner → own profile | allowed | the feature suites |
| owner A → owner B's profile | 404 on all 169 owner routes | `TestCrossProfile` |
| caregiver with every permission → owner route | 404 on all 169 | `TestCaregiverBoundary` |
| caregiver with permission → care route | allowed | `TestCaregiverBoundary` |
| caregiver without permission | 404 | `TestCaregiverBoundary` |
| revoked caregiver | 404 on the next request, nothing invalidated in between | `TestCaregiverBoundary` |
| device → another device | refused | `TestDeviceBoundary` |
| account token → device route | 401 | `TestDeviceBoundary` |
| assistant tool → another profile | no tool takes a profile argument | `TestAssistantBoundary` |
| another account → private media | 404; unauthenticated 401 | `TestPrivateMedia` |

### The caregiver-reachable surface, written out

Thirteen routes of 218, each with a stated purpose, asserted by **equality** so
the list cannot rot in either direction. Adding a fourteenth fails the suite
until somebody says what it is for.

Five are caregiver-only (their own surface: `care/home`,
`care/notifications`, `care/routines`, and proposing or withdrawing a
suggestion) and eight accept either side, because PRD 9 chose that shape for a
two-sided conversation — family threads and messages, the calling refusal, the
suggestion list, and PRD 10's two alert routes.

---

## 6. Sensitive logging

§12 names eleven classes of content that must never reach a log line.
`test_privacy_logging.py` attaches a capture handler to the whole `app` logger
tree at `DEBUG`, drives one write per domain through the real HTTP routes, and
asserts none of the distinctive strings came out.

It captures at `DEBUG` on purpose: §52 is about release configuration not
enabling verbose logs with sensitive content, and the way to be sure is to
capture the most verbose level and find the content absent even there.

**Two traps worth recording.** Alembic's `env.py` calls
`fileConfig(alembic.ini)`, which defaults to `disable_existing_loggers=True`,
so every application logger is switched off for the whole pytest session — and
`disabled` is set on each logger object individually, so clearing it on `app`
leaves `app.services.privacy.export` silent. A capture handler on a disabled
logger records nothing, and every "this content is absent" assertion then
passes while proving nothing. The fixture re-enables every `app.*` logger, and
the suite asserts that *something* was logged alongside asserting what was not.

Invitation tokens are checked too, though §12 does not list them: an invitation
token grants caregiver access to somebody's medical record, and PRD 9 stores it
hashed for that reason.

---

## 7. Offline and degraded behaviour

### One retry policy

Five features each had their own `RETRYABLE` list and their own `isRetryable` —
medications, symptoms, appointments, daily life, the daily check-in — and all
five were already identical. So `features/reliability/retry.ts` is a
de-duplication rather than a change, and it is the one place §57's "at least
two systems genuinely reuse it" is unarguable.

The policy, as §30 states it:

| failure | behaviour |
|---|---|
| transport (`offline`, `unavailable`, `timeout`) | retry |
| server (`server`, `unknown`, `configuration`) | retry |
| auth (`unauthorized`) | retry — the request stops, the app routes to sign-in, and the queued action survives it |
| validation | stop, and surface. The server will refuse the same body forever |
| conflict | stop. The resolver has already decided |
| not found | stop. The thing being acted on is gone |

The list is of what *is* retryable, so a new `ApiErrorKind` is non-retryable
until somebody decides otherwise — it surfaces rather than spins. A test
asserts exhaustiveness against the union as written in the source, and that
none of the five queues has grown its own copy back.

### Queues, and where they are flushed

| queue | holds |
|---|---|
| `nura.checkin.pending` | a check-in answered with no signal |
| `nura.medications.pendingActions` | doses taken, snoozed or skipped offline |
| `nura.symptoms.pendingEntries` | symptom entries, and photos waiting to upload |
| `nura.appointments.pending` / `pendingQuestions` | appointments and doctor questions |
| `nura.productivity.pendingTasks` / `pendingTaskActions` / `pendingReminders` / `pendingSteps` | PRD 12's four |

PRD 13 mounted the daily-life sync on **Today and Care** as well as
`/daily/*`. The other four were deliberately given that "second chance after
being offline" — their own comments say so — and PRD 12's never got it, so an
action queued on a daily-life screen followed by a restart that landed on Today
left four queues unflushed until somebody happened to reopen `/daily`.

Caregiver messages and suggestions are **drafts, not queues**: PRD 9 chose to
keep what somebody typed and say it has not been sent, rather than promising to
send it later. That is still the right answer and PRD 13 did not change it.

### Degraded wording

`DegradedModeBanner` takes a `kind` rather than new copy per screen:
`offline`, `unavailable`, `pending`, `robotOffline`. PRD 3's `OfflineBanner` —
used on ten screens — is now a thin call into it.

Every sentence states the fact and then what still works, because a banner that
states only the fact leaves somebody to guess the consequence and they usually
guess worse than it is. "Nura Device is offline. App features are still
available." is §34's own example.

§34 allows a high-risk feature to override, and PRD 10 does: its own
`OFFLINE_BODY` says Nura cannot record or send an emergency request and to call
somebody directly. That is a stronger claim than a generic banner should make,
and it stays where it is.

### No false success

§35's rule is held everywhere it has been built, and was before this stage:
"sent to Nura" rather than "shown", `attempted` rather than `delivered`, "saved
on this phone", `not_configured`, `not_verified`. The privacy screens are held
to it too — the export screen says "ready" and never "saved", because what a
phone does with downloaded bytes is the phone's business.

---

## 8. Session and cache isolation

**Sign-out** clears the Supabase session, the Zustand account state, the whole
query cache, and — new in PRD 13 — every local store, through an inventory in
`features/privacy/localData.ts` that groups seventeen keys into pending queues,
caches, notification mirrors, drafts and context. It is a list rather than
`AsyncStorage.clear()`, because removing another library's state on sign-out is
the kind of fix that works until it breaks something unrelated. The two auth
keys are excluded with a reason: the auth service clears them through secure
storage, and listing them would mean removing them twice.

**A profile switch** removes the profile-scoped query keys rather than
invalidating them. `removeQueries`, not `invalidateQueries`: an invalidated
query keeps serving its old value while it refetches, which is exactly the
stale flash PRD 9 §58 forbids.

PRD 11's four robot keys are scoped by **device id**, not profile. A device is
claimed by an account and no caregiver route reaches one, so switching which
person is on screen does not change which robot is theirs. They are in the
documented account-scoped list rather than quietly added to the clear.

Both lists are guarded by drift tests that read the source — every `queryKey`
literal, every `'nura…'` storage key — and require each to be classified, in
both directions. The reverse direction is not theoretical: it is what caught
`health-summary` matching nothing.

---

## 9. API and upload security

Reviewed rather than rebuilt (§41, §42), and all of it predates this stage:

- **CORS** is an allowlist, `*` only when `APP_ENV=development` and no origins
  are configured.
- **HTTPS** outside local development; the release build refuses `http://`.
- **Uploads** validate the MIME type by sniffing the bytes rather than trusting
  the header, cap at 6 MiB and five photos per entry, and build the object key
  server-side from ids the server generated.
- **Path traversal** is refused twice: a narrow regex, then a resolved-path
  check against the media root that also catches a symlink out of the tree.
- **Rate limits** exist where a request costs something: the assistant is
  limited per profile per hour from the rows it already writes, caregivers are
  capped at ten per profile, and PRD 13's export is one at a time.
- **Authorization failures are uniform**: 404 at every depth, so an id is never
  confirmed to exist.

---

## 10. What is still not true

Unchanged by this stage, and restated because a privacy document is the wrong
place to be vague:

- **No notification, alarm or vibration has ever fired**, and no
  operating-system background behaviour has been observed. The app has never
  run on a physical phone.
- **No frame has been drawn on a robot's panel**, no sound has been played, and
  no physical acknowledgement has ever reached the backend.
- **No external provider is configured** — no weather, news or external
  calendar — and `providers.IMPLEMENTED` is empty, so no configuration can
  change that.
- **No push, SMS or calling provider exists**, so nothing has ever reached a
  person outside the app.
- **No penetration test and no compliance certification.** PRD 13 added a
  security regression suite, which is evidence about the boundaries this code
  enforces and nothing more.

---

## Related

- [data-retention.md](data-retention.md) — the data classification, and how
  long each category lives
- [ADR 0016](../decisions/0016-privacy-export-deletion-and-reliability.md) —
  why it is shaped this way
- [caregiver-and-family.md](caregiver-and-family.md) — the second
  authorization path this stage tests exhaustively
- [health-data.md](health-data.md) — the records an export contains
- [API reference](../api/README.md) — the privacy endpoints
