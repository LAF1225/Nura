# Safety and emergency architecture

**Status: implemented by PRD 10.** This page is the design note PRD 0 wrote
before any of it existed, kept because it is the record of what was intended
and because every constraint on it turned out to be load-bearing. The build is
in **[safety-monitoring.md](safety-monitoring.md)**, which is the page to read
if you want to know what the system does today.

What changed since this was written: monitoring sessions, safety events, the
check-in and its deadlines, the escalation engine, in-app caregiver alerts, the
capability model and emergency mode all exist. What has *not* changed is the
honest part — there is still no way to reach a person who is not already
looking at Nura, and no detector has ever produced a reading.

Each constraint below is annotated with how it was kept.

## Escalation flow

The principle is that Nura asks before it escalates, and a person always gets
the chance to say "I'm fine".

```text
            Possible event detected
                      │
                      ▼
               Prompt the user
                      │
                      ▼
      Wait a user-configured period
                      │
                 Response?
                  ╱        ╲
               Yes          No
                │            │
                ▼            ▼
        Continue safely   Escalate to the emergency
                          contact priority chain
```

Events that may later qualify: falls, seizure-like activity, vomiting,
prolonged immobility, and obvious calls for help.

**Kept.** This is the flow PRD 10 built, with one addition the PRD asked for:
an optional second prompt between the first wait and escalation (PRD 10,
section 8). Every deadline is a stored timestamp rather than a screen timer,
so the flow survives the app being closed.

## The explicit override

Saying **"Nura, emergency"** must bypass the waiting period entirely and begin
escalation immediately. A person asking for help directly is not a signal that
needs confirming.

**Kept.** The phrase is matched deterministically in
`services.assistant.policy` *before* any model is called, raises a real
`call_for_help` event and escalates inside the same request. An emergency never
waits on a model, a rate limit or a network.

## Constraints on any future implementation

- **Describe, never diagnose.** "Nura noticed unusual movement", not "Nura
  detected a seizure." A detected event is an observation, not a finding.
  *Kept, and made structural: every sensor-observed event type begins with
  `possible_`, there is no confidence column on an event, and one module writes
  all safety prose with a test reading every string in it.*
- **The waiting period is the user's to set**, including how long it lasts and
  who is contacted in what order. *Kept: five timeout options stored on the
  session, and the PRD 9 contact chain reused directly rather than
  reimplemented.*
- **Escalation order is an explicit, ordered chain**, not a broadcast. *Kept,
  and frozen as a snapshot when escalation starts, so reordering it mid-event
  does not change who is being reached.*
- **A missed response is not proof of an emergency.** The design tolerates
  false positives by asking first; it must not tolerate silently escalating
  without having asked, except for the explicit override above. *Kept: a
  passive trigger always begins a check, and a false-positive label is stored
  with three states so silence is not read as a claim.*
- **Detection must be separable** from general assistant functionality, so
  companion features can change without touching the safety path. *Kept:
  `services.safety.detectors` is an interface and an empty registry, and the
  assistant's tools cannot create a sensor event at all.*
- **Camera and microphone data is not retained by default.** Any capture needs
  an explicit retention rule decided before the feature ships. *Kept by
  absence: no safety table has a media column, and the detector interface
  carries scalars only.*
- **Offline behaviour must be deliberate.** Medication reminders are the one
  place this is now implemented, and deliberately so: the reminder is an
  OS-scheduled local notification, an action taken with no signal is queued on
  the device rather than lost, and the queue is drained when the connection
  returns — see [the medication system](medication-system.md). *Emergency*
  offline behaviour remains out of scope and must not be approximated.

## Caregiver access

Caregiver visibility will require an explicit, granted permission record.
An API must never return medical data merely because a client supplied a user
id — see the security posture in
[system-overview.md](system-overview.md).

**Kept.** PRD 9 built the permission record and PRD 10 uses it unchanged:
safety alerts need `safety_alerts` on an *active* caregiver relationship,
re-checked on every read rather than inherited from when the alert was created.
A caregiver cannot reach any of the owner's safety routes.

## What this page does not cover

The limits of the built system — what has never been delivered, what has never
been validated, and what depends on a script nobody schedules — are in
[safety-monitoring.md](safety-monitoring.md), section 19. That is the section
to read before relying on any of this.

How safety state reaches the robot's screen, and why that direction is one-way,
is in
[robot-companion-experience.md](robot-companion-experience.md). The short
version: PRD 11 reads this state and never writes it, and drawing a screen
cannot advance a safety deadline.
