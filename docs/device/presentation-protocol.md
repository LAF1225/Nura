# The Nura presentation protocol, version 1

**Status: implemented on both sides, and never run on a screen.** The backend
builds envelopes, the firmware parses and dispatches them, the simulator
renders them, and the three agree on every name in this document — checked by
`backend/tests/test_robot_protocol.py` and
`mobile/tests/robotPresentationProtocol.test.ts`, which both read
`firmware/xiao_esp32s3/src/presentation_protocol.h`. What has never happened is
a frame on a panel.

This is the wire contract between the backend and the robot. It is the document
a firmware author reads; the reasoning behind it is
[ADR 0014](../decisions/0014-robot-presentation-architecture.md) and the
product thinking is
[the companion experience](../architecture/robot-companion-experience.md).

Three sentences the whole protocol exists to keep true:

- **A presentation is a request, not a render.** Only the device can say what
  was shown.
- **A layout is a name from a closed set.** The robot never interprets a string
  as a drawing instruction.
- **A capability is what the device has proven, not what it compiled.**

---

## 1. The shape, in one picture

```text
         heartbeat  ──────────────────────────▶  presentation_pending: true
robot                                                                    backend
         GET  /device-actions/presentations/next  ──▶  envelope (200) or 204
         POST /device-actions/presentations/{id}/ack ──▶  received / rendered / …
         POST /device-actions/capabilities        ──▶  what this hardware is
```

Section 58 of PRD 11 asks for the existing heartbeat to be extended rather than
a second transport added, and that is what `presentation_pending` is. The
heartbeat carries the **flag** and never the presentation: a heartbeat is
retried and logged, and a medication name travelling in one would eventually
sit in a retry log (section 67).

The cost is one extra request per presentation. The benefit is that the
liveness ping carries no health data, ever.

---

## 2. The envelope

```json
{
  "protocol_version": 1,
  "presentation_id": "7f3a1c20-0000-4000-8000-000000000001",
  "type": "medication_reminder",
  "priority": 40,
  "mode": "information",
  "layout": "REMINDER",
  "payload": {
    "title": "Medication",
    "primary": "Reminder due",
    "respond_in_app": true,
    "sensitive": false
  },
  "settings": {
    "brightness": 70,
    "volume": 40,
    "reduced_motion": false,
    "face_animation": true,
    "sleep_screen": "dim"
  },
  "expires_at": "2026-10-04T20:10:00+00:00"
}
```

| Field | Meaning |
| --- | --- |
| `protocol_version` | Section 116. A device that does not recognise it refuses the envelope and reports `unsupported` with `unsupported_protocol_version`. |
| `presentation_id` | The row's own id. The only identifier in the envelope; nothing from the health record travels. |
| `type` | One of the eleven presentation types (§4). |
| `priority` | The rank from the table in §5. Copied so the device can reason about what it is holding. |
| `mode` | What the robot *is* at this moment (§6), so a card arrives knowing whether it is a companion moment or an emergency. |
| `layout` | One of eight (§3). |
| `payload` | The layout's own fields, already shortened and sanitised. |
| `settings` | The device's preferences, travelling with every presentation. |
| `expires_at` | Absent for safety and emergency presentations, which are tied to live PRD 10 state rather than to a timer (section 113). |

**The settings travel with the envelope** rather than on an endpoint of their
own (sections 30, 44, 45). A robot that reconnects after a week draws the right
brightness on the first card it shows, and a preference change takes effect on
the next thing shown. `face_animation` is already combined with reduced motion
by the backend, so the firmware has one field to read rather than a rule to
remember.

**Envelopes are small.** `ENVELOPE_MAX_BYTES` is 1 KiB and
`test_the_envelope_is_small` builds the largest envelope the backend can
produce and asserts it fits. Section 108 rules out media; there is no URL field
and nothing to download.

---

## 3. Layouts

Eight, and the firmware has one branch per layout in `card_renderer.cpp`.

| Layout | Required | Optional | Used for |
| --- | --- | --- | --- |
| `FACE` | `face_state` | — | the companion face (§7) |
| `TITLE_BODY` | `title`, `body` | — | a heading and a sentence |
| `TITLE_VALUE` | `title`, `value` | — | a heading and one short value |
| `REMINDER` | `title`, `primary` | `secondary`, `prompt` | medication, appointments |
| `MESSAGE` | `title`, `body` | `sender` | a family message |
| `STATUS` | `title`, `lines` | — | safety status, system status |
| `EMERGENCY` | `title`, `lines` | — | emergency state |
| `PAIRING_CODE` | `title`, `code` | — | PRD 2's pairing code |

Any layout may also carry these, because they are about *how* to show
something rather than what it says:

```text
serious          no face, no decoration, high contrast (section 7)
sensitive        keep this payload out of logs and previews (section 67)
truncated        there was more text than fitted (section 77)
continue_in_app  the rest is in the app (sections 78, 79)
actions          what the card offers, if the device has input (section 85)
speak            may be read aloud, if a speaker exists (sections 43, 82)
chime            which chime, if any audio exists (section 81)
respond_in_app   the device has no input, so say where to answer (section 86)
```

**An unknown layout is refused, not approximated.** `layoutFromName` answers
`Layout::UNKNOWN`, and the manager acknowledges `unsupported` with
`unsupported_layout`. There is no fallback that draws something close enough,
which is section 111: validated layout enums and fields, and nothing else.

**Text is data and never structure** (section 112). The payload is built from
typed fields and serialised once; the firmware reads each field by name into a
`String`. A family message containing `{"layout": "EMERGENCY"}` is a string in
`body`, and the layout stays `MESSAGE`. Control characters, zero-width marks
and newlines are stripped by `layouts.sanitize` on the way in — a serial
display driver is exactly the kind of thing that would act on them.

### Text limits

Shortened by the backend before sending, so the firmware's buffers are sized
from the same numbers (section 77).

```text
title           24      status line     48
primary         32      max lines        5
secondary       48      code             8
body           140
```

`layouts.shorten` cuts at a word boundary and appends an ellipsis, and sets
`truncated`. Nothing relies on a screen running out of pixels.

---

## 4. Presentation types

```text
face_state           info_card            medication_reminder
appointment_reminder family_message       assistant_response
safety_check         safety_status        emergency_status
system_status        setup_code

task_reminder        general_reminder     alarm
routine
```

**The last four are PRD 12's** (§30), and they reuse two layouts the firmware
already draws: a task, a reminder and an alarm are `REMINDER`, and a routine's
progress is `STATUS`. **No firmware parser change was needed**, which is the
point of dispatching on layout rather than on type — and it is checked rather
than claimed: the type vocabulary is mirrored in `presentation_protocol.h` as
`TYPE_*` constants, compared against the backend tuple by a test that runs on a
laptop, and `test/test_presentation/test_main.cpp` parses one of each new
card.

The firmware does not branch on a type at all. The names are there for a log
line that says what kind of card was handled without quoting its content
(§67), and for that drift test.

**`setup_code` has no backend producer, deliberately.** Section 35 says to
reuse PRD 2's pairing flow and not to create a second pairing mechanism. PRD
2's code is generated on the robot and drawn by the robot, over BLE, before any
device record exists — routing it through a backend queue would *be* the second
mechanism. The type and the `PAIRING_CODE` layout exist so the firmware's
dispatch and the simulator cover them, and
`backend/tests/test_robot_builders.py` asserts that nothing queues one.

---

## 5. Priority and preemption

Lowest number wins. Section 16 fixes the order of nine of the eleven and asks
only that the ordering be deterministic; it is a table rather than a rule
because a rule would eventually be read differently in two places.

```text
10  emergency_status        50  appointment_reminder
20  safety_check            54  task_reminder
30  safety_status           56  routine
35  setup_code              58  general_reminder
38  system_status           60  family_message
40  medication_reminder     70  assistant_response
45  alarm                   80  info_card
                            90  face_state
```

The two PRD 11 does not rank sit between `safety_status` and
`medication_reminder`: a pairing code and "Nura needs attention" are both about
whether the robot is usable at all, so neither belongs under a reminder — and
neither may outrank anything to do with safety.

PRD 12's four sit in the order its §18 gives Today — an appointment, then a
task, then a routine, then a general reminder — with one exception.
**`alarm` ranks above an appointment**, because PRD 12 §4 defines an alarm as a
time-critical alert whose whole purpose is to get attention at a specific time.
It still sits below medication and far below the safety band, which is what
makes PRD 12 §64's "emergency preempts alarm" a comparison rather than a
special case.

`alarm` is also the one daily-life card a quiet mode does **not** suppress. An
alarm silenced by Sleep mode would be an alarm that does not work, since the
hour it is for is exactly the hour the robot would be asleep. What the robot
cannot do is *sound* it — its speaker reports `not_connected` — so the card
says "Nura cannot sound this", derived from the capability map rather than
written into the card.

**Only safety preempts.** A presentation ranked at or above
`ROBOT_SAFETY_PRIORITY_CEILING` (30) cancels the ordinary cards that are
*on the screen*. Anything else waits its turn. Section 17 says higher priority
*may* interrupt, and this is where the "may" is decided: an emergency takes the
screen, and a medication reminder does not cancel a message nobody has read
yet.

A queued card is never preempted — only a `sent`, `acknowledged` or `displayed`
one. An emergency that ends in ninety seconds should not also have discarded a
message that never had its moment.

---

## 6. Modes

```text
companion  information  focus  sleep  privacy
safety     emergency    offline  setup  error
```

Four of them are PRD 8's `assistant_preferences.mode` seen from the robot's
side (`normal` becomes `companion`). The rest are facts about the moment, read
off PRD 2's heartbeats and PRD 10's live safety state. **Nothing stores a
mode** — it is computed on every read, the same way PRD 10 does not store
emergency mode.

The order, which is the whole rule:

```text
emergency  >  safety  >  setup  >  offline  >  sleep / privacy / focus
           >  information  >  companion
```

**`error` is the robot's own word and the backend never says it.** Section 36
lists what it is for — Wi-Fi unavailable, something needing attention — and
every one of those is something only the robot can know; section 98 then says
the robot should fall back to safe local behaviour when the backend is
unreachable, which is precisely the case where the backend hears nothing. So
`error` is in the vocabulary, the firmware uses it locally, and
`modes.resolve` cannot return it. A test asserts that.

---

## 7. Face states

```text
idle  listening  thinking  speaking  happy  concerned  sleeping  privacy  offline
```

Nine, and deliberately not more. Section 28 forbids expression that implies a
medical judgement, so there is no `worried`, no `alarmed` and no `sad` for a
renderer to reach for because a symptom was severe — and serious moments use
`information` mode, which has no face at all.

The face is geometry, not artwork (sections 109, 110): `face_renderer.cpp`
turns a face state, a motion preference and the clock into two rounded
rectangles and a blink. `shapeFor` is a pure function, which is what makes it
the one piece of the renderer that can be reasoned about without a panel.

Section 29's rules are properties of that function: the blink is the only
movement; there is no animation *state*, so drawing something else needs
nothing unwound; `animate: false` means no blink at all; and a blinking face
and a still face say exactly the same thing.

---

## 8. Acknowledgement

```http
POST /api/v1/device-actions/presentations/{id}/ack
{ "state": "render_started" }
```

| State | Means | Row becomes |
| --- | --- | --- |
| `received` | the envelope arrived | `acknowledged` |
| `render_started` | it is on the screen and staying there | `displayed` |
| `render_completed` | the device is finished with it | `completed` |
| `failed` | the driver could not draw it | `failed` |
| `unsupported` | this build does not know this layout or version | `not_supported` |

**`render_started` and `render_completed` say different things about the
screen, not about the drawing.** A robot that has drawn a card keeps it there
until something replaces it, and reports `render_started`: the row sits in
`displayed`, which is what makes it preemptable and what the Nura Device screen
shows as "on screen". `render_completed` is for a presentation the device is
*finished with*, and the backend finishes a displayed card by itself when a
later one is drawn over it.

`queued` appears in none of the transitions: a device cannot report having
rendered something it was never sent, and that is a 409.

Repeating an acknowledgement is accepted and changes nothing, so a device whose
response was lost can send it again. Moving backwards is a 409 — that is not a
retry.

**`failure_code` is a stable code or nothing.** Never the device's own error
text, which could quote a payload back (section 67):

```text
render_failed  unsupported_layout  unsupported_capability
unsupported_protocol_version  no_display  device_error
```

### The constraint underneath

`displayed_at` is written by exactly one function, and the database refuses
anything else:

```sql
CHECK (displayed_at IS NULL
       OR (ack_state IS NOT NULL
           AND ack_state IN ('render_started', 'render_completed')))
```

The parenthesised half matters more than it looks. A SQL `CHECK` is satisfied
when it evaluates to TRUE *or null*, and `ack_state IN (…)` is null when
`ack_state` is — which is precisely the row this constraint exists to refuse.
Written the short way it accepted it, and a test that writes past the service
is what caught that.

---

## 9. Capabilities

```http
POST /api/v1/device-actions/capabilities
{
  "capabilities": { "display": "not_verified", "speaker": "not_connected" },
  "source": "self_test",
  "firmware_version": "0.1.0"
}
```

Twelve keys, not one `robot_ready` boolean (section 10):

```text
display  display_text  display_animation
speaker  tts  audio_playback
microphone  wake_word
camera  camera_detection
buttons  touch
```

Four states, and the third is mandatory (section 91):

| State | Means |
| --- | --- |
| `available` | proven to work |
| `unavailable` | not fitted |
| `not_verified` | the driver is present and nothing physical has been proven |
| `not_connected` | nothing has been reported about this |

**Only a device can report `not_verified`.** Section 12's point is that a
compiled driver is not a working one, and the backend has never seen a build —
so it cannot tell the difference and does not guess. What the backend knows is
whether a robot has said anything, and the honest answer to that is
`not_connected`, which is what a missing row reads as.

**The firmware reports `not_verified` for a panel whose `init()` succeeded.**
That return value means this code talked to something over SPI; it does not
mean a person has seen a legible frame, and section 93 keeps that verification
as a separate, later, physical step.

A partial report is normal and erases nothing it leaves out. An unknown key or
state is a 422 rather than a silent drop: a firmware inventing a capability is
a protocol mismatch its author should see.

**A report goes stale when the firmware changes.** Section 124 asks for stale
reports to be handled, and the useful definition is not "old" but "proven by a
build that is no longer running". An `available` reported by an earlier
firmware version — or one older than 30 days — reads as `not_verified` until
the robot says so again. The stored row keeps what the device said; the
downgrade is derived, and can only ever move towards *less* certainty.

---

## 10. Expiry

```text
medication_reminder   30 min        safety_check      state-driven
appointment_reminder  24 h          safety_status     state-driven
family_message        24 h          emergency_status  state-driven
assistant_response     5 min        face_state        replaced, not expired
info_card             30 min
system_status          1 h
setup_code             5 min  (no backend producer; see §4)
```

Every one is a stored instant and a comparison, the same shape PRD 10 uses for
its deadlines. `queue.expire_due` runs on every read path — the device's fetch,
the heartbeat, the app's status read, the history endpoint — so a presentation
is never handed over late whether or not any job has run.

`scripts/robot_maintenance.py` runs it on a schedule as well, and **nothing
depends on that**. Unlike PRD 10's worker, there is no deadline here whose
passing has to cause something to happen; the job is housekeeping, so a table
of stale rows does not make the history screen read as though something is
waiting.

---

## 11. Deduplication

Section 57's key is `source:source_id:type`, computed by the builder:

```text
medication:7f3a1c20-…:0:medication_reminder
family_message:9b2e…:family_message
safety:4c71…:escalating:safety_check
system:idle:face_state
```

A retried request, a replayed job and two concurrent workers all converge on
one card. For everything except the idle face that holds for the whole life of
the row: a dose reminded once is not reminded again by a retry an hour later.

Two parts of the key are worth noticing. A medication key carries the dose's
**snooze count**, because a snoozed dose is genuinely a second occasion — and
the reconciler withdraws the earlier card, or the robot would hold two cards
for one tablet. A safety check's key carries the event **status**, so the
second prompt replaces the first card rather than folding into it.

The idle face is the one `repeatable` presentation: a face is a state the robot
returns to rather than an occasion that happened once, so its key folds only
into a card that is still open.

---

## 12. The firmware's state machine

```text
IDLE  ──▶  FETCHING  ──▶  RENDERING  ──▶  WAITING
             │                │              │
             ▼                ▼              ▼
           ERROR            ACKING  ────────▶ IDLE
```

Kept separate from the connectivity state machine in `main.cpp` and from
anything to do with safety, which section 88 asks for explicitly: what the
robot is *showing* and whether it is *online* are different questions, and a
single machine covering both is how a robot ends up stuck on a card because
Wi-Fi dropped.

`presentation_manager::loop()` does at most one unit of work per call, so the
BLE stack and the button are never starved by a render.

### Firmware modules

```text
presentation_protocol.*  the vocabulary, parsed by tests on two other sides
presentation_manager.*   the state machine above
card_renderer.*          JSON → Card, then dispatch on layout
face_renderer.*          a face state → geometry (pure, testable)
display_driver.*         DisplayDriver, Simulated and Physical
audio_output.*           AudioOutput, Silent and I2S; TextToSpeechProvider
display.*                PRD 2's panel owner, plus three primitives
backend_client.*         PRD 2's client, plus the three calls above
```

Section 89 asks for existing `display.*`, `audio.*` and `backend_client.*` to
be reused if cleanly structured, and they were: `display.cpp` still owns the
panel and gained `drawEyes`, `drawLines`, `blank` and `setBrightness`;
`I2SAudioOutput` reuses the I2S driver `audio.cpp` already installs rather than
installing a second one on the same port.

---

## 13. What has not been verified

Everything in this document is implemented and none of it has driven hardware.

- **No frame has been drawn on a panel.** The physical display driver compiles
  (`pio run -e xiao_esp32s3_peripherals`) and reports `not_verified`.
- **No sound has been played.** `SilentAudioOutput` returns false from
  `playChime`, and `speakText` returns false everywhere — there is no
  `TextToSpeechProvider` implementation.
- **No microphone, camera, button or touch panel exists.** All four are
  reported `not_connected` or `unavailable` by the firmware's self-test.
- **No physical acknowledgement has reached the backend.** Every `displayed`
  row in any database came from a simulated acknowledgement in a test.
- **The firmware's own unit tests have never run.** They compile for the target
  (`pio test -e xiao_esp32s3 -f test_presentation --without-uploading
  --without-testing`); PlatformIO's Unity tests execute on the board, and there
  is no board.
- **No alarm has ever sounded on the robot.** PRD 12's `alarm` card is built,
  ranked and tested, and the robot's only audio output is the silent one — so
  the card carries "Nura cannot sound this" and that sentence is the whole
  truth of it.
- **None of PRD 12's four cards has reached a panel.** They parse in the
  firmware's Unity tests, which have never run on a board, and they render in
  the simulator, which is a Python script.

What *is* verified on a development machine: the vocabulary agreement across
all three sides, the queue, the priority table, the preemption rule, the expiry
comparison, the acknowledgement state machine, the privacy filter, and the
whole experience through the simulator — see
`backend/tests/test_robot_simulator.py` and `scripts/robot_simulator.py`.

Simulator proof is not hardware proof.

---

## See also

- [ADR 0014](../decisions/0014-robot-presentation-architecture.md) — why it is
  shaped this way
- [The companion experience](../architecture/robot-companion-experience.md) —
  what it feels like, and the privacy rules
- [The provisioning protocol](provisioning-protocol.md) — PRD 2's pairing and
  heartbeat, which this extends
- [Safety monitoring](../architecture/safety-monitoring.md) — PRD 10's state,
  which the safety presentations render
