# Safety monitoring, SOS and escalation

**Status: built, green, and reaching nobody outside the app.** PRD 10 is
implemented: monitoring sessions, safety events, the check-in and its
deadlines, the escalation engine, in-app caregiver alerts, the capability
model, emergency mode, the audit trail and the maintenance worker. What does
not exist is any way to reach a person who is not already looking at Nura —
no push provider, no SMS provider, no calling provider — and this document
says so wherever it is relevant rather than once at the end.

Three sentences the whole design exists to keep true:

- **Nura describes; it never diagnoses.** An event says what was observed.
- **Nura does not watch unless it was asked to.**
- **Nura never says somebody was reached unless somebody was reached.**

---

## 1. The shape, in one picture

```text
safety_monitoring_sessions      a period the user asked to be watched over
    │
    └── safety_events               something observed or asked for
            │
            ├── safety_escalation_attempts   one try at one person, one channel
            └── safety_alerts                an in-app record for a caregiver

safety_audit_events             what the system did, kept minimal
```

Five tables, and two references out of them: an attempt may name an
`emergency_contacts` row (PRD 9's chain) or a `caregiver_relationships` row
(PRD 9's second authorization path). Both are `ON DELETE SET NULL`, because an
attempt that records who was tried must outlive the contact it was tried on.
`recipient_label` is the snapshot that keeps it readable afterwards.

**No foreign key from any safety table reaches the health record**, and there
is no media column anywhere. Both are asserted by tests in
`backend/tests/test_models.py`.

---

## 2. Describe, never diagnose

PRD 10 section 3 draws the line and sections 16 and 52 police it. The event
vocabulary is:

```text
manual_sos                       a person asked for help
call_for_help                    a person asked out loud ("Nura, emergency")
possible_fall
possible_prolonged_immobility
possible_vomiting
possible_seizure_like_activity
possible_distress
test_event                       the harness only
```

Every sensor-observed type begins with `possible_`, and a test reads the tuple
and asserts the prefix rather than trusting a reviewer to notice. The words
section 52 forbids — "seizure detected", "fall confirmed", "unconscious" —
cannot be stored, because no such value exists, and cannot be *said*, because
`backend/app/services/safety/wording.py` is the only module that writes safety
prose and a test reads every string in it.

**There is no confidence column on `safety_events`.** Section 54 calls
confidence engineering metadata about a detector's own output rather than a
probability that somebody is ill. The detector interface carries it; the event
does not, because a column is a thing a screen eventually reads, and a number
next to "possible seizure-like activity" would be exactly the medical claim
section 52 rules out.

---

## 3. Monitoring is explicitly the user's

Section 4: never silently enabled. A session exists because somebody pressed
Start, and `started_by_account_id` records who.

| Duration mode | Ends |
| --- | --- |
| `30_minutes` | 30 minutes from the start |
| `1_hour` | an hour from the start |
| `until_bedtime` | the next time it is the user's bedtime, in their zone |
| `until_turned_off` | never — the only honest null `ends_at` |
| `custom` | 5 minutes to 12 hours, bounded |

**The client sends a mode, never an instant.** `compute_ends_at` is the only
function that answers "when does this end", which is what makes section 61's
"do not silently extend" checkable by reading one function instead of trusting
every caller — and what stops a phone with a wrong clock from arranging to be
monitored for a week.

`until_bedtime` needs `user_settings.safety_bedtime`, which is null until
somebody sets one. Section 6 forbids inferring a bedtime from behaviour, so the
request is refused with `bedtime_not_set` and the app asks for a time.

**Only `mobile_app` is accepted as a source.** `SAFETY_MONITORING_SOURCES`
reserves `assistant_future`, `robot_future` and `caregiver_future` so a later
PRD adds a writer rather than reopening the vocabulary — and
`caregiver_future` is reserved and deliberately refused, because section 10
says a caregiver must not switch monitoring on for somebody and section 58
repeats it for the caregiver assistant.

**One active session per profile**, enforced by a partial unique index on
`status = 'active'`. Starting a second ends the first as `superseded` rather
than failing: somebody who pressed Start twice meant to be monitored.

---

## 4. The state machine

```text
                      OFF
                       │  Start monitoring
                       ▼
                    ACTIVE ──────────── ends_at reached ──▶ EXPIRED
                       │
         ┌─────────────┴──────────────┐
         │                            │
   passive trigger              manual SOS / "Nura, emergency"
   (needs monitoring)           (works with monitoring off)
         │                            │
         ▼                            │
   CHECKING_USER                       │
         │                             │
   ┌─────┼─────────┬──────────┐        │
   │     │         │          │        │
 I'm   I need   false     deadline     │
 okay   help    alarm      passed      │
   │     │         │          │        │
   │     │         │    second prompt? │
   │     │         │       ├── yes ──▶ SECOND_PROMPT ──┐
   │     │         │       └── no ─────────────────────┤
   │     │         │                                   │
   ▼     ▼         ▼                                   ▼
RESOLVED │     RESOLVED                          ESCALATING
         └───────────────────────────────────────────▶ │
                                                       ▼
                                                  ESCALATED
                                      (outcome: complete / partial /
                                       failed / no_contacts /
                                       providers_not_configured)
                                                       │
                                     late "I'm okay", or Cancel
                                                       ▼
                                              RESOLVED / CANCELLED
```

`status` is where the event *is*; `escalation_outcome` is how escalation
*went*. They are separate columns on purpose: folding them together would mean
a row that cannot say "escalation finished partially and then the user said
they were fine", which section 126 requires it to be able to say.

---

## 5. Deadlines, and the exact timing

Every deadline is a stored timestamp. Section 28 asks for state a restarted
backend can reconstruct, and the mechanism is a column and a `WHERE deadline <=
now` — there is no in-memory timer anywhere, and an app that was force-quit
mid-countdown changes nothing about when escalation happens.

Section 8 asks for the second prompt's timing in writing:

```text
trigger
  │
  │  response_timeout_seconds   15 / 30 / 45 / 60 / 90, default 45
  ▼
first prompt runs out
  │
  ├── second prompt off ──────────────────▶ escalate
  │
  └── second prompt on
        │
        │  SECOND_PROMPT_TIMEOUT_SECONDS = 20, always
        ▼
      second prompt runs out ─────────────▶ escalate
```

**Twenty seconds, whatever the first wait was.** The first wait is for somebody
who may be busy; the second is for somebody who has already not answered once.
Worst case with the longest timeout and the second prompt on: 110 seconds from
trigger to escalation.

The timeout is stored **on the session** (section 7), so an event inherits the
value that was in force when monitoring started rather than the one in force
when the event happened to be processed.

---

## 6. State correctness versus timely escalation

Section 80 asks for this distinction to be explicit, so here it is.

**State correctness** does not need a worker. Every read of the safety status
advances a deadline that has passed, so whoever opens the app sees the true
state — the same way PRD 5 replenishes doses on every read.

**Timely escalation** does. Somebody whose phone is in another room is not
reading anything. `backend/scripts/safety_maintenance.py` is the durable path:

```text
expire monitoring sessions whose time is up
process response deadlines  → second prompt, or escalate
retry provider attempts that failed and are due
```

It is a script, not infrastructure (section 79): run it from cron, a scheduled
task or a container's own scheduler. **Once a minute** is the right cadence,
unlike the medication job's hourly — the shortest response timeout is fifteen
seconds, and a worker that ran hourly would turn a 45-second promise into an
hour-long one.

**The honest limit:** nothing in this project schedules that script for a
deployment. Without it, escalation happens when the event is next read, which
may be much later or never. `backend/tests/test_safety_worker.py` runs the real
script against a real database with a frozen clock, because section 80 says not
to claim timing works if the worker has never run.

---

## 7. Triggers: who may raise what

| Caller | May raise | Needs monitoring |
| --- | --- | --- |
| The app, owner-authenticated | `manual_sos`, `call_for_help` | no (section 21) |
| A linked device, device token | the `possible_*` set, `test_event` | yes (section 22) |
| The assistant | nothing directly — see §11 | — |

A passive trigger arriving while monitoring is off is refused with
`monitoring_not_active`. Section 22 allows rejecting or ignoring; rejecting
with a reason is the version a device can act on, and it is also the version
that cannot be mistaken for Nura monitoring anyway.

**The device route takes no profile id.** `DeviceSafetyEventCreate` has no
field for one, so section 105's "never trust profile identity from the request
body" is enforced by the schema rather than by a check somebody could remove.
The device token resolves the device, and the device resolves the profile it is
linked to.

**Two idempotency guards** (sections 20 and 77). A client or device key if one
was sent, and otherwise any event still live for this profile. Somebody
pressing SOS twice because nothing visibly happened must not alert everybody
twice.

**`developer_simulation` is a trigger source and never a production control.**
Section 18 puts the harness in tests, seed scripts and developer diagnostics,
and the app has no control that sends it. The harness is
`python -m scripts.seed_dev --account latest --safety …` plus a device token
and a `curl`.

---

## 8. The escalation policy, written out

Section 40 asks for the exact policy. It is:

1. **Freeze the plan.** The caregivers permitted *right now*, the active
   emergency contacts in their current priority order, the capability map and
   the response timeout. Stored on the event as `escalation_snapshot`
   (sections 87 and 88), and the rest of the run reads it — so a chain
   reordered mid-emergency does not change who is being reached.
2. **Caregivers first, all at once, priority 0.** An in-app alert costs nothing
   to create and there is no reason to make one wait behind a phone call that
   cannot happen. A push is attempted only when a provider exists *and* the
   caregiver asked for one.
3. **Then the emergency contacts, one at a time in priority order.** For each,
   try a call before a text — a call wakes somebody — and **stop the whole
   chain at the first contact actually reached.** Section 40 says to continue
   when a contact is unavailable or fails; it does not say to ring everybody.
4. **Record the outcome.**

Today step 3 reaches nobody, so every contact gets a row saying
`not_configured`. That is what makes the user-facing list truthful: *in-app
alert created for Ayesha; phone call for Ayesha: not set up in this build*. A
chain that silently did nothing would look identical to one that worked.

**The PRD 9 chain is reused directly** (section 30). Nothing in PRD 10 sorts
contacts; `escalation.build_plan` reads `contacts.list_contacts` and preserves
its order, and a test reorders the chain through PRD 9's own route and checks
the next escalation changes.

---

## 9. Attempts, alerts, and what "delivered" means

`safety_escalation_attempts.status`:

| Status | Means |
| --- | --- |
| `pending` | made, not yet tried |
| `attempted` | tried; **nobody has confirmed anything** |
| `delivered` | a provider confirmed it |
| `failed` | a provider said no |
| `skipped` | cancelled before it went |
| `not_configured` | there is no provider for this channel |

**Nothing in this build ever writes `delivered`**, and a test asserts it across
the whole table. The value exists so a real provider can use it; the absence of
a code path that writes it is section 38's rule made structural.

`not_configured` is a first-class outcome rather than a failure: a build that
cannot send an SMS has not failed to send one.

`safety_alerts` is separate from attempts because the two answer different
questions. The attempt records what the system tried; the alert is the artefact
a caregiver can open. **An alert row means an alert exists, not that anybody
saw it** (section 37) — `read_at` stays null until the caregiver opens their
list, which is the only thing in the system that can write it.

Uniqueness makes repeats safe (section 75): attempts are unique on (event,
recipient, channel) via a single text `recipient_key`, and alerts on (event,
account). A `recipient_key` rather than three nullable foreign keys because
PostgreSQL treats NULLs as distinct — a unique constraint over nullable
columns would never collide, and a duplicated worker run would contact
somebody twice.

---

## 10. Providers, and which are configured

`SafetyNotificationProvider` — `send_in_app_alert`, `send_push_alert`,
`send_sms_alert`. `EmergencyCallProvider` — `start_emergency_call`,
`get_call_status`. No vendor concept in any signature.

| Channel | Provider today | Code |
| --- | --- | --- |
| `in_app` | `InAppOnlyNotificationProvider` | — (`attempted`) |
| `push` | none | `push_not_configured` |
| `sms_future` | none | `sms_not_configured` |
| `voice_call_future` | none | `calling_not_configured` |

`calling_not_configured` is deliberately the same code PRD 9's
`services.caregivers.calls` returns: one code for "Nura cannot ring anybody",
whichever feature asked. The two interfaces stay separate, though —
`AudioCallProvider` is a two-way call between a primary user and a caregiver
who both have the app open; `EmergencyCallProvider` would ring a number
belonging to somebody with no Nura account. Conflating them would mean
configuring one silently claimed the other.

Configuration (section 109): `SAFETY_PUSH_PROVIDER`, `SAFETY_SMS_PROVIDER`,
`SAFETY_CALL_PROVIDER`. Unset means not configured; **a name nobody implemented
is refused loudly**, because a deployment that set `SAFETY_SMS_PROVIDER=twilio`
and got silence would believe it had SMS.

**Why `send_in_app_alert` is on the interface at all.** It is the one channel
that works, and it is tempting to treat it as not really a delivery. But the
question each method answers is the same — *is this a real way to reach this
person, and what happened when we tried?* — and an in-app alert's honest answer
is "a record now exists for them to find", which is `attempted` and never
`delivered`. The row is written by `escalation`, which owns the transaction; the
provider says whether the channel is real.

**Retries are bounded** (section 124): `MAX_RETRIES = 2`, a fixed 30s/120s
backoff, recorded as `retry_count`. `not_configured` is never retried — a build
with no SMS provider will not grow one in thirty seconds.

**`RecordingNotificationProvider` is test-only, and that is a property rather
than a note** (section 110). No setting value reaches it;
`build_notification_provider` has no branch that returns it, and a test
asserts that every plausible name (`recording`, `mock`, `test`, `log`, `fake`)
is refused.

---

## 11. The caregiver path, and the assistant

**Caregiver access is PRD 9's second authorization path, unchanged**
(section 104). `safety_alerts` on an *active* relationship, resolved through
`CareScope`. Nothing in PRD 10 touches `account_profile_roles`, so a caregiver
still cannot reach a single route written before PRD 9 — and cannot reach the
owner's safety routes either. Their whole view of safety is the alert list.

**Permission is re-checked at read time, not inherited from creation**
(section 86). An alert created last night for a caregiver whose permission was
withdrawn this morning is not returned to them. The row stays: deleting
evidence of what the system did is not a retention policy.

**Permission and preference are different things** (section 93). The
permission decides whether an alert exists for a caregiver at all. The
preference — `notify_safety_alerts` on the relationship — decides only whether
a push would be sent, and can never create access.

**PRD 9's `safety_alerts` left `CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE`.** PRD
9 section 94 said the key could exist before its event source did and warned
against fabricating one. PRD 10 built the source, so the tuple shrank to
`("routines",)` and the screens stopped saying the category shares nothing —
because it no longer does.

The assistant gains nine tools (section 56), and their shape comes from
section 57:

| Tool | Who | Acts |
| --- | --- | --- |
| `get_safety_status` | owner | reads |
| `get_active_safety_event` | owner | reads |
| `get_escalation_status` | owner | reads |
| `start_safety_monitoring` | owner | **asks first** |
| `stop_safety_monitoring` | owner | **asks first** |
| `manual_sos` | owner | **asks first** |
| `respond_to_safety_check` | owner | `need_help` at once; `im_okay` asks first |
| `get_active_safety_alerts` | caregiver with `safety_alerts` | reads |
| `acknowledge_safety_alert` | caregiver with `safety_alerts` | acts |

**No tool anywhere takes an event type, a trigger source or a confidence.**
Section 57's rule — the model must not create a `possible_*` event from a
speculative interpretation — is satisfied by absence, and a test checks every
argument model in the registry.

**The asymmetry in `respond_to_safety_check` is the point.** Erring towards
help is a safe error; erring towards "they are fine" is not. A model that ended
an escalation because it misread a sentence would have done the one
unrecoverable thing in this feature.

**The emergency fast path does not go through the model at all.** "Nura,
emergency" is matched deterministically in `services.assistant.policy` before
any provider is called, raises a real `call_for_help` event, escalates, and
replies with a notice assembled from what the escalation actually did
(section 14). An emergency never waits on a model, a rate limit or a network.

**Emergency mode** (sections 43 and 96) is derived from the event, never
stored: `safety_mode = "emergency_active"` on the reply, a prompt block that
overrides humour and proactivity, and an instruction to repeat
`get_escalation_status`'s lines rather than describe an outcome.
`acknowledge_safety_alert` is the single caregiver write in the tool layer, and
it is allowed because of what it is: one timestamp saying a caregiver said they
would look in. It resolves nothing (section 125).

---

## 12. Capabilities: the UI is driven by what exists

Section 64 gives the reason in one line: *this prevents misleading UI*.

```json
{
  "manual_sos": "available",
  "in_app_safety_checks": "available",
  "caregiver_in_app_alerts": "available",
  "push_delivery": "not_configured",
  "sms_delivery": "not_configured",
  "audio_calling": "not_configured",
  "robot_detection": "not_connected"
}
```

Every value is derived from the thing itself: `push_delivery` asks the
notification provider, `audio_calling` asks PRD 9's call provider,
`robot_detection` asks `services.safety.detectors.DETECTORS` — which is empty,
and that emptiness is load-bearing. Deleting the registry and hard-coding the
capability would work until somebody wrote a detector and forgot the screen.

`not_configured` and `not_connected` are different facts: nobody wired a
provider, versus there is one and it cannot be reached. A robot that has never
existed reports `not_connected`, because section 66's honest sentence is "not
connected yet".

---

## 13. Offline and degraded behaviour

Section 67: the app detects that it cannot reach the server, says so
prominently, **does not claim server escalation occurred**, and offers what is
locally available — the phone's own dialler, labelled "Nura does not place the
call" (section 68).

Section 69: **no emergency services number is hard-coded anywhere.**
Jurisdiction-specific emergency calling needs separate validation, and a
number that is wrong in somebody's country is worse than none.

Section 70: a backend that answers but is failing produces the same honest
sentence rather than a half-working screen.

There is no offline queue for safety. Every other PRD 0–9 feature queues an
action taken with no signal; an emergency must not, because a queued emergency
request is the one piece of queued work whose delay makes it worthless — and
showing it as sent would be the lie this whole PRD is written against.

---

## 14. Privacy Mode, and a failed escalation

Two policies PRD 10 asks to be written down rather than guessed at later.

**Privacy Mode and Safety Monitoring** (section 63). PRD 8's `privacy` mode is
about what the *assistant* brings up in conversation: it keeps the record out
of the prompt and stops Nura suggesting things to remember. It does not switch
Safety Monitoring off, and today it could not meaningfully interact with it,
because there is no camera and no microphone anywhere in this system — so
nothing exists for Privacy Mode to mute, and nothing in the product claims
otherwise.

**The policy for when sensors exist**, stored here now so it is a decision
rather than an improvisation:

- Privacy Mode must **suspend passive detection** while it is on. A person who
  turned privacy on did not consent to being watched more quietly.
- It must **leave manual SOS and the in-app check-in working.** Those are
  things the person does, not things done to them.
- The capability map must then report `robot_detection` as `unavailable`
  rather than `available`, so the monitoring screen says detection is
  suspended instead of implying coverage the person switched off.
- And Safety Monitoring must not silently re-enable detection when Privacy
  Mode ends; the session's own state decides, as it does now.

**A failed escalation** (section 127). Nothing may be left sitting in
`escalating`. The whole run is wrapped: anything that raises leaves the event
`escalated` with `escalation_outcome = "failed"` — section 127's
`escalation_failed` expressed as this schema's status-and-outcome pair, because
the two answer different questions (see §4). The user-facing sentence is "Nura
could not complete any step", and the emergency screen keeps the phone's own
dialler and the no-providers warning on it, which is the truthful fallback
instruction section 127 asks for.

## 15. False positives, and what is not done with them

Section 47 asks after a safe dismissal; section 48 says to store the label and
the optional coded reason. `false_positive` is **nullable**: null means nobody
was asked or nobody answered, `false` means they said it was real. Collapsing
those two would turn silence into a claim.

**Nothing trains on these columns.** No model in this project reads them, and a
later PRD that wants one needs a governance decision first — which is this
sentence, rather than a comment nobody reads.

---

## 16. Audit and retention

Eighteen event types (section 89), and every `meta` payload is built by a
helper in `services.safety.audit` from a fixed set of keys: a status, a
channel, an outcome, a count, a number of seconds. **No helper takes free text,
a name or a phone number**, so none can reach the table, and a test asserts
that from the helper signatures.

The trail records no *views*. `alert_acknowledged` is in the vocabulary because
a caregiver saying "I'm checking on them" is an action somebody may need to
account for; there is no event for opening the safety history, for the same
reason PRD 9 has none for opening a medication list.

**Retention** (section 91), documented and not yet enforced:

| Rows | Policy |
| --- | --- |
| `safety_events` | kept — the history is the feature |
| `safety_escalation_attempts` | kept with their event |
| `safety_alerts` | kept with their event; a withdrawn permission hides them from the caregiver rather than deleting them (section 86) |
| `safety_audit_events` | kept; a few rows per event |
| false-positive labels | kept with the event, used for nothing |
| raw camera/audio | **never stored** (section 92) — there is no column |

There is no deletion job in this project for any table, and inventing one only
for safety rows would delete the evidence first. A later PRD implements the
policy.

---

## 17. Privacy in logs and analytics

Section 121: safety logs carry operational data only. Every log line in the
safety services is of the shape `safety.monitoring.started`,
`safety.escalation.finished outcome=partial`, `safety.audit.alert_created` — no
profile, no account, no recipient, no event type where it is avoidable, and
never a phone number. The `escalation_snapshot` carries names and priorities
and **no phone numbers**, asserted by a test.

Section 122's analytics vocabulary is reserved and nothing emits it: there is
no analytics pipeline in this project yet.

Section 123's future push copy is written and unused: "Nura safety alert /
Please open Nura to review." A lock screen is not an authenticated surface, so
the detail stays behind the app.

---

## 18. Robot independence

Section 115: no PRD 10 acceptance test needs a real ESP32, BLE, a camera, a
microphone, a speaker, a display, a fall detector or a heartbeat — and none
does. The device-trigger contract is exercised with authenticated simulated
device requests, which is what section 115 says to do instead.

Section 131's checkpoint — *can every software workflow run without the
robot?* — is **yes**: start and stop monitoring, manual SOS, the
"Nura, emergency" contract, possible-event ingestion, the check-in, the
timeout, escalation, caregiver alerts, acknowledgement, cancellation, false
alarms, history and emergency mode. Physical detectors are future event
producers, not workflow dependencies.

**PRD 11 added a screen for some of this, and did not become a dependency.**
The robot can now show a monitoring indicator, a check-in prompt and an
emergency card, all built from this state by reading it — PRD 11's
`builders.safety.sync` reconciles rather than being notified, so nothing here
had to change and no safety behaviour can wait on a display.

Two deliberate choices keep the direction one-way.

*Drawing a screen never advances a deadline.* PRD 11 reads monitoring through
`monitoring.peek_session`, which reports a session whose time has passed as
gone **without ending it**. `active_session` is still the right call for
anything that acts on monitoring; a display request is not that, and one that
expired somebody's session as a side effect would make the presentation path
load-bearing for safety. A test moves the clock past a session's end,
reconciles the robot, and asserts the session is untouched.

*The emergency card is this state, not a summary of it.* PRD 11 section 8
forbids "Help is on the way." unless a real provider confirmed something
equivalent, so the card reports who an alert *record* exists for and that
calling is not configured — the same two facts section 9 above describes, in
the same words, from the same capability map.

And one claim PRD 11 explicitly does not make: the monitoring card says
monitoring is on and until when. It cannot say a detector is watching, because
no sentence that could exists in either wording module.

---

## 19. What is not enforced, and what is not validated

The section to read if you are deciding whether to rely on any of this.

**Nothing has reached a person outside the app.** No push notification has been
delivered, no text message sent, no call placed. The capability endpoint says
so, the escalation list says so per contact, and two standing warnings say so
on screen.

**No detector exists, and none has been validated.** There is no fall model, no
immobility model, no seizure-like classifier and no vomiting detector.
`DETECTORS` is empty. **No clinical validation of any kind has been performed**
(section 117), and nothing in this project may claim otherwise.

**No hardware has produced a reading.** The device route is tested with a
simulated device holding a real token. No robot exists.

**The app has never run on a phone.** The safety screens are mounted and driven
in tests against a stubbed backend; no person has ever answered a real
countdown on a real device.

**Timely escalation depends on a script nobody has scheduled.** See §6.

**`routines` is still a permission with nothing behind it.** PRD 9's reason
holds: no PRD through 10 says what a routine is.

**Emergency mode has never been seen by a model.** The prompt block and the
`emergency_active` safety mode are real and tested against a scripted provider;
Nura has still never spoken to a real model.

---

## See also

- [Caregivers and family](caregiver-and-family.md) — the relationship,
  permission and emergency-contact model PRD 10 reuses
- [The Nura assistant](nura-assistant.md) — the tool layer and the emergency
  phrase
- [Safety and emergency](safety-and-emergency.md) — the PRD 0 design notes
  this implements
- [The robot companion experience](robot-companion-experience.md) — how this
  state reaches a screen, and why that direction is one-way
- [ADR 0013](../decisions/0013-safety-monitoring-and-escalation.md) — why the
  decisions above were made
