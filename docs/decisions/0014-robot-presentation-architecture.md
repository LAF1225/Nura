# 0014 — Robot presentation architecture

**Status:** accepted, implemented, and never run on hardware.
**Date:** 11 October 2026 (PRD 11)

## Context

Nura's robot does not exist. The firmware compiles, the pin assignments in
`board_config.h` are assumptions, and no panel, speaker or microphone has ever
been attached. PRD 11 nonetheless has to deliver the whole software layer that
drives it — a presentation queue, priorities, a face, a capability model and an
acknowledgement contract — in a way that will not need redesigning when
hardware arrives.

That constraint shapes every decision below. So does one fact from PRD 10: this
product has already built an escalation engine that cannot reach anybody, and
the discipline that made that safe was refusing to let the software *say* it
had. The same discipline applies to a screen.

---

## Decision 1 — The robot is additive, and nothing calls into it

No service in PRD 0–10 was modified to notify the robot. There is no hook in
the dose service, the appointment service, the messaging service, or anywhere
in PRD 10's safety engine. Instead `services.robot.presenter.refresh` reads
what is currently true and makes the queue match.

Three things follow, each of which the PRD asks for separately:

- **A workflow cannot fail because of the robot** (sections 51–54, 100–102),
  because no workflow calls it.
- **A card cannot go stale** (section 56). There is no event that could have
  been missed — only state, read again. A dose that has been taken loses its
  card on the next reconciliation, a second later or after a week unplugged.
- **Reconnecting is not special** (sections 20, 99). A robot that comes back
  gets what is true now. No replay, no backlog, no "while you were away".

The alternative — a notification per source, each responsible for cancelling
its own card — would have meant six places that could forget, and the thing
they would forget is withdrawing a reminder that has stopped being true.

The one exception is the assistant (section 71), because a reply is an
utterance rather than a state: there is nothing to reconcile it against. It
goes through `services.robot.presentations`, a two-function module that finds
the profile's robots, does nothing when there are none, and **cannot raise** —
the caller is in the middle of answering somebody.

## Decision 2 — Capability truthfulness, with `not_verified` only from the device

Twelve capability keys, not one `robot_ready` boolean (section 10), and four
states where the third is mandatory (section 91).

**The backend never writes `not_verified`.** That state means "the driver is
present and nothing physical has been proven", which is a statement about a
build — and the backend has never seen a build. What it knows is whether a
robot has said anything, and the honest answer to that is `not_connected`,
which is what a missing row reads as.

The firmware reports `not_verified` for a panel whose `init()` returned true,
because that return value means this code talked to something over SPI and not
that a person has seen a legible frame. Section 93 keeps that as a separate,
later, physical step.

**A report goes stale when the firmware changes**, not merely when it is old
(section 124). "Proven by a build that is no longer running" is the useful
definition, and the downgrade is derived rather than written — the stored row
keeps what the device actually said, and `effective_state` can only ever move
towards *less* certainty.

## Decision 3 — Predefined layouts, never markup

Eight layout names from a closed set, each with required and optional fields,
and one firmware branch per layout. A payload says `REMINDER` and fills in four
short strings; the firmware decides what a reminder looks like.

An unknown layout is refused and acknowledged `unsupported` — there is no
fallback that draws something close enough (section 111). A backend that wanted
a new arrangement has to add a layout here *and* in the firmware, which is the
intended cost.

Text is data and can never become structure (section 112). The envelope is
built from typed fields and serialised once, so a family message containing
`{"layout": "EMERGENCY"}` is a string in `body`. Control characters are
stripped on the way in, because a serial display driver is exactly the kind of
thing that would act on them.

## Decision 4 — The backend owns the queue, the priority and the preemption

Ordering is a table (`ROBOT_PRESENTATION_PRIORITIES`), not a rule evaluated at
selection time. A rule would have been deterministic too, right up until a
second place evaluated it differently.

**Only safety preempts.** A presentation at or above the safety ceiling cancels
the ordinary cards that are *on the screen*; everything else waits its turn.
Section 17 says higher priority *may* interrupt, and this is where the "may" is
decided — an emergency takes the screen, and a medication reminder does not
throw away a message nobody has read yet. A merely *queued* card is never
preempted.

The device holds no policy. It fetches, draws and acknowledges; which thing to
draw is a question the backend has already answered.

## Decision 5 — The idle face is a presentation like any other

Section 83 says the robot shows the companion face when the queue is empty, and
section 84 that a temporary card returns to the previous valid mode afterwards.
Both are free if the face is itself the lowest-priority item in the queue: a
reminder outranks it, the reminder's render marks the face card completed, and
the next reconciliation queues the face again. **Nothing has to remember to go
back.**

It is also the only `repeatable` presentation — a face is a state the robot
returns to rather than an occasion that happened once — and that exception is
the reason the deduplication rule has one.

## Decision 6 — Command delivery is not physical render

The distinction PRD 11 turns on, and the one most likely to be eroded by a
later release. Four things keep it:

1. **Separate statuses.** `sent` means the backend handed the envelope over;
   `displayed` means a device said it drew it.
2. **One writer.** `queue.acknowledge` is the only function that writes
   `displayed_at`.
3. **A database constraint**, so a future bug cannot write it from anywhere
   else:
   `displayed_at IS NULL OR (ack_state IS NOT NULL AND ack_state IN (…))`.
   The parenthesised half is load-bearing: a SQL `CHECK` passes when it
   evaluates to null, and the short form accepted exactly the row it exists to
   refuse. A test that writes past the service caught that.
4. **Separate words.** The history label for `sent` is "sent to Nura" and for
   `completed` is "shown", and the app never composes either — the sentence is
   rendered server-side.

The app cannot acknowledge anything at all: it holds no device token, and
`robotApi.test.ts` asserts there is no function and no path in the client that
could.

## Decision 7 — Simulator-first verification

Section 63 is unusually direct: the robot is unfinished, so the simulator is a
**core verification surface, not optional polish**. `services.robot.simulator`
holds a `SimulatedRobot` that reports capabilities, reconciles, fetches and
acknowledges through the same services the HTTP endpoints call, and a `render`
function that turns an envelope into the lines a person would read.

That renderer mirrors the firmware's dispatch table, which is the honest answer
to section 131: the firmware's own dispatch cannot be executed on a development
machine, so the same dispatch is implemented in Python, the vocabulary is
checked against the firmware header from both the backend and the app, and the
completion report says plainly that simulator proof is not hardware proof.

The same core serves the tests, `scripts/robot_simulator.py` (a CLI that walks
section 132's manual plan) and `scripts/seed_dev.py --robot`. It is imported by
nothing in `app.api`, and a test asserts that — section 62 keeps simulator
controls out of production UI.

---

## Consequences

**Good.** No PRD 0–10 code changed except the assistant's one bounded call and
a read-only accessor added to PRD 10's monitoring service. Cards cannot go
stale. The queue is a table and two indexes. The whole experience is
exercisable without hardware, and the firmware's physical drivers compile under
a build flag so they keep working while nothing can run them.

**Costs, accepted.** Reconciliation runs on every heartbeat and every fetch — a
handful of indexed queries every thirty seconds per robot, which buys the
staleness guarantee. The heartbeat/fetch split costs one extra request per
presentation, which buys a liveness ping that never carries health data. And
the Python renderer in the simulator is a second implementation of the
firmware's dispatch, kept honest by the three-way vocabulary test rather than
by sharing code across a language boundary.

**What this does not do.** It does not validate a display, a speaker, a
microphone or a button. It does not prove the firmware's C++ behaves as written
— those tests compile for the target and have never run, because PlatformIO's
Unity tests execute on a board. And it makes no claim that any person has ever
seen anything on a Nura.

---

## See also

- [The presentation protocol](../device/presentation-protocol.md) — the wire
  contract, and §13 there for what is unverified
- [The companion experience](../architecture/robot-companion-experience.md)
- [ADR 0013](0013-safety-monitoring-and-escalation.md) — the truthfulness
  discipline this inherits
- [ADR 0003](0003-device-connectivity.md) — the two-transport strategy this
  extends rather than replaces
