# The medication system

How Nura turns a medication *record* into a set of reminders, what happens at
each reminder, and what it deliberately refuses to do.

This covers PRD 5: schedules, doses, the Taken / Snooze / Skip actions, missed
doses, adherence, supply and refills, offline behaviour, and the future robot
voice hook. The medication *record* itself — name, dose, form, prescriber —
belongs to the health record and is covered in [health data](health-data.md).

> **None of this needs the robot.** Every medication feature works with no
> robot linked, with one that is offline, and with one the backend has heard
> from. The one robot-facing route is a real, authenticated contract with no
> hardware behind it yet, and nothing in the product depends on it being
> called. No medication data is ever sent over BLE or embedded in a
> provisioning payload.

---

## Record versus schedule

These are three different things, in three different tables:

```text
medications          what it is            (PRD 4 — untouched by PRD 5)
    │
    ├── medication_schedules        when to remind
    │       └── medication_schedule_times   the times within that pattern
    │
    ├── medication_doses            one concrete moment, and what happened
    │
    └── medication_supply           how many are left
```

A medication may have no schedules, one, or several. "One at night" and "two
in the morning on weekdays" are two schedules for the same medication, not one
schedule with a special case inside it.

Keeping them apart is what stops a medication record from quietly becoming an
instruction. Deleting a schedule does not touch the record; marking the record
inactive pauses the schedules; neither erases a dose anybody recorded.

---

## The schedule model

| Column | Meaning |
| --- | --- |
| `schedule_type` | `daily` or `specific_days` |
| `timezone` | IANA name, e.g. `Europe/London` |
| `start_date`, `end_date` | Local calendar dates; `end_date` null means ongoing |
| `is_active` | The pause switch |
| `times[]` | `time_of_day`, plus `weekday` on a `specific_days` schedule |

Only two patterns exist, because those are the two PRD 5 asks for. Several
times a day is not a third type — it is several `times` rows. A date range is
a start and an end on either type. "9am on Mon, Wed and Fri" is three rows,
built from the days and times the user chose.

**Out of scope, and not expressible anywhere in the model:** tapering, sliding
scales, insulin or weight-based dose calculation, infusion schedules,
chemotherapy cycles, interpreted PRN dosing, and interaction checking. An "as
needed" medication stays a record with no schedule.

---

## Time zones

**A reminder is a wall-clock time, not an instant.** "Eight in the morning"
means eight where the person is, in March and in July alike. So the schedule
carries an IANA zone, and dose generation resolves *local date + local time in
that zone* into a UTC instant. Storing an offset instead would be wrong twice
a year, in the direction of either a missed dose or a doubled one.

Everything is stored in UTC (`scheduled_for` is `timestamptz`); the local
calendar day the dose belongs to is stored alongside it as `local_date`, so
"today's medications" and a day of history are one indexed comparison rather
than timezone arithmetic per row.

### The daylight-saving policy

Resolution uses Python's `fold=0`, which settles both awkward days:

| Case | Example | Result |
| --- | --- | --- |
| Time does not exist | 01:30 on a spring-forward day | Resolved through the pre-transition offset — the instant it would have been had the clocks not moved, which reads an hour later on the clock. **One dose, never zero.** |
| Time happens twice | 01:30 on an autumn day | The earlier of the two occurrences. **One dose, never two.** |

Verified in `backend/tests/test_medications.py`: 8am stays 8am across the
spring change in `Europe/London` while the underlying UTC instant moves from
08:00Z to 07:00Z, and both awkward days produce exactly one occurrence.

### Travel

A schedule's zone changes only when the user edits the schedule, and an edit
*regenerates* its future doses rather than reinterpreting the existing ones.
So changing zones cannot produce two doses for one day — there is a test that
asserts exactly that. A unique constraint on `(schedule_id, scheduled_for)`
backs it up in the database.

---

## Dose generation

Doses are **rows, generated ahead of time**, not a recurrence rule evaluated
on every read. That way "what is due today", "what did I miss" and the local
notification schedule all read the same thing.

- **Horizon:** 14 days ahead (`GENERATION_HORIZON_DAYS`).
- **Forward only.** Nothing before `now` is ever created. A schedule made at
  10am does not retroactively produce — let alone miss — this morning's 8am,
  because there was nothing to remind anybody about at 8am.
- **Idempotent.** A moment that already has a dose row, in any status, is left
  exactly as it is.

### Replenishment, without a background worker

`replenish()` tops the window up and records missed doses. It runs at the top
of every read of Today, the dose list and adherence — so **an app that is
opened is always correct, and nothing depends on a scheduled job having run.**

`backend/scripts/medication_maintenance.py` does the same for every profile
and is meant for cron (or a deployment's own scheduled task) so that somebody
whose phone has been off for a week still finds last Tuesday recorded
honestly. It is idempotent; hourly is plenty.

```bash
python -m scripts.medication_maintenance
python -m scripts.medication_maintenance --dry-run
```

---

## Status transitions

```text
                  ┌──────────── snooze ────────────┐
                  │  (≤ 3 times, 10 / 30 / 60 min) │
                  ▼                                │
  scheduled ──────────────────────────────────► snoozed
      │                                             │
      │  grace period (2h) with nothing recorded    │
      ▼                                             ▼
   missed ◄──────────────────────────────────────────
      │
      │  Taken / Skip stay available indefinitely
      ▼
    taken   or   skipped          cancelled  (future dose withdrawn
  (terminal, correctable)                     when a schedule changes)
```

| Status | Meaning |
| --- | --- |
| `scheduled` | Waiting |
| `snoozed` | Put off; still unrecorded |
| `taken` | The person recorded taking it |
| `skipped` | The person recorded not taking it, optionally with a reason |
| `missed` | The grace period passed with nothing recorded |
| `cancelled` | A future dose withdrawn because the schedule changed |

**Grace period: 2 hours.** Deliberately generous — somebody who takes a tablet
with breakfast an hour late has not missed it. It is a bookkeeping threshold
and nothing follows from it.

**A snoozed dose is measured from its snooze**, not from the original time, so
snoozing genuinely buys the time it says it does.

**A late Taken keeps the same row.** Taking a dose long after it was due sets
`status = taken` and records `action_at`; `late` is derived on read from
`action_at > scheduled_for + grace`. There is never a second, "late" dose.

### Time windows

Derived on every read from the clock — never stored, for the same reason a
robot's connection status is never stored:

| Window | When |
| --- | --- |
| `upcoming` | more than 30 minutes before it is due |
| `due` | from 30 minutes before, until the grace period is up |
| `overdue` | past the grace period and still unrecorded (including `missed`) |
| `completed` | `taken`, `skipped` or `cancelled` |

---

## Idempotency and concurrency

An action **sets a state on one row**; it never appends an event beside it.
That single decision covers most of what PRD 5 sections 48 and 49 ask for:

- Re-sending Taken finds the dose already taken. `applied: false` comes back,
  the stored dose comes back with it, and **supply is not decremented twice.**
- The app marks Taken, and the robot says "I took it" afterwards: the robot's
  confirmation is agreement, not a correction. Nothing changes, nothing
  errors, and there is one Taken in the history.

**A source other than `app` never overwrites a completed dose.** A robot that
mishears cannot rewrite what somebody recorded about their own medication.

### Editing a schedule

Editing withdraws future doses and regenerates them, in one transaction:

- A future dose nobody has touched is **deleted** — no history is lost,
  because nothing ever happened at it.
- A future dose the user has **snoozed** becomes `cancelled` instead. They
  interacted with it, and quietly deleting that would erase something they
  did. `cancelled` is excluded from adherence, so it counts against nobody.
- Anything already taken, skipped or missed is never touched — including
  earlier the same day.

Deleting a schedule does the same and then removes the schedule;
`medication_doses.schedule_id` is `ON DELETE SET NULL`, not a cascade, so the
doses it produced keep their status, their times and their source forever.

Pausing (`is_active = false`) withdraws future doses and stops generation
while keeping everything recorded. Resuming starts generating again.

---

## Adherence

One number, one definition:

```text
taken / (taken + skipped + missed)
```

Cancelled doses are excluded — nobody was ever asked to take them — and so is
anything still in the future, which would otherwise drag the figure down as
the day went on. The counts are returned alongside the percentage so the app
can state the denominator, and `percent` is **null** when nothing was due: 0%
for a week with no doses would say something about the person that the data
does not.

It is not a score, not a grade and not a clinical measure. Nothing in Nura
calls it adequate or inadequate, sets a target, or draws a conclusion from it.

---

## Supply and refills

Opt-in per medication. A count nobody keeps up to date is worse than no count
at all, so Nura never turns it on by itself.

| Column | Meaning |
| --- | --- |
| `tracking_enabled` | Off until the user asks for it |
| `remaining_doses` | The user's own count |
| `refill_threshold_doses` | Warn at or below this. Null means never warn. |
| `last_refill_date` | When they last picked one up |

- **Only Taken moves the count.** Snooze, Skip and Missed leave it alone — a
  dose that was not taken is still in the packet.
- It **stops at zero** rather than going negative.
- Correcting a taken dose to skipped puts one back. Best-effort: it can only
  act on tracking that is on now, and the count stays editable by hand.
- A refill **replaces** the count rather than adding to it, because people
  count what is in front of them.
- Nura warns in cautious words ("You have about 5 doses of Metformin left")
  because the number came from a person estimating. It never estimates how
  long a supply will last, never orders anything, and never contacts a
  pharmacy.

---

## Reminders on the phone

**OS-scheduled local notifications, and nothing else.** The JavaScript process
is not running most of the time, so anything depending on it would simply not
fire. The backend stays the source of truth for schedules and history; the app
mirrors the next few doses into the operating system's own scheduler.

- **Local, not push.** One channel, so the same dose cannot be announced
  twice, and no medication name ever leaves the phone to reach a push service.
- **At most 48 pending**, comfortably inside the 64 iOS allows.
- **Permission is requested when somebody turns a reminder on** — not at
  launch and not during onboarding, so the prompt arrives with an obvious
  reason attached. A refusal is handled honestly: the schedule still exists
  and the app still shows what is due; only the phone's alert is off.
- **No notification action buttons.** Acting on a notification would have to
  reach the backend from a background handler, which this app cannot promise
  on both platforms. PRD 5 section 16 says not to fake unsupported actions, so
  tapping a reminder opens Nura, where Taken, Snooze and Skip are real
  buttons.
- **Rebuilt, not accumulated.** `rebuildReminders()` reconciles what the OS
  holds against what the doses say: unchanged reminders are left alone,
  moved ones are cancelled and re-created, and an empty plan cancels
  everything. A paused schedule, a deleted one and an inactivated medication
  all arrive here as "no doses", which is why none of them needs a special
  case.
- It runs after every schedule change, and from Today for anybody who has
  schedules — which is what makes a new phone or a reinstall work: sign in,
  open the app, and the reminders rebuild from the server.

---

## Offline behaviour

**A medication action is never silently lost.** If the phone cannot reach the
backend, Taken, Snooze or Skip is written to the device and the row says so.

- The queue holds **one action per dose**, not a log of taps: pressing Taken
  and then Skip on the same dose sends one final answer, because the server
  holds one row per dose.
- Every entry carries `action_at` — when the user actually pressed it.
- It drains when a medication screen is focused and when the phone comes back
  online.
- Only transport failures are queued. A refusal the server would repeat — a
  snooze limit, a dose that is no longer scheduled — is surfaced instead,
  because retrying it later would fail identically.
- The queue stores a **dose id and nothing else identifying**; no medication
  name is written to the device by it.

### Conflict resolution

The most recent explicit user action wins, the same rule the daily check-in
uses. If the stored dose already has an `action_at` newer than the incoming
one, the stored answer stands and `applied: false` comes back with it, so the
client converges on the server rather than retrying.

Duplicate rows are impossible by construction: one dose per scheduled moment,
enforced by a unique constraint.

---

## The robot voice hook

Future behaviour: somebody says "I took it" and the robot records the dose.
The contract exists now; the hardware does not.

```http
POST /api/v1/device-actions/medication-doses/{dose_id}/taken
Authorization: Bearer <device token>
```

It lives under `/device-actions` rather than beside the app's own medication
routes because the two authenticate completely differently, and a reader
checking who can do what should not have to notice which dependency a route
used. Everything under that prefix is authenticated by a **device token** and
nothing else.

Checked on every request:

1. A device token issued at claim. A user's access token does not work here,
   and **the robot never holds one** — PRD 2 kept the user's credentials away
   from the hardware and PRD 5 keeps it that way.
2. The device is claimed **and linked to a profile**. A robot not set up for
   anybody cannot act on anybody.
3. The dose belongs to *that* profile — fetched by profile and id together, so
   nothing is loaded first and authorized second.
4. Anything else is a **404**. A robot with a valid token learns nothing about
   which dose ids exist elsewhere.
5. The action is idempotent, and never overrides what the person recorded.

The response is deliberately thin — an id, a status, and whether anything
changed. No medication name, no dose, no supply count: the robot has no use
for them, and medication data has no business in a device's memory or logs.

### Testing it without hardware

A device token is the whole of what a robot has, so a device token is the
whole of what a developer needs. In development:

```bash
python -m scripts.seed_dev --account latest --device offline
python -m scripts.seed_dev --account latest --device-token
```

The second prints a freshly issued token (the stored value is still a hash,
and rotating invalidates any previous one). There is **no pretend-robot button
anywhere in the app**, and there never will be.

---

## Privacy

- **No medication name, dose, skip reason text, adherence figure or refill
  detail is ever logged.** Every log line names the resource and the action
  and stops: `medication.dose.taken success`, `medication.schedule.create
  success`.
- No medication data is transmitted during BLE provisioning, or over BLE at
  all.
- Analytics, if it is ever added, may carry generic events
  (`medication_dose_action`, `action = taken`) and nothing identifying.
- The reminder body is built through one function, so a future privacy option
  that hides medication names on the lock screen is a flag rather than a
  rewrite.

---

## Safety boundary

Nura records what somebody does about their medication. It does not:

- recommend changing a dose, or doubling after a missed one
- advise stopping or starting anything
- decide whether a late dose should be taken
- infer side effects, or check interactions
- interpret a skip reason — "feeling unwell" changes nothing, escalates
  nothing, and produces no advice

The only sentence in the product that approaches advice points at a person:

> If you're unsure what to do after missing a dose, follow the instructions
> from your clinician or pharmacist.

It is defined once, in `mobile/src/features/medications/doses.ts`, and asserted
by a test.

---

## Where the code is

| Path | What |
| --- | --- |
| `backend/app/models/medication.py` | The four tables and their constraints |
| `backend/app/services/medications/doses.py` | Recurrence, grace period, the three actions |
| `backend/app/services/medications/schedules.py` | What a schedule may be; what editing does |
| `backend/app/services/medications/supply.py` | Counts, thresholds, refills |
| `backend/app/services/medications/adherence.py` | The formula |
| `backend/app/services/medications/summary.py` | The slice Today shows |
| `backend/app/api/v1/medications.py` | The app's routes |
| `backend/app/api/v1/device_actions.py` | The robot's one route |
| `backend/scripts/medication_maintenance.py` | The cron-friendly top-up |
| `mobile/src/features/medications/schedule.ts` | Form rules and the schedule sentence |
| `mobile/src/features/medications/doses.ts` | All the user-facing wording |
| `mobile/src/features/medications/notifications.ts` | Reminder planning and the OS scheduler |
| `mobile/src/features/medications/pendingActions.ts` | The offline queue |
| `mobile/app/medications/` | The screens |

---

## Related

- [The health record](health-data.md) — where a medication *record* lives, as
  opposed to the schedule that makes it act.
- [The symptom system](symptom-system.md) — the other feature area that joins
  Today, and which reuses several patterns from here.
- [The appointment and report system](appointment-and-report-system.md) — where
  the adherence figure defined here is quoted to a clinician, as counts and never
  as a grade.
