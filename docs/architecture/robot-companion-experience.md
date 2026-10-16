# The robot companion experience

**Status: built, green, and never shown to anybody.** PRD 11 is implemented —
the presentation queue, the priority and preemption rules, the canonical face,
serious information mode, the emergency display, the five domain builders, the
capability model, the preferences, the device fetch/ack API, the simulator, the
mobile Nura Device screens and the firmware's presentation layer. What does not
exist is the robot: no panel, no speaker, no microphone, no button, and no
frame has ever been drawn. This document says so wherever it is relevant rather
than once at the end.

The wire contract is
[the presentation protocol](../device/presentation-protocol.md); the reasoning
is [ADR 0014](../decisions/0014-robot-presentation-architecture.md).

Three sentences the whole design exists to keep true:

- **A companion first and a screen second.** Calm, recognisable, and never a
  notification billboard.
- **The robot is additive.** Nothing in the app or the backend depends on it.
- **Nura never says it showed, spoke or played anything unless a device said
  so.**

---

## 1. What it is, in one picture

```text
         what is true now                            what the robot shows
  ┌──────────────────────────┐                   ┌────────────────────────┐
  │ PRD 5  a dose is due     │                   │                        │
  │ PRD 7  a visit tomorrow  │   presenter       │   one card at a time   │
  │ PRD 9  an unread message │  ──refresh──▶     │   or the companion     │
  │ PRD 10 a live safety     │                   │   face                 │
  │ PRD 8  the chosen mode   │                   │                        │
  └──────────────────────────┘                   └────────────────────────┘
                                  device_presentations
```

`presenter.refresh` is the only function that decides what should be on the
screen. It reads current state and makes the queue match — so there is no event
that could have been missed, and a card cannot describe something that has
stopped being true.

---

## 2. Companion mode, and the face

The default is the canonical Nura face: two rounded eyes, a slow blink, and
nothing else. Section 109 rules out avatar packs and section 110 rules out
local media, so the face is geometry — `face_renderer.cpp` turns a face state,
a motion preference and the clock into a handful of numbers.

Nine face states (`idle`, `listening`, `thinking`, `speaking`, `happy`,
`concerned`, `sleeping`, `privacy`, `offline`) and deliberately not more.

**No face ever carries a health judgement** (section 28). There is no
`worried`, no `alarmed` and no `sad` for a renderer to reach for because a
symptom was severe, and `concerned` is described in the app as *attentive*.
Serious moments do not get a face at all — they get information mode, which is
section 7.

Animation is subtle, short, interruptible and non-essential (section 29): a
blinking face and a still face say exactly the same thing. Reduced motion
removes the blink entirely.

---

## 3. Serious information mode

Section 7's locked decision. When the moment is a medication-safety context, a
Safety Monitoring prompt, an SOS, an escalation, or anything privacy-sensitive,
the robot drops the face and shows plain text.

It is structural rather than remembered:

- `MODE_FACES` maps `safety`, `emergency`, `setup` and `error` to **no face**.
- The `serious` flag on a payload means no decoration and high contrast, and
  `card_renderer` passes it to the driver rather than deciding anything itself.
- `builders.assistant.build` chooses the layout *from* `serious`, so there is
  no way to ask for an animated presentation of a serious reply.
- Section 106: a serious or emergency card uses the plain text colour rather
  than the brand accent, in the firmware and in the app's preview alike.

---

## 4. The emergency display

Section 8, and the sentence it forbids. The card is built from PRD 10's own
state by `wording.emergency_lines`, which is given three facts — who an alert
*record* exists for, whether any calling provider is configured, whether there
were contacts at all — and has no argument that could make it claim somebody is
coming.

```text
EMERGENCY MODE

Nura is processing your safety request.
In-app alert created for Ayesha.
Calling is not configured.
```

The third line is in every deployment, because no calling provider exists. "Help
is on the way." cannot be produced by any code path, and
`backend/tests/test_robot_wording.py` reads every string in the module —
including every generated sentence at its edges — and asserts it.

A cancelled escalation says so for two minutes rather than going quiet
(section 114), because leaving a stale emergency card up is the dangerous kind
of stale. A caregiver acknowledgement may be shown (section 115) and says only
that somebody pressed a button in their own app — never that they are nearby,
on their way, or at the door.

Safety presentations have **no expiry instant** (section 113). They are tied to
the live PRD 10 event and are withdrawn when it resolves, which is what the
next reconciliation does.

---

## 5. Safety monitoring, shown honestly

```text
Safety Monitoring
ON until 10:30 PM
```

That is the whole card. It says monitoring is on and until when, both of which
PRD 10 knows. **"Fall detection active" cannot be produced** — there is no
sentence in the wording module that could, which is section 9 met by absence
rather than by a check.

Nothing the robot does touches safety. `builders.safety.sync` reads PRD 10 and
writes only to `device_presentations`; it uses `monitoring.peek_session`, which
reports an expired session as gone **without ending it**, because a display
request that expired somebody's monitoring as a side effect would make the
presentation path load-bearing for safety — the opposite of section 100.

---

## 6. Privacy: the screen is in a room

The robot sits on a shelf in a room other people walk through, and that is the
whole reason section 22 exists.

| Level | Shows |
| --- | --- |
| `full` | "Metformin / 500 mg · 8:00 PM" |
| `name_only` | "Metformin / 8:00 PM" — the amount often says what the condition is |
| `private` | "Medication / Reminder due" — and nothing else |

**`private` is the default** (section 104), so a robot arriving in a household
does not start naming somebody's tablets before anybody has chosen anything.

**The redaction happens while the payload is built**, not when it is drawn. The
row stored in `device_presentations` is already the redacted one, so the app's
own history endpoint cannot show more than the robot was sent — a private
reminder reads as "Reminder due" there too.

**Privacy Mode overrides the preference, downwards only** (section 33). Somebody
who chose "full details" and then put Nura in Privacy Mode gets the private
card: the mode is something they are doing now and the preference is something
they set once.

Family messages need four things to be true (section 24): an authorized stored
message exists, the `communication` permission is *still* granted, the robot's
message display is enabled, and the display capability supports it. The
permission is re-checked when the card is built — PRD 10 section 86's lesson,
applied to PRD 9's permissions — and the message itself is never invalidated
(section 101); it simply stops being queued.

---

## 7. Audio, which has never made a sound

`AudioOutput` is the abstraction (section 41) and `TextToSpeechProvider` is
declared with no implementation (section 42). `SilentAudioOutput` is the driver
on every build: it logs what it would have played, returns **false**, and
reports every audio capability as `not_connected`.

Three read-aloud preferences exist and all default off (sections 43, 104). They
are offered even though nothing can honour them, which is section 49 — somebody
may reasonably decide today that their messages should never be read out in a
room. Their wording is what keeps that honest: *"When Nura has a working
speaker, read messages out loud."*

`speak` on an envelope requires three things: the capability, the preference,
and a mode that does not suppress audio. It has been false on every envelope
this project has ever built.

**Nothing speaks on its own** (section 82). There is no code path that reads a
card aloud because it arrived.

---

## 8. Capability-aware settings

Section 47: do not present live controls as if they work. The Audio section is
not a set of disabled switches — it is a sentence saying this Nura has not
reported a speaker, because a greyed-out volume slider still implies there is a
speaker to be loud.

Brightness and volume are five discrete steps rather than a slider
(sections 44, 45). The column stores 0–100 so a future slider needs no
migration; five steps is enough to be useful on a device nobody can see yet,
and a slider for a screen that does not exist is a control pretending to do
something.

**Reduced motion has three positions**, not two (sections 30, 105). Null means
*follow the account's accessibility preference* and is the default; true and
false are deliberate overrides. A plain boolean would have had to pick a value
and would then have stopped following the accessibility setting the first time
anybody opened the screen.

---

## 9. What each mode does

| Mode | Behaviour |
| --- | --- |
| `companion` | the face, resting (section 5) |
| `information` | a card is on the screen; derived from the queue (section 6) |
| `focus` | minimal motion, no casual prompts — reminders still go through (section 32) |
| `sleep` | dim, sleeping face or blank; medication follows PRD 5's settings; emergency overrides (section 31) |
| `privacy` | sensitive previews suppressed, read-aloud suppressed, state shown (section 33) |
| `safety` | the check-in prompt, as information (sections 7, 9) |
| `emergency` | PRD 10's actual state, overriding everything (section 8) |
| `offline` | the robot's own local card; anything queued stays queued (sections 34, 99) |
| `setup` | "Finish setting up in the Nura app" — no pairing code (section 35) |
| `error` | the robot's own word; the backend never says it (sections 36, 98) |

Sleep and privacy are the only two that suppress ordinary cards, because they
are the two a person chose to mean "do not put things in front of me". Offline
is **not** a suppression: sections 20 and 99 are explicit that a useful
unexpired presentation stays queued for a robot that is not there, so it is
waiting when the robot comes back.

Nothing claims a camera or microphone has been switched off in hardware
(section 33's last line) — that is a thing only the device can report, and no
device reports it.

---

## 10. Offline, both ways

**Robot offline, backend up** (section 99). Cards stay queued until they
expire. Nothing is fetched, so nothing is acknowledged, so nothing is
displayed — which is why section 20's rule is easy to keep. The app says:

> Robot offline — this item remains available on your phone.

**Backend unreachable, robot up** (section 98). The firmware shows its own
offline card locally and backs off; it does not retry in a loop and it never
shows a stale emergency as though it were current.

**App offline** (section 97). Core health workflows continue as prior PRDs
define them; the robot's settings simply fail to save and say so.

---

## 11. Where the words live

Section 75. Two modules, and the split is deliberate:

- `backend/app/services/robot/wording.py` — anything that could make a claim
  about hardware: capability labels, state labels, history lines, the emergency
  lines, the offline note, the hardware note.
- `mobile/src/features/robot/copy.ts` — the words that are about the *app*:
  titles, section headings, and what a setting will do when there is hardware
  to do it with.

Both have an exhaustive copy audit (`test_robot_wording.py` and
`robotCopy.test.ts`) that collects every string and applies the four rules:
nothing says help is coming, nothing describes a detector, nothing claims the
robot showed or said anything, and nothing promises anything.

Localization readiness (section 76): the protocol carries already-shortened
concise text rather than localization keys, so the firmware needs no string
table and no font set beyond what it draws today. The limits in
`presentation_protocol.h` are character counts, and a language with longer
words will need them revisited — documented here rather than discovered later.

---

## 12. Analytics and logs

Section 68's generic events only, and PRD 10's rule carried forward. The
backend logs `robot.presentation_queued`, `robot.presentation_sent`,
`robot.presentation_displayed`, `robot.presentation_cancelled`,
`robot.refresh` and `robot.preference_changed` — each with a type, a layout or
a count, and **never a payload** (section 67).

`layouts.without_sensitive_text` exists for diagnostics and returns the shape:
the layout, which fields were present, and the flags. The firmware is the same:
`SilentAudioOutput` logs a character count rather than the text it was given,
and the physical display driver logs nothing at all.

---

## 12a. Daily life on the screen (PRD 12)

PRD 12 adds four card types through this same queue — §30 forbids a second
transport — and changes nothing about how any of it works. No new layout, no
new acknowledgement state, no new transport, and the same reconciliation:
nothing in PRD 12's services calls into the robot, and
`services.robot.presenter.refresh` reads what is true and makes the queue
match.

| type | layout | rank | quiet modes |
|---|---|---|---|
| `alarm` | `REMINDER` | 45 | **not** suppressed |
| `task_reminder` | `REMINDER` | 54 | suppressed |
| `routine` | `STATUS` | 56 | suppressed |
| `general_reminder` | `REMINDER` | 58 | suppressed |

Three decisions carry the interesting parts.

**An alarm is not an ordinary card.** It ranks above an appointment, because
PRD 12 §4 defines it as a time-critical alert whose purpose is to be noticed at
a specific time, and it is the one daily-life card Sleep and Privacy mode leave
alone — an alarm silenced by Sleep mode would be an alarm that does not work.
What the robot cannot do is sound it: the speaker reports `not_connected`, so
the card says "Nura cannot sound this", and the line comes from the capability
map rather than from the card, so it disappears on its own if a chime ever
appears (PRD 12, §65).

**Daily-life content gets its own privacy level.** PRD 12 §32 asks for the same
preview control over a task or a routine name that §6 gave a medication, and it
is the same three levels on a separate preference: `daily_life_privacy_level`,
defaulting to `full`. That is a different default from medication and a
deliberate one — "Call the physiotherapist" on a shelf is a note to self, and
hiding it by default would make the robot useless for what PRD 12 is for.
Somebody with a task they would rather not have read over their shoulder sets
`name_only` or `private`, and the redaction happens while the payload is built,
so the stored row is already the redacted one.

**One switch turns all four off.** `daily_life_display_enabled`, which is §31's
additive principle as a setting: the task, the reminder, the alarm and the
routine are untouched, every one of them still works on the phone, and only the
cards go.

The routine card is §33's example, rendered as a `STATUS`: the routine's own
name as the title, then "2 of 3 complete", then "Next: Stretch", then PRD 11's
"Use the Nura app to respond." — because there is still no input. A level
change drops the step name before the title, because a step title is the part
that says what the routine is actually for.

Full detail in
[daily-life-assistant.md §13](daily-life-assistant.md).

---

## 13. What is not validated, and what is not built

The list PRD 11 section 135 asks for, in full.

- **The robot has not been built.** No enclosure, no wiring, no assembly.
- **The display driver has never been physically tested.** It compiles under
  `NURA_HAS_DISPLAY=1` and reports `not_verified` when `init()` succeeds,
  because that is not evidence a person saw a legible frame.
- **The speaker and amplifier have never been physically tested.** No sound has
  been produced by this project. `playChime` returns false.
- **The microphone has never been tested**, and nothing in the firmware reads
  one. No wake word, no speech recognition.
- **There is no real voice response.** No `TextToSpeechProvider` exists, so
  `speakText` returns false everywhere.
- **The app has never run on a phone.** Every mobile test is jest-expo.
- **No physical presentation acknowledgement has been received.** Every
  `displayed` row in any database came from a simulated acknowledgement in a
  test.
- **The firmware's own unit tests have never run.** They compile for the
  target; PlatformIO's Unity tests execute on a board.
- **No camera, button or touch panel exists**, and no detector was added — PRD
  10's statement that none is clinically validated is unchanged.

What *is* verified, on a development machine: the queue, the priority table,
the preemption rule, the expiry comparison, the deduplication key, the
acknowledgement state machine and its database constraint, the privacy filter
at all three levels, the capability model including stale reports, the
three-way protocol vocabulary agreement, and the whole experience end to end
through the simulator.

Simulator proof is not hardware proof.

---

## See also

- [The presentation protocol](../device/presentation-protocol.md)
- [ADR 0014](../decisions/0014-robot-presentation-architecture.md)
- [Safety monitoring](safety-monitoring.md) — the state the safety cards render
- [Caregivers and family](caregiver-and-family.md) — where family messages come
  from, and why a caregiver controls nothing here
- [The Nura assistant](nura-assistant.md) — the bounded hand-off from a reply
  to a card
- [The provisioning protocol](../device/provisioning-protocol.md) — PRD 2's
  pairing and heartbeat
