# 0008 — Medication scheduling, doses and reminders

**Status:** Accepted · PRD 5

## Context

Nura has to remind somebody to take a medication at the right time, record
what they did about it, and survive a phone that is offline, a clock that
changes twice a year, a person who travels, and eventually a robot that thinks
it heard "I took it". Six decisions shaped how.

## Decision 1 — a schedule carries its own IANA time zone

`medication_schedules.timezone` holds a name like `Europe/London`, and dose
generation resolves *local date + local wall-clock time in that zone* into a
UTC instant.

A reminder is a wall-clock time, not an instant: "eight in the morning" means
eight where the person is, in March and in July. Storing an offset instead is
wrong twice a year, and wrong in the two directions that matter — a dose
fires an hour early, or a dose does not fire at all.

Taking the zone from the phone at read time was the alternative, and it is
worse: someone who travels for a week would find their 8am reminder following
them, which is exactly the "travel must not silently create duplicate doses"
problem PRD 5 section 12 names. The zone belongs to the schedule, and changing
it is an edit the user makes deliberately.

The two awkward days a year are decided rather than left to a library
default. Resolution uses `fold=0`: a local time that does not exist resolves
through the pre-transition offset (one dose, never zero), and one that happens
twice resolves to the earlier occurrence (one dose, never two). Both are
tested against real transitions in `Europe/London`.

## Decision 2 — doses are rows, generated ahead

Concrete `medication_doses` rows are created 14 days ahead rather than a
recurrence rule being evaluated on every read.

Three readers need the same answer: "what is due today", "what did I miss",
and the phone's local notification schedule. Re-deriving a recurrence rule in
three places is three chances to disagree, and the third one runs inside the
operating system where a disagreement is invisible. A row also gives every
dose a stable id, which is what makes an action idempotent and an offline
queue possible at all.

Generation is **forward-only** — nothing before `now` is ever created — so a
schedule made at 10am cannot retroactively produce, let alone miss, this
morning's 8am.

The cost is rows: roughly 14 per schedule per fortnight, topped up on read.
That is nothing, and it buys a system where the hard part happens in one
function.

## Decision 3 — replenish on read, with cron as a safety net, not a dependency

`replenish()` runs at the top of every read of Today, the dose list and
adherence. `scripts/medication_maintenance.py` does the same for every profile
and is meant for cron.

An app that is opened is therefore always correct, with no infrastructure at
all. PRD 5 section 71 warns against adding heavy distributed machinery for
this, and a prototype that needed a worker running to be truthful would be a
prototype that is quietly wrong on anybody's machine but ours.

The job exists for the profile nobody opened: somebody whose phone was off for
a week should find last Tuesday recorded honestly rather than sitting as
`scheduled` forever. Nothing depends on it having run.

## Decision 4 — an action sets a state on one row

Taken, Snooze and Skip update the dose. They never append an event beside it,
and there is no `PATCH /doses/{id}` that takes a `status`.

This one decision covers most of what PRD 5 sections 25, 48 and 49 ask for:

- A retried request finds the dose already taken, returns `applied: false`,
  and **does not decrement supply twice.**
- Taking a dose hours late keeps the same row and records `action_at`. There
  is no second, "late" dose; `late` is derived on read.
- The app marks Taken and the robot says so afterwards: the robot is agreeing,
  not correcting. One Taken in the history, and no error shown to anybody.

A source other than `app` never overwrites a completed dose, so a robot that
mishears cannot rewrite what somebody recorded about their own medication.

The event-log alternative would have needed a projection to answer "what is
this dose's state", and every one of the guarantees above would have become a
rule in that projection rather than a property of the schema.

## Decision 5 — editing withdraws the future and never touches the past

A schedule edit deletes future doses nobody has touched, marks snoozed future
doses `cancelled`, and regenerates — in one transaction. `schedule_id` on a
dose is `ON DELETE SET NULL`, not a cascade.

The distinction between deleting and cancelling is the point. A future dose
nobody interacted with carries no history, so deleting it loses nothing and
keeps the table clean. A dose somebody *snoozed* is something they did;
quietly deleting it would erase an action they took. `cancelled` is excluded
from adherence, so it counts against nobody either way.

The cascade would have been simpler and is wrong: deleting a schedule must
stop future reminders without erasing months of somebody's recorded history.
The same reasoning produces the `409 medication_has_history` refusal on PRD
4's medication delete — a medication somebody has been taking is archived by
marking it inactive, not erased.

## Decision 6 — reminders are local notifications, rebuilt rather than accumulated

The phone mirrors the next 48 waiting doses into the OS scheduler.
`rebuildReminders()` reconciles what the OS holds against what the doses say:
unchanged reminders are left alone, moved ones are cancelled and re-created,
and an empty plan cancels everything.

Local rather than push, because the backend already knows the schedule and a
push service would mean medication names leaving the phone for no benefit
(PRD 5 sections 41 and 58). One channel, so the same dose cannot be announced
twice.

Reconciling rather than rescheduling is what makes a pause, a delete, an
inactivated medication and a time change all work without a special case each:
they all arrive as "fewer doses", and the reminders for what is gone come
down.

**No notification action buttons.** PRD 5 section 16 allows them only where
they are reliable and says plainly not to fake unsupported ones. Acting on a
notification would have to reach the backend from a background handler, which
this app cannot promise on both platforms, so tapping a reminder opens Nura
where Taken, Snooze and Skip are real buttons. An honest reminder beats a
button that sometimes does nothing.

## Consequences

- The recurrence rules are pure functions and are tested directly, including
  both daylight-saving transitions and a timezone change that must not
  duplicate a day.
- There is exactly one definition of adherence, one grace period and one set
  of snooze durations, each in one file, mirrored in the app with a test that
  asserts they still match.
- An offline action queue can hold one final answer per dose rather than a log
  of taps, because the server holds one row per dose.
- The robot's future voice confirmation is a real authenticated contract that
  is tested with a seeded device token, and nothing in the product depends on
  it ever being called.
- What PRD 5 deliberately cannot express — tapering, sliding scales, dose
  calculation, interaction checking — is not expressible anywhere in the
  model, rather than being omitted from the UI and reachable through the API.
