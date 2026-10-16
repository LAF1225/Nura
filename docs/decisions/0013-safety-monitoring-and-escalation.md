# 0013 — Safety monitoring, escalation and the limits of honesty

**Status:** Accepted · PRD 10

## Context

Every PRD before this one answered a question about *records*: can this account
reach this data, did somebody take this dose, what did a doctor say. PRD 10
answers a question about a *person*: is somebody all right, and if nobody knows,
who finds out.

That changes what a bug costs. A wrong permission leaks information. A wrong
escalation means somebody lay on a floor while an app displayed a reassuring
sentence. So the governing constraint for this stage is not completeness, it is
that **nothing in the product may ever claim more than happened** — and the
design decisions below are mostly about making that structural rather than
careful.

Seven decisions shaped it.

## Decision 1 — a sensor event is an observation, and the vocabulary says so

Every event type a detector may produce begins with `possible_`.
`SAFETY_EVENT_TYPES` has no `fall`, no `seizure`, no `vomiting` and no
`unconscious`, and the one module that writes safety prose is read in full by a
test that forbids those words.

The alternative was a confidence score and a neutral label — "fall, 0.82". It
reads as more informative and is worse in every way that matters: a number next
to a body part is a diagnosis in the only sense that affects behaviour, nobody
has validated the model that would produce it, and a screen that shows it will
eventually be quoted to a clinician.

So confidence exists on the *detector interface*, where a future evaluation can
use it, and there is **no confidence column on `safety_events`** — because a
column is a thing a screen eventually reads.

The cost: the product says less than a detector might know. That is the point.

## Decision 2 — monitoring is explicitly activated, and the server decides when it ends

A session exists because somebody pressed Start. The client sends a *duration
mode*; `compute_ends_at` is the only function that turns one into an instant.

Trusting the client with `ends_at` would have been simpler and is the shape most
APIs take. It also means a phone with a wrong clock, a buggy build or a
malicious caller can arrange to be monitored for a week — and §61's "do not
silently extend" becomes a property of every caller rather than of one function.

`until_bedtime` refuses rather than guessing (§6). Inferring a bedtime from
behaviour is the hidden monitoring period §5 forbids, in a politer costume.

And `caregiver_future` is a reserved source that is deliberately refused: a
caregiver switching monitoring on for somebody without their knowledge is the
surveillance product this whole system is written against.

## Decision 3 — escalation is server-state driven, and every deadline is a column

`response_deadline_at` and `second_prompt_deadline_at` are timestamps. The
worker's query is a comparison. There is no in-memory timer anywhere, and no
screen decides that time is up.

A countdown in the app would have been easier and is what a prototype usually
does. It fails in exactly the case the feature exists for: the phone is face
down on a table, the app is backgrounded, the process is killed. A timer that
only runs while somebody is watching is a timer for a problem that does not
need solving.

The consequence is a distinction §80 insists on being explicit about, and which
this project draws in two places:

- **state correctness** — every read advances a passed deadline, so whoever
  looks sees the truth, worker or no worker;
- **timely escalation** — `scripts/safety_maintenance.py`, which no deployment
  here schedules, and whose absence is documented as a limit rather than
  papered over.

The honest statement is in
[safety-monitoring.md §6](../architecture/safety-monitoring.md): without that
script, escalation happens when the event is next read.

## Decision 4 — PRD 9's authorization and PRD 9's chain are reused, not reimplemented

Caregiver safety access is `safety_alerts` on an active
`caregiver_relationships` row, through the same `CareScope` PRD 9 built.
Escalation walks `emergency_contacts` in the priority the user set, read through
PRD 9's own service.

Two competing models would have been easy to arrive at: a safety-specific
"alert list" permission, and a safety-specific contact order. Both are worse
than they look. A second permission means a person who revoked caregiver access
might still be alerting them; a second order means a chain that reads one way
on the contacts screen and runs another way in an emergency.

§30's "do not create a second competing priority model" is therefore checkable:
reordering through PRD 9's route changes who PRD 10 tries first, and a test
asserts it.

The one thing PRD 10 *did* change in PRD 9 is honest rather than additive:
`safety_alerts` left `CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE`, because PRD 9
§94 said the key could exist before its event source did — and PRD 10 built the
source, so the screens stopped saying the category shares nothing.

## Decision 5 — external delivery is behind a provider interface, and nothing pretends

`SafetyNotificationProvider` and `EmergencyCallProvider` exist; the only
implementations report `not_configured` with a stable code. `delivered` is in
the attempt vocabulary and **no code path writes it**.

The tempting alternative is a provider that logs and returns success. It makes
every screen look finished, every test pass, and every demo work — and it is
the single most dangerous thing this project could contain, because the first
time it matters nobody will be reached and the app will say somebody was.

So the in-app channel — the one that works — reports `attempted`, never
`delivered`: the record exists and nobody has read it. `read_at` is written only
by the caregiver opening their list, which is the one event that genuinely means
somebody looked.

A recording provider is allowed in tests (§110), and it is unreachable from any
setting value rather than merely discouraged: `build_notification_provider` has
no branch that returns it, and a test asserts that `recording`, `mock`, `test`,
`log` and `fake` are all refused as configuration.

## Decision 6 — an unconfigured provider fails explicitly, and the UI is driven by capability

`GET /safety/capabilities` reports each of seven capabilities as `available`,
`not_configured`, `not_connected` or `unavailable`, and **every value is
computed from the thing itself** — the notification provider, PRD 9's call
provider, the detector registry. None is a constant and none is a flag somebody
could flip without wiring something behind it.

Hiding a control is not the same as saying it does not exist. A person deciding
whether to rely on Nura cannot infer "there is no push provider" from the
absence of a toggle, so the capability screen says it in words, and two standing
warnings say it where it matters: before monitoring starts, and during an
emergency.

That is also why `not_configured` and `not_connected` are different values:
nobody wired a provider, versus there is one and it cannot be reached. A robot
that has never existed reports "not connected yet", which is the sentence §66
asks for.

## Decision 7 — physical detection is deferred, and the socket is empty on purpose

`services.safety.detectors.DETECTORS` is an empty tuple.

Hard-coding `robot_detection: "not_connected"` would have been one line less and
would have worked — until somebody wrote a detector and forgot the capability
map. An empty registry makes the capability *derived*, so the day a detector
exists the UI stops saying nothing is watching without anybody editing a screen.

The interface is also where §92's "emit events, not continuous raw media" is
enforced: a `DetectedEvent` carries scalars, and there is nowhere to attach a
frame, a clip or a waveform. No safety table has a media column either.

**No fall, immobility, seizure-like or vomiting detector exists, and none has
been clinically validated.** PRD 10 §117 forbids claiming otherwise, and this
project does not.

## Consequences

- An emergency never waits on a model: "Nura, emergency" is matched
  deterministically before any provider is called.
- A caregiver's whole view of safety is the alert list, and it carries a type,
  a time, an outcome and a sentence — no health data.
- The assistant can ask to start monitoring, stop it, raise an SOS or say the
  person is okay, and **all four ask the person first**; only "I need help"
  acts immediately, because erring towards help is the safe error.
- Every claim the product makes about reaching somebody is a row somebody can
  read, in words a test can check.
- And the thing nobody should have to dig for: **nothing has ever reached a
  person outside this app, no detector has ever produced a reading, and the app
  has never run on a phone.**

## See also

- [Safety monitoring, SOS and escalation](../architecture/safety-monitoring.md)
- [ADR 0012 — caregiver access and approval](0012-caregiver-access-and-approval.md)
- [ADR 0011 — the assistant and the model boundary](0011-assistant-and-model-boundary.md)
