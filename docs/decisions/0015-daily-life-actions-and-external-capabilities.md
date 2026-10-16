# 0015 — Daily-life actions and external capabilities

**Status:** accepted and implemented. Nothing in it has run on a physical
phone.
**Date:** 12 October 2026 (PRD 12)

## Context

Through PRD 11 Nura was a health product with a robot attached. PRD 12 asks it
to become useful for ordinary days — tasks, reminders, alarms, routines — while
changing nothing about the boundaries the previous eleven stages established:
server-authoritative authorization, truthful capability states, a model that
cannot reach a health record, and a robot that is never the source of truth.

Two pressures run in opposite directions here, and most of the decisions below
are about holding both.

The first is that a daily-life feature is *easy*, and that is the danger. There
is no clinical risk in a task list, so the temptation is to be quick about it —
reuse the medication engine, let the assistant write what it likes, put the
weather on the Today screen. Each of those would break something that was
expensive to get right.

The second is that an everyday assistant is where somebody would most
reasonably expect Nura to look things up. It cannot. There is no weather
provider, no news provider and no calendar integration, and PRD 12 section 12
is explicit that a missing integration must say so rather than returning
something that looks live.

---

## Decision 1 — Four tables, not one

A task, a reminder, an alarm and a routine are four things with four different
behaviours, and section 113 says not to fold them into one ambiguous table
unless the differences stay explicit. They are separate, and the differences
are load-bearing rather than cosmetic:

| | has occurrence rows | has a time | has history worth keeping |
|---|---|---|---|
| task | no | optional | yes — completion is a record |
| reminder | **yes** | required | yes — what happened at each moment |
| alarm | **no** | required | no — nobody asks about last Tuesday's 7am |
| routine | yes (runs) | required | yes — "I did this every morning" |

The alarm row is the one worth explaining. Everything else that repeats
generates concrete rows; an alarm does not, because there is nothing worth
keeping about a moment that has gone. "Is this alarm for now" is derived from
the stored time, the stored days and the clock — the same choice PRD 2 made for
a robot's connection status, for the same reason: a value meaning *right now*
is wrong the moment it is written.

The cost is that the robot's alarm card has to carry the moment in its dedupe
key, because there is no occurrence id to use. That is one line in the builder,
and it buys a table nobody ever has to tidy.

## Decision 2 — The recurrence engine is PRD 5's, by calling it

Section 35 says to reuse PRD 5's recurrence and time-zone discipline and not to
build a second, contradictory policy. `services.productivity.recurrence` calls
`services.medications.doses.occurrence_instant` — the function itself, not the
idea — so PRD 5's two decisions about daylight saving hold for a reminder, an
alarm and a routine without being restated:

- a wall-clock time that happens twice on an autumn morning resolves to the
  first of them;
- one that never happens on a spring morning resolves through the pre-transition
  offset, so it lands the same elapsed time later and reads an hour on.

Either way exactly one occurrence exists, which is the property that matters. A
test asserts the identity of the function as well as the behaviour, so a later
refactor cannot quietly fork it.

One thing is decided here rather than reused, because PRD 5 had no reason to: a
monthly reminder on the 31st uses the last day of a short month. Eleven months
with a reminder and one without is the answer somebody who set a month-end
reminder would least expect.

## Decision 3 — Runs cover a day; doses cover a moment

This is the one place PRD 12 deliberately departs from PRD 5's generator.

A dose created at ten in the morning does not retroactively produce this
morning's eight o'clock, because there was nothing to remind anybody about at
eight. A routine is different: a morning routine is a checklist for the
morning, and somebody opening Nura at nine should be able to tick off the water
they drank at half past seven. So routine runs are generated from the start of
the local *day*, and a run stays open until its day is over.

That also gives "missed" an honest definition. A run is missed when its day has
gone — not two hours after its time — and nothing follows from it: no advice,
no score, nobody told.

## Decision 4 — Two timestamps on anything two devices can edit

Section 40 asks for deterministic conflict resolution and names the failure it
is worried about: *a completion should not be accidentally undone by an
unrelated title edit from another device.*

One `updated_at` with last-write-wins produces exactly that failure. So a task
carries two timestamps — `content_updated_at` and `status_changed_at` — and an
edit is compared against the one it touches. The field-level consequences:

- A **content** edit (title, notes, priority, due date) compares against
  `content_updated_at`. An older edit loses and the response says so, carrying
  the stored task for the client to adopt.
- A **status** change (complete, reopen, archive, cancel) compares against
  `status_changed_at`. A queued Done from an hour ago cannot undo an Archive
  made since.
- A content edit **cannot reach the status at all**. There is no `status` field
  on `TaskUpdate` — not validated away, absent — so the failure section 40
  names is unrepresentable rather than merely prevented.

`PATCH` and the four action endpoints are therefore different endpoints on
purpose, not for tidiness.

## Decision 5 — The assistant acts on four things and proposes the rest

Section 22 allows low-risk writes to execute directly when intent is complete
and unambiguous. The split is:

**Executes** — create a task, create a reminder, create an alarm, complete a
task. Each is small, appears in a list, changes nothing else, and is one tap to
undo. Asking "shall I?" for every one would make Nura slower than typing it.

**Proposes** — update a task, create a routine, pause a routine. Editing
something the person wrote, setting up a standing commitment with a schedule
and steps, and stopping something that keeps happening are all changes to
something that already exists.

Two guards sit around that:

**A missing time is a question, not a guess.** `CreateReminderArgs.time` is
required, so "remind me later" cannot reach the function — the call fails
validation and the model is told why. Nothing anywhere defaults a time, a date
or a day of the week.

**The model has no clock and no location, and the code says so.** A reminder is
a wall-clock time; a model cannot know which zone. Rather than defaulting to
UTC — which would put a seven o'clock reminder at an hour nobody chose —
`services.productivity.zones` answers from the zones the person entered
themselves through a client that *did* know, and a tool with no answer says so
and asks. PRD 10 hit the same wall and refused a feature over it; this is the
narrowest honest version of answering it.

## Decision 6 — The daily-life tools are not a way round the medical boundary

Section 23's example is the dangerous one, and it is not an attack: *"Remind me
to double my medication tomorrow."* An ordinary sentence, and a reminder app
that writes it down without comment has quietly become a place where a dose
change is recorded as a decision.

What Nura cannot do is already structural — no tool, anywhere, changes a
medication, a schedule or a dose, and PRD 12 adds none. On top of that,
`services.productivity.boundaries` recognises the phrasing so the note gets
written *and* the person is told where dose changes come from. The sentence is
in `wording.MEDICATION_CHANGE_BOUNDARY`, once, so neither the assistant nor a
screen can improvise a softer version.

It is deliberately conservative. A dose-change verb *and* a medication noun
have to both be present, and — because no fixed word list could ever hold every
drug name — the names on *this person's own record* count as the noun.
Somebody else's drug name does not, which is both more accurate and the
privacy-respecting direction. "Pick up my medication" is an errand and is
treated as one.

## Decision 7 — `not_configured` is derived, never written

Weather, news and an external calendar are `not_configured` in every
deployment, and the state comes from asking whether a provider is both *named*
and *implemented*. `services.productivity.providers.IMPLEMENTED` is empty for
all three keys, and `build_provider` refuses every name — so a deployment that
sets `WEATHER_PROVIDER=openweather` hoping it will work gets a warning and
`not_configured`, not a feature that sometimes answers.

The capability map is exhaustive over every key, internal and external, because
section 29 says the model must not improvise a capability absent from the map —
and a map that listed only what works would have nothing to be absent from. It
is in the system prompt as well as on an endpoint, because a model that is
simply not given a weather tool will eventually answer from memory, while one
that has been told weather is not configured has been handed the true sentence
to say.

`alarms` is `available` **and** carries a limitation sentence, which looks
contradictory and is not. `available` describes what the feature does: an alarm
can be created, edited, enabled and scheduled, and all of that is true.
Whether the operating system wakes anybody is a different question, it has
never been tested, and it is answered beside the switch rather than by a false
`unavailable` that would be wrong about the part that works.

## Decision 8 — One scheduler, and PRD 5's reminders were left alone

Section 62 asks for the notification service to be extended into a shared
scheduler with domain wrappers, and in the same breath says not to destabilise
medication reminders while generalising.

`features/notifications/scheduler` is the shared engine: permission, the
Android channel, the stored map from source id to notification id, and the
reconcile-to-plan algorithm, once. PRD 12's two domains — reminders and alarms
— use it. **PRD 5's and PRD 7's reminders were not migrated.** They work, they
are tested, and moving them is a later PRD's job, deliberately left undone
rather than done carelessly.

Reconciliation is what makes section 34's "retries must not duplicate" true:
notifications whose key *and* time are unchanged are left alone, so running it
twice schedules nothing the second time. Routines get no notification at all,
which is a decision rather than an omission — a run is open all day, and
interrupting at half past seven for something somebody can tick off at nine is
noise.

## Decision 9 — The routines permission gets a source, and reaches nothing else

PRD 9 reserved `routines`, granted it faithfully, and had it unlock nothing,
with a test asserting as much. PRD 12 builds the source, so
`CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE` is now empty — the second time that
tuple has shrunk, and the honest record of a permission becoming real.

Section 42 draws the edge, and it is kept by absence rather than by filtering:

- There is **one** caregiver route in PRD 12, `GET /care/routines`, and it
  requires the permission.
- There is **no** caregiver suggestion action for a task, an alarm or a
  reminder — so a request for one fails schema validation before any code
  runs, the same shape PRD 9 used for `change_medication_dose`.
- A caregiver's assistant is shown two routine read tools and nothing else.
  Neither routine *write* is caregiver-writable: a caregiver who wants a
  routine paused proposes it, and the person approves.

Approval goes through the ordinary routine service, so an approved routine has
runs, steps and a schedule exactly like one the person made — and carries
`source = caregiver_suggestion` for as long as it exists.

## Decision 10 — Daily life is last on Today, in one list

Section 18 ends with the rule: *daily-life items must never obscure
safety-critical items.* The Important Today list is therefore assembled in a
fixed order in `api/v1/today.py` — medications, appointments, symptoms, then
daily life — and nothing in the daily-life summary can change where its rows
land.

Symptoms stay above daily life, which section 18 does not mention either way: a
symptom somebody recorded as getting worse is health information, and a
shopping list is not.

The robot's priority table makes the same ordering with one exception. An
`alarm` ranks above an appointment, because section 4 defines an alarm as a
time-critical alert whose purpose is to get attention at a specific time — and
it still ranks below medication and far below the safety band, which is what
makes section 64's "emergency preempts alarm" a comparison rather than a
special case. For the same reason an alarm is the one daily-life card a quiet
mode does not suppress: an alarm silenced by Sleep mode would be an alarm that
does not work, since the hour it is for is exactly the hour the robot would be
asleep.

## Decision 11 — Four presentation types, no new layout, no second transport

Section 30 says to extend PRD 11's queue rather than create a second robot
transport, and to update every shared layer together. The four new types go
through the same queue, the same reconciler, the same acknowledgement contract
and the same privacy mechanism. They reuse two existing layouts: a task, a
reminder and an alarm are `REMINDER`; a routine's progress is `STATUS`.

That is why **the firmware needed no parser change**, and it is checked rather
than claimed: the type vocabulary is mirrored in `presentation_protocol.h` and
compared against the backend tuple by a test that runs on a laptop, and
`test/test_presentation/test_main.cpp` parses one of each new card. The
firmware still dispatches on layout, which keeps its branch count equal to the
number of shapes a screen can take rather than the number of reasons a card
exists.

---

## Consequences

**What this makes easy.** Adding a daily-life feature is additive: a table, a
service, a route, a builder. Nothing in PRD 0–11 changed shape to accommodate
it — the only existing behaviour that moved is the `routines` permission
gaining a source, which is what it was reserved for.

**What this makes deliberately hard.** A new robot card needs a layout on both
sides. A new assistant write has to choose a side of section 22's line. A new
external capability needs a provider that exists before its key can read
`available`. Each of those costs are the point.

**What is still not true.** No notification has fired, no alarm has fired, no
vibration has been felt, and no frame has been drawn on a panel — the app has
never run on a physical phone and the robot has never been built. Every
scheduling test is a recording stub, and every robot test is a simulator.
Simulator proof is not hardware proof, and a recorded call is not a delivery.

**What a later PRD should pick up.** Migrating PRD 5's and PRD 7's reminders
onto the shared scheduler; a "follow my current time zone" option, which
section 36 allows to be deferred and which this stage defers; a real external
provider, which would turn one `IMPLEMENTED` entry into a capability without
any screen changing.
