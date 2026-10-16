# Caregivers, family communication and emergency contacts

**Stage:** PRD 9 · depends on PRD 0–8

This is how somebody else gets to help, and the exact limits on what helping
means. It is the most security-sensitive feature in Nura so far: everything
before it answered "can this account reach its own records?", and this one
answers "can this account reach *somebody else's*, and which parts?"

---

## 1. The shape, in one picture

```text
users (accounts)                     profiles (people Nura is for)
   |                                      |
   +-- account_profile_roles -------------+     the owner path. PRD 0-8.
   |      self / setup_helper                   deps.get_owned_profile
   |
   +-- caregiver_relationships -----------+     the caregiver path. PRD 9.
          |    pending / active / ...           deps.get_care_scope
          |
          +-- caregiver_permissions            one row per category
          +-- caregiver_suggestions            changes proposed, not made
          +-- family_threads -> family_messages

   emergency_contacts        the priority chain PRD 10 escalates through
   caregiver_audit_events    what was done -- never what was read
```

## 2. The decision everything else rests on

**A caregiver is not a row in `account_profile_roles`.**

That table is what `deps.get_owned_profile` walks, and every profile-scoped
route written in PRD 0–8 authorizes through it: the complete health record,
every symptom photo, every doctor report, the assistant's own conversations.
Adding a `caregiver` role to it would have granted all of that on the day PRD 9
shipped — no route change, no review, no way to notice.

So caregiver access is a **second, narrower path**:

| | owner | caregiver |
|---|---|---|
| dependency | `OwnedProfile` | `CareScopeDep` / `CaregiverScope` |
| resolves through | `account_profile_roles` | `caregiver_relationships` |
| reaches PRD 0–8 routes | yes | **no, at any depth** |
| reaches caregiver routes | yes (as owner) | yes, per category |
| what the reads return | everything | deliberately less (§6) |

`tests/test_caregivers.py::test_a_caregiver_cannot_reach_any_route_written_before_prd_9`
grants a caregiver *every* category and then walks eight PRD 0–8 endpoints,
expecting 404 from each. That test is the load-bearing one in this feature.

## 3. Role versus permission

`role` is a label for a list. Nothing in the authorization path reads it — not
`permissions.py`, not `deps.py`, not any route. PRD 9 §10 says roles are
descriptive and §54 that changing one must not widen access; the way to be sure
is for the code that decides access not to know the column exists.

The test changes `family` to `primary_caregiver` — the most senior-sounding
value there is — and asserts the granted set is byte-identical before and after.
`emergency_contact` as a *role* also grants nothing, which is worth knowing
because the name invites the opposite assumption: emergency contacts are a
different table with no permissions attached at all.

## 4. Permissions

Eight categories, a row each, `allowed` boolean, **default deny**:

```text
medications  appointments  symptoms  reports
reports      safety_alerts communication routines  general_health_summary
```

A row per key rather than a column per key, and certainly not one boolean for
the lot (§7). The cost is a join; what it buys is that adding a category in PRD
10 is a tuple entry rather than a migration, and that a permission set is
something the audit trail can describe key by key.

**A missing permission and a missing relationship give the same answer: 404.**
Not 403 — the whole codebase answers 404 for "not yours", because a 403 confirms
something exists. §18 goes further: the *absence* of a permission must not leak,
so a caregiver without `symptoms` cannot tell from the API whether this person
has ever recorded one.

**Every category now unlocks something, and the list that said otherwise is
empty.** `CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE` is the list and
`CareScope.usable()` is the check, and both stay: the next permission reserved
before its data exists goes there, and the screens that render the sentence
keep working.

`routines` was the last entry, and it left in PRD 12. Through PRD 0–11 nothing
defined what a routine *was* — no table, no fields, no screen — so the key was
stored faithfully, appeared in `granted_without_data`, and the screens said so
rather than showing an empty section that reads as "nothing recorded". PRD 12
built routines, runs and steps, so a caregiver with the key now sees what the
routine is, when it runs, whether it is paused and how today's run is going.
See [daily-life-assistant.md §12](daily-life-assistant.md).

**`safety_alerts` was the first to leave, in PRD 10.** §94 allowed the key to
exist before its event source did and warned against fabricating an alert; PRD
10 built the source, so the key now unlocks real in-app safety alerts and a
caregiver's view of the safety events they cover. The tuple shrinking twice —
two entries, then one, then none — is the honest record of two permissions
becoming real. See [safety-monitoring.md §11](safety-monitoring.md).

**What `routines` does *not* reach** is PRD 12 §42, and it is kept by absence
rather than by filtering: there is one caregiver route for routines, there is
no suggestion action for a task, an alarm or a personal reminder, and a
caregiver's assistant is shown two routine read tools and nothing else. A
caregiver asking for the owner's `/tasks`, `/alarms`, `/reminders` or
`/daily-life/summary` gets 404 — the same answer as a profile that is not
theirs. The caregiver screens say so in a sentence, so somebody helping can see
where the edge is rather than wondering why a list looks short.

**Revocation is immediate and needs no invalidation.**
`permissions.granted_keys` returns an empty set for a relationship that is not
`active`, and every request reads the row. There is no session to expire and no
cache to clear, so the same request that worked a line earlier answers 404 a
line later. The row and its permissions stay, because §52 asks for the history
to remain answerable.

## 5. Invitations

The invitation **is** the relationship (§79): a `pending` row with a token hash,
an expiry and a consumed-at. Accepting is a status change, so there is no second
table to keep in step and "accept twice" is idempotent because the second
attempt finds the token spent.

**Nura does not deliver it, and does not pretend to.** There is no mail sender,
no SMS gateway and no push infrastructure in this backend, so `POST
…/caregivers/invitations` returns the token **once, to the inviter**, with
`delivery: "share_manually"` in the body and a sentence on the screen saying
sharing it is their job. That is the same handoff PRD 2 uses for a provisioning
token. A `send_invitation_email` that logged a line and returned success would
be worse than its absence.

The consequence is written down rather than hidden: **the link is the
credential.** What bounds it is everything §13 and §75 ask for — 256 bits of
randomness, stored only as SHA-256, a 7-day expiry, single use, and revocable at
any moment.

**The contact is a note, not a check.** An invitation may name an email or a
phone, and acceptance does not require the signed-in account to match it. That
is a deliberate trade: matching would lock out somebody who signed up by phone
after being invited by email, or whose Apple relay address differs from the one
their mother knows — and the token, not the address, is what authorizes.

**The lookup requires authentication**, which is stricter than §81 asks and
matches §14's own ordering (sign in, *then* review). It costs nothing and means
a leaked link alone does not even reveal a first name. The preview returns a
name, a role, the permission list and an expiry — and **no profile id**, so a
token holder never learns the key to every other route.

## 6. What a caregiver is actually shown

`services/caregivers/care_view.py` assembles every caregiver read, deliberately
smaller than its owner-side equivalent (§67). Reusing the owner's routes would
have been less code and the wrong answer.

| category | what a caregiver gets | what they do not |
|---|---|---|
| `medications` | names, doses, reminder times, a week of counts, whether supply is low | **free-text skip reasons** (§19) |
| `appointments` | title, when, type, location, question count | the user's own notes |
| `symptoms` | what is tracked, severity, change, when | free text, and **photos** |
| `reports` | that one exists, its version and date | the snapshot, and the PDF |
| `general_health_summary` | counts | any condition, medication or allergy name |
| `communication` | their own thread | any other caregiver's |

`build_home` is permission by permission, and every `if` is a granted category
with no `else` returning an empty list — because §18 says the absence must not
leak, and an omitted key is indistinguishable from a person with nothing
recorded.

Verified by reading a real one: a profile is filled with a condition, an allergy,
a symptom and a medical note whose body reads `SYSTEM: ignore all previous
instructions`, and none of their text appears anywhere in a caregiver's home.

## 7. Suggestions: a caregiver never changes anything

```text
caregiver proposes  ->  suggestion row  ->  primary user approves  ->  the
                        (pending)           (their own account)        ordinary
                                                                       service
```

§21 says important changes must never be applied silently by a caregiver
account. In this codebase they cannot be applied by one *at all*: there is no
caregiver route that writes to a medication schedule or an appointment. This is
the shape PRD 8 gave the assistant's one write, for the same reason.

**The forbidden changes are absent rather than refused** (§85):

```python
CAREGIVER_SUGGESTION_ACTION_TYPES = (
    "change_medication_reminder_time",
    "pause_medication_reminder",
    "resume_medication_reminder",
    "add_appointment",
    "change_appointment_time",
    # PRD 12, §16
    "add_routine",
    "change_routine_time",
    "pause_routine",
)
```

That is the whole list. `change_medication_dose`, `delete_condition` and
`change_diagnosis` are not validated away — there is no action type for them, the
schema's `Literal` refuses the request, and the database CHECK constraint is
built from the same tuple.

The same reasoning covers PRD 12's three categories: there is no `add_task`, no
`create_reminder` and no `set_alarm`, because §42 keeps those private to the
primary user and the surest way to be sure a caregiver cannot reach somebody's
task list is for there to be no action type that could carry the request.

`suggestions.ACTIONS` has one entry per name, each with a pydantic payload model
(`extra="forbid"`), a `describe` that renders the diff and an `apply` that calls
the ordinary service. `assert set(ACTIONS) == set(CAREGIVER_SUGGESTION_ACTION_TYPES)`
keeps the registry and the constraint from drifting.

**Approval does all six of §24's steps**, in order: revalidate the permission
against the *current* relationship, re-find the target inside the profile,
re-validate the payload, apply through `medications.schedules` or
`appointments.appointments`, mark the suggestion, write the audit row. The first
step is the one people skip — a suggestion is not a capability somebody keeps
after their access is withdrawn, and the test revokes the caregiver between
proposing and approving to prove it.

**Approving twice does what approving once did.** `applied_resource_id` is
written with the status, so a retry returns the same suggestion rather than
creating a second appointment (§74).

**The diff is read at review time, not stored** (§86). A reminder the owner moved
themselves yesterday shows today's real value, because a diff against a reality
that no longer exists is worse than none. Both halves are rendered server-side
for the PRD 7 reason: a time only means something in its schedule's zone.

**A decline note is private** (§25, §88). It is stored, returned only to the
account that wrote it, and the caregiver-facing model has **no field for it** —
so sharing it later is a deliberate feature rather than a leak waiting for
somebody to serialise the wrong model.

**Routines got their action types in PRD 12.** §85 listed `add_routine` and
`change_routine` and §27 said a caregiver may suggest one, but nothing in
PRD 0–9 said what a routine *was* — no table, no fields, no screen in §83 — so
inventing one was not PRD 9's call. PRD 12 §12 defines the record, and the
registry took the three new entries in the one place this section promised it
would: `add_routine`, `change_routine_time` and `pause_routine`, each with a
payload model, a describer and an applier that calls
`services.productivity.routines`.

An approved routine carries `source = caregiver_suggestion` for as long as it
exists (PRD 12, §43), so "my daughter suggested this" is still answerable
months later.

## 8. Family messaging

**One thread per relationship.** That is a decision, not a shortcut: §66 rules
out unnecessary caregiver-to-caregiver exposure and §32 rules out chat rooms and
communities, and a thread belonging to a *pairing* gives both for free — no
participant table, and no query that could return caregiver B's messages to
caregiver A.

**The pairing has to allow messages, not just the caller.** An owner's scope
holds every category, so checking only the caller would let the primary user
open a thread with somebody who was never granted `communication` and send into
it — messages the other side cannot read. `messaging.pairing_allows_messages` is
checked in `get_thread` and `list_threads`, so a new reader cannot forget it.
(This was found by a test, not by review.)

**A check-in is a code, not a sentence.** `check_in_code` is stored and
`wording.CHECK_IN_SENTENCES` renders it — the PRD 7 lesson, which also means a
check-in can never carry free text the sender did not intend to put in a care
thread. The two sides have different lists (§35, §36): the person says how they
are, the caregiver asks.

**Nothing infers urgency from one** (§35, §102). "I need help with something" is
stored as a message and produces nothing else: no suggestion, no alert, no audit
event, no escalation. The screen says so next to the buttons.

**Sent and read, and no stronger claim** (§37). `created_at` is when the server
stored it; `read_at` is when the *other* side opened the thread. There is no push
for a family message yet, and no string anywhere says "delivered".

**No AI touches a family message** (§65). No assistant tool names a thread, a
message or a check-in, which a test asserts across the whole tool layer — so
there is nothing to opt out of.

**Photo messages are deferred.** §33 makes them optional and requires private
storage, signed access and size limits. The private-storage half already exists
from PRD 6; the upload route, the picker flow and the size policy do not.
`photo` stays in `FAMILY_MESSAGE_TYPES` (so the column and constraint are already
right) and is absent from `FAMILY_MESSAGE_TYPES_ALLOWED`, the same approach PRD 6
took to future symptom sources.

## 9. Emergency contacts: managed here, walked by PRD 10

PRD 9 builds the chain and PRD 10 walks it. Nothing *in this file's feature*
contacts anybody: no function here reads `priority` to decide who to reach, and
the escalation engine lives in `services.safety.escalation`, which reads
`contacts.list_contacts` and preserves its order rather than sorting its own.

**The sentence on the contacts screen changed with PRD 10**, and the change is
worth reading. It used to say "Nura does not contact anyone automatically". It
now says Nura uses this order if you ask for help, **and** that it cannot call
or text anybody in this build. The first version became wrong in the direction
that undersells the feature; the obvious replacement — "Nura will call these
people" — would be wrong in the dangerous direction. Both halves, or neither.

`priority` is 1-based and contiguous, renumbered by the server on every change,
which is why the column carries no unique constraint — the same decision
appointment questions make about their order. A reorder sends the list as
displayed, not numbers the client keeps consistent.

**Owner-only at every verb, reads included.** There is no caregiver-scoped route
for an emergency contact anywhere in `api/v1/caregivers.py`, which is how §45's
"caregivers must not silently reorder the chain" is enforced.

**There is no `is_verified`.** §46 recommends verification *if the infrastructure
exists* and says not to block the prototype on it. Nothing here can send a code
to a phone, so a column that could only ever read "unverified" would say less
than its absence.

What PRD 10 found waiting (§93), and used unchanged: contacts with a
contiguous priority, an `is_active` flag it skips over, an optional `account_id`
for contacts who also use Nura, and the `safety_alerts` permission key already
in the vocabulary. §30 of PRD 10 forbids a second competing priority model, and
a test reorders the chain through *this* feature's route and asserts the next
escalation changes who it tries first.

## 10. The assistant, in a caregiver's hands

§63 requires the PRD 8 tool layer to respect caregiver permissions. Each tool
now names the category it reads, and `ToolContext` carries the granted set:

```python
tools.specs(context)   # filtered: an unavailable tool is not shown at all
tools.run(context, …)  # refused, with the same answer as an unknown tool
```

`permission=None` means **owner only**, which is the safe reading rather than
"unrestricted". Three tools have it: `get_today_summary` and
`get_daily_checkin_summary` span categories a caregiver is granted separately —
a caregiver with only `appointments` must not learn a symptom count through a
tool that mentions one in passing — and `add_appointment_question` writes, which
§64 reserves for a suggestion a person approves.

`ToolContext.allowed` has **no default**. A future caregiver-facing assistant has
to say what scope it runs in rather than silently getting the owner's.

**There is no caregiver chat endpoint in PRD 9.** One would need conversations,
memory and preferences scoped to a caregiver account, none of which §80 or §83
asks for. What §63 names — the tool layer using the caregiver's relationship
scope — is built and tested; the surface that would use it is not.

## 11. Audio calling: the boundary, and nothing behind it

§38 is unusually direct: prioritise the abstraction, the permission flow, the
initiation UI and the state model; implement real audio only if it is reliable
now; **do not simulate successful calls**.

So `AudioCallProvider` is real and complete — five methods, which is §39's own
list, with no vendor concept in any signature (no room, no SDP, no ICE server, no
token format). The state vocabulary is real. Authorization is real: a call needs
`communication` on an active relationship, checked exactly as a message is, and
the *pairing* must allow it too.

And the only implementation is `UnconfiguredCallProvider`, every method of which
raises. The route answers `503 calling_not_configured`, `callingAvailable` is
false in the caregiver home, and the app shows a sentence instead of a Call
button. **No call has ever been placed**, there is no table for calls because
nothing has happened that would need recording, and this is partial
implementation documented as such.

## 12. Audit trail

`caregiver_audit_events`: profile, actor, actor kind, event type, target,
minimal metadata, `created_at`. No `updated_at` and no delete path — an audit row
that can be edited is not an audit row.

**There is no event for reading anything.** §49 says not to notify the user every
time a caregiver views a permitted category and §50 not to build a feed of read
operations. A care app that records every glance is the surveillance experience
§2 rules out, and a test asserts no event type contains `view`, `read`, `opened`
or `accessed`.

**Nothing medical reaches `meta`.** §51 asks for minimal metadata and §69 forbids
health content in logs, so every payload is built by a helper in `audit.py` from
a fixed set of keys — a permission key, an action type, a count. A medication
name cannot get in because no function there accepts one.

There is no read API for these rows in PRD 9, deliberately: §50 asks for backend
auditability, not a feed. `psql` is the reader.

## 13. Caregiver Mode in the app

The same app, not a second one (§3). `app/care-mode/` is a stack inside Nura, and
an account that both uses Nura for itself and helps somebody else has both.

`modeStore` holds **a choice, not a credential**: a profile id the account has
already been shown in `/caregiver/profiles`. Setting it grants nothing; every
request still resolves the relationship server-side. `useCareMode` validates the
stored choice against what the server currently lists and falls back to self
mode if the relationship has gone, so a revoked caregiver does not come back to a
screen full of 404s.

**Switching clears before it changes** (§58).
`clearProfileScopedQueries` calls `removeQueries`, not `invalidateQueries`: an
invalidated query keeps serving its old value while it refetches, which is
exactly the "briefly display the prior profile's data" §58 forbids. Removing
means the next render is a loading state, which is the honest thing for a screen
that does not yet know anything about this person.

`permissions.ts` has §62's helpers (`canView`, `canUse`, `homeSections`). They
decide what to *draw*, never what is allowed: a bug there can hide a section the
caregiver may see, and cannot reveal one they may not.

## 14. Offline

| | behaviour | PRD 9 |
|---|---|---|
| caregiver data | read from cache, may be stale | §71 |
| message drafts | persisted per thread to AsyncStorage | §71, §72 |
| suggestion drafts | persisted, **never applied locally** | §73 |
| a sent message | `pending` until the server confirms | §72 |
| permissions | never final until the server confirms | §71 |

**There is no send queue.** §72 asks for `pending` until confirmation, not for a
background retry, and a message that went out an hour later without the sender
knowing is worse than one they resend themselves. The banner says what is true:
saved on this phone, not sent.

A retry keeps its `client_message_id`, so a send that timed out *after* the
server stored it comes back as the message already there (§74). Same for a
suggestion's `client_suggestion_id`.

## 15. What is not enforced

Said plainly, in the manner of `assistant-safety.md`:

- **Nothing stops a caregiver reading a screenshot over somebody's shoulder.**
  Permissions bound what the API returns, not what a person does with a phone.
- **Nothing verifies that a caregiver is who the invitation meant.** The token
  authorizes; the contact is a note. §8 of this document explains the trade.
- **Nothing detects a caregiver acting against somebody's interests.** A
  caregiver with `medications` can propose pausing a reminder every day, and the
  only defence is that the primary user has to approve each one and can revoke
  at any moment. A behavioural heuristic that flagged "too many suggestions"
  would be a judgement about a family that Nura is not in a position to make.
- **Nothing reaches an emergency contact, still.** PRD 10 walks the chain and
  records what it tried; what it can actually do is create an in-app alert for
  a caregiver. There is no push provider, no SMS provider and no calling
  provider, so every contact in the chain gets a row saying the channel is not
  set up. This is the most important entry on this list, because it is the one
  somebody might assume otherwise about — and PRD 10 changed *how* it is false
  without making it true.
- **No notification is delivered.** Every preference in §48 is recorded and
  nothing is sent — there is no push for a family message, a care request or a
  safety alert. An approval request stays visible in-app regardless, which is
  what §48 actually requires, and a safety alert is likewise a record the
  caregiver finds rather than one that finds them.

## 16. Robot independence

Nothing in this feature references BLE, a device token, a heartbeat, a display or
a speaker (§90). A full caregiver flow — invite, accept, read the home, propose,
approve, message, reorder contacts, revoke — runs on an account with no robot
claimed, and a test asserts the device list is empty while doing it. There is
nothing to switch off because nothing in this code path knows a robot exists.

The future surfaces §91 and §92 describe consume the same backend: a robot
displaying a family message reads `family_messages`, and a robot placing a call
goes through `AudioCallProvider`. Neither needs a new table.

---

## 17. What PRD 10 added on top of this

Three things, all of which reuse this feature rather than extending it:

- **`safety_alerts` became real.** An active relationship with that category
  gets in-app alert records and a safety section on the caregiver home. The
  permission is re-checked at read time, not inherited from when the alert was
  created, so a withdrawn permission hides last night's alerts without deleting
  them.
- **The contact chain is consumed, in this feature's order.** The snapshot is
  frozen when escalation starts, so reordering mid-emergency does not change
  who is being reached.
- **One caregiver write was opened.** `acknowledge_safety_alert` — "I'm
  checking on them" — is a single timestamp, the only exception to §64's "a
  caregiver's changes go through a suggestion a person approves". It resolves
  nothing and reaches nobody, which is why it is allowed to be the exception.

The build is in [safety-monitoring.md](safety-monitoring.md).

## 18. What PRD 11 added on top of this

Two things, and the second is an absence worth naming.

**A family message can become a card on the robot's screen** (PRD 11, section
24), and it needs four things to be true at once: an authorized stored message
exists, the `communication` permission is **still** granted, the robot's
message display is switched on, and the display capability supports it.

The permission is re-checked when the card is built, not remembered from when
the message was sent — PRD 10 section 86's lesson, applied to §12's
permissions. A caregiver whose `communication` permission was withdrawn this
morning does not appear on the shelf this afternoon, and a card already waiting
is withdrawn. The message itself is never touched: PRD 11 section 101 forbids
invalidating it, and it stays readable in the app exactly as §30 describes.

Reading it aloud is a separate preference that defaults off and has never been
possible, because no robot has reported a speaker.

**A caregiver controls nothing about the robot** (PRD 11, section 70) — not
brightness, not volume, not privacy mode, not the face, not pairing, not the
emergency display. This is enforced the way §9's rule is enforced everywhere
else: the robot's endpoints resolve a device through the signed-in account's own
claim, so a caregiver is answered 404 rather than being shown a disabled
control. No caregiver scope is resolved anywhere in that part of the API, which
is the absence a reviewer can check.

See [the robot companion experience](robot-companion-experience.md).

## See also

- [`system-overview.md`](system-overview.md) — where this sits in the whole
- [`nura-assistant.md`](nura-assistant.md) — the tool layer §63 constrains
- [`assistant-safety.md`](assistant-safety.md) — the "what is not enforced"
  pattern §15 above follows
- [`health-data.md`](health-data.md) — what a caregiver is and is not shown
- [`safety-monitoring.md`](safety-monitoring.md) — what PRD 10 built on top
  of this
- [`robot-companion-experience.md`](robot-companion-experience.md) — where a
  family message goes when there is a robot, and why a caregiver controls none
  of it
- [`../decisions/0012-caregiver-access-and-approval.md`](../decisions/0012-caregiver-access-and-approval.md)
