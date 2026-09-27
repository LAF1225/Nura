# The symptom system

PRD 6. How Nura records what somebody is experiencing, without ever telling them
what it means.

```text
Conditions = what a clinician has told you you have
Symptoms   = what you are experiencing, over time
```

Those are two different things and they live in two different places. A symptom
is never promoted to a condition, and a condition is never inferred from a
symptom (PRD 6, section 6).

---

## Episode and entry

The distinction the whole feature rests on (PRD 6, section 8):

```text
symptom_episodes         one bout of one symptom -- "this headache"
    |
    +-- symptom_entries      one observation about it, at one moment
            |
            +-- symptom_photos   what it looked like, stored privately
```

An **episode** is the ongoing problem. It has a name in the user's own words, a
site, an onset, and a status. An **entry** is one observation: how bad it is now,
which way it is going, what else is happening. The first entry is the
description; every later one is a follow-up.

That structure is what makes longitudinal tracking possible, and it is why a
follow-up needs almost nothing:

```text
25 Sep  3/10   started, throbbing, behind both eyes
26 Sep  4/10   about the same
27 Sep  6/10   worsening, nausea, no vomiting
```

Three entries, one episode. The description was written once.

### An episode is a bout, not a name

A headache in March and a headache in October are **two episodes**. The second
points back at the first through `previous_episode_id` and carries the status
`recurring`.

PRD 6 section 38 asks for one documented recurrence model and forbids silently
merging unrelated events. This is the second of the two options it offers, with
the status value giving it a name. The alternative -- reopening the original --
would produce one episode with a first-noticed date from months ago and a gap in
the middle that no summary could describe honestly.

Reopening is refused with `409 symptom_episode_not_resolved` while the episode is
still ongoing. An ongoing symptom wants a follow-up; creating a second live
episode of the same symptom is the merge problem arrived at from the other
direction.

### Statuses

```text
active       going on now
recurring    going on now, and this has happened before
resolved     the user said it has ended
historical   something from the past
```

`active` and `recurring` together are what "ongoing" means, everywhere:
`SYMPTOM_ACTIVE_STATUSES` is the single definition the active list, the summary
and the Today card all read.

**Nothing infers `resolved`.** An episode nobody has updated for six weeks is
still active, because the alternative is Nura deciding somebody got better. A
resolution is an explicit action, and it records *when* -- a database CHECK makes
`status = 'resolved'` imply a `resolved_at`, so the two can never disagree.

Resolving keeps everything: no entry is deleted, no photo is removed, and the
episode stays fetchable forever (PRD 6, section 37). Deleting is offered
separately, for a symptom logged by mistake, and the confirmation says plainly
what goes and points at the other option.

---

## The structured fields

The fields somebody is asked for when describing a symptom to a clinician
(PRD 6, section 12):

| Field | Example |
| --- | --- |
| main symptom | "headache", "knee pain", "feeling wobbly" |
| site | "behind both eyes", "left knee" |
| onset | "suddenly, three days ago" |
| character | "throbbing", "sharp", "burning" |
| radiation | "spreads to my back", "stays in one place" |
| associated symptoms | "nausea", "light sensitivity" |
| timing | "comes and goes", "worse at night" |
| exacerbating factors | "bright light", "walking" |
| relieving factors | "rest", "lying down" |
| severity | 0-10 |
| change state | improving / same / worsening / unsure |

**Every one of them is optional.** Only an episode's `name` is required, and a
follow-up needs not even that. PRD 6 sections 11 and 91 require a useful record
to be savable without a severity, a site or a character, and a model that
demanded answers would either lose the description or invent it.

**Not every symptom goes through every field.** Radiation means nothing for
nausea, and a fever is not *somewhere*. The guided flow skips what does not
apply; the manual form offers it and labels it optional.

### Severity is a number, never a word

0 to 10, anchored as "0 = no symptom" and "10 = the worst you can imagine". The
middle is deliberately unlabelled: calling 5 "moderate" would turn the user's own
number into Nura's judgement of how bad things are (PRD 6, section 22).

A number is never required. Where one is the wrong shape of answer, severity
stays null and the note carries the description.

### Onset keeps its precision

Three columns, at most one filled: an exact instant, a day, or a year. "I think
it started in 2024" stays a year rather than becoming the 1st of January -- the
same rule PRD 4 set for diagnosis dates.

Alongside them, `first_noticed_text` keeps the user's own wording. "It started
suddenly" is *how*, not *when*, so somebody who says only that is still asked
roughly when, and both answers are kept (PRD 6, section 74).

### Uncertainty and denial are preserved

Three list fields exist so a description cannot claim more certainty than the
person expressed (PRD 6, section 24):

```text
negated_items             "no nausea"
uncertain_items           "I might have felt dizzy"
context_dependent_items   "only when I stand up"
```

A symptom word inside a denial never becomes a symptom the person has. This is
not a nicety: it is what stops "no chest pain" from reading as chest pain, in a
summary or in a safety rule.

The six list fields are `jsonb` defaulting to `[]`, never null. They are only
ever read and written whole, which is why they are not a join table (PRD 6,
section 9). Nothing mutates one in place -- SQLAlchemy does not track mutation
inside a JSONB value, so every write assigns a fresh list.

---

## Two flows, one record

PRD 6 section 4 requires the manual form and the guided conversation to produce
the same structured record. That is a property of the code rather than a promise:

```text
manual form  ─┐
              ├─→  SymptomDraft  →  entryPayload()  →  POST /symptoms
Talk to Nura ─┘
```

One draft type, one validator, one payload builder, one endpoint. The only
difference between the two is the `source` the server records -- `manual_app` or
`guided_app` -- which is an observation about how the data arrived, not a
different kind of data. There is deliberately no second table, no transcript
column and nowhere for one flow to stash something the other cannot read.

### The draft

The draft lives on the phone, in a Zustand store persisted to AsyncStorage
(PRD 6, sections 29 and 59). Nothing incomplete is ever written to the backend.

Putting it in a store rather than in component state is what lets the form, the
conversation and the review screen all edit one thing -- and what lets somebody
who is interrupted come back to it. It also has a testing consequence worth
recording: a store update re-renders reliably under React 19, so **typing into
the symptom form is genuinely exercised by the test suite**, unlike PRD 4's and
PRD 5's forms.

`clientEntryId` is generated when the draft starts, before anything is sent. See
[Idempotency](#idempotency).

### The guided conversation

Deterministic, and **not** a general-purpose model (PRD 6, section 27).

```text
conversation/vocabulary.ts   the words it recognises
conversation/extract.ts      one message -> structured fields
conversation/questions.ts    which question to ask next, and how to word it
conversation/engine.ts       the turn loop, as pure functions
```

The engine is `(state, draft, message) -> (state, draft)`. No effects, no
network, no component state -- which is what makes the interesting behaviour
testable without rendering anything.

**Non-repetition** (PRD 6, section 28, a hard acceptance criterion) falls out of
one rule in `nextField`: a field that has a value is never a candidate. So this
first message:

> I have a sharp pain in my left knee that started yesterday and is 6/10

fills the symptom, the site, the character, the onset and the severity, and the
conversation asks none of them. `symptomConversation.test.ts` asserts exactly
that.

What the vocabulary misses is not lost. An answer that matches no pattern is
**kept verbatim** for whatever question was asked, so "it feels like a tight
band" becomes the character whether or not that phrase is in a list (PRD 6,
section 75). And everything is shown on a review screen before it is saved. The
vocabulary makes the conversation shorter when it works and harmless when it does
not.

Two extraction rules are worth knowing because they were bugs first:

- Negation and hedging cues are matched **on word boundaries**. "cannot breathe"
  contains the letters of "not", and a substring test read it as a denial of
  breathing.
- The conditional cues are deliberately narrow -- "only when", "unless" -- because
  a broader list swallowed "it is worse when I walk", which is an aggravating
  factor rather than a qualification.

### Review before save

Both flows end on the same screen, showing the draft in plain words with every
field editable (PRD 6, sections 30 and 76). This is the reason the guided
conversation is safe to ship at all: whatever the rules made of what somebody
typed, the person sees it and can change it before a single thing is stored.

Rows with nothing in them are not drawn, so a sparse description reads as a short
summary rather than a form full of blanks. The denied and uncertain rows *are*
drawn -- dropping them would be the false certainty section 24 forbids.

---

## Safety-netting

The one part of the system that says anything back. It lives in
`app/services/symptoms/safety.py` and `src/features/symptoms/safetyMessages.ts`,
apart from all symptom logic, so somebody clinical or legal can read and change
every sentence without touching a screen (PRD 6, section 45).

### Nura reports recorded change; it does not diagnose deterioration

Every input is something the user did (PRD 6, section 41):

| Reason | What it means |
| --- | --- |
| `reported_worsening` | they chose "worsening" on the latest entry |
| `severity_increase` | their own number rose by 2 or more between two saved entries |
| `new_associated_symptom` | they added something that was not in the previous entry |

Two points, not one, because a self-reported scale moves by one on a bad
afternoon and calling that worsening would make the signal meaningless.

**Severity alone is never enough**, whatever the number. PRD 6 section 78 rules
out treating 10/10 as a confirmed emergency, and `assess()` has no branch on an
absolute severity anywhere. A test asserts it.

### The red-flag rules are built, tested and switched off

PRD 6 section 44 allows red-flag safety-netting only with a reviewed rule set,
and says that without one, ship the generic guidance and leave the urgent
architecture ready but disabled. **Nothing here has been reviewed by a
clinician**, so:

```text
symptom_red_flag_rules_enabled = False
```

With it off, `red_flag_message()` returns None whatever matched, and the only
thing a running deployment ever says about a symptom is:

> You have recorded this as worsening. If it keeps getting worse, becomes severe,
> or is affecting what you can normally do, consider contacting a healthcare
> professional.

The rules themselves are written down -- the five categories section 44 lists --
and are evaluated by the tests, so a later review has something real to review
and turning them on is a setting change rather than a code change.

### Uncertainty and denial suppress escalation

A rule matches on **canonical phrases the user explicitly confirmed**, not on
words found in prose. A phrase in `uncertain_items` or `negated_items` does not
fire, which is PRD 6 section 46 as an equality test:

```python
confirmed = stated - uncertain - negated
```

"I'm not sure if I'm short of breath" is not a report of breathlessness, and
treating it as one would be exactly the false certainty section 24 forbids.

### Confirming an ambiguous statement

When the conversation notices a concerning phrase it is not sure about, it asks:

> Just to confirm: are you saying you have severe difficulty breathing right now?

A "yes" records the canonical phrase, so a server rule can see it. A "no" records
it as *denied* rather than dropping it -- "no, I can breathe fine" is
information, and keeping it stops the same phrase being queried again. Anything
else leaves it in `uncertain_items`, which is what it is.

The canonical vocabulary is shared between `RED_FLAG_TERMS` on the backend and
the app's copy of it, with a test on each side asserting they still agree. A term
the app confirms that the server does not know would be a confirmation no rule
can act on.

### Nothing is autonomous, and nothing is a diagnosis

No emergency service is called, no caregiver is messaged, no medication is
changed, and no monitoring is activated (PRD 6, section 43). A notice is a card
above the Save button, never a dialog in front of it: somebody describing a
worsening symptom must still be able to finish describing it (section 77).

A test reads every sentence in the safety module and fails on a named condition,
a likelihood, an attribution of cause, or an instruction about medication
(section 81).

---

## Photos

Stored privately. **Nothing looks at them** (PRD 6, section 32): no
classification, no wound assessment, no rash identification, no medical computer
vision of any kind. A photo is something a person keeps for themselves and shows
a clinician.

### Authenticated downloads, not signed URLs

PRD 6 section 33 allows either; this uses the first.

```http
GET /api/v1/profiles/{pid}/symptoms/{eid}/entries/{entry_id}/photos/{photo_id}/content
Authorization: Bearer <the user's token>
Cache-Control: private, no-store
```

A signed URL is a bearer token in a query string: it lands in logs, in
screenshots and in share sheets, and it stays valid until it expires no matter
who ends up holding it. This route re-checks the whole chain -- account owns the
profile, episode belongs to the profile, entry belongs to the episode, photo
belongs to the entry -- for every byte it serves (section 63).

`storage_key` never leaves the backend. It is not in any response body, so
knowing a photo's id, or guessing a key, gets nobody anything.

### Storage

```python
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
```

`LocalObjectStore` writes under `private_media_root` (default
`backend/.private-media`, gitignored), which nothing serves statically. Keys are
built from server-generated ids and validated against a narrow pattern, and the
resolved path is confirmed to be inside the root -- a store that accepts a
caller's path is one `../` away from serving the rest of the disk.

Swapping in S3 or a Supabase bucket later means one new class and one line in
`get_object_store`. No route, service or test changes.

### On the way in and out

The declared content type is **not believed**. An upload is sniffed from its
first bytes (JPEG, PNG, HEIC/HEIF) and a mismatch is refused. The app compresses
to a 1600px JPEG before uploading and strips EXIF, so location and camera
metadata do not travel with a photo of somebody's skin.

Deleting removes the object *and* the row, object first: a failure must not leave
a row pointing at bytes nobody can reach. Deleting an entry or an episode purges
its stored objects explicitly, because a database cascade cannot reach into
storage.

---

## Offline

A symptom description is never silently lost (PRD 6, sections 59 and 60).

```text
Save with no signal
    ↓
one pending record on the phone: the episode body (or an episode id),
the entry, and the local photo files
    ↓
sent when a symptom screen is focused, or when the connection returns
    ↓
photos uploaded one at a time after the description lands
```

The record is keyed by `clientEntryId`, so pressing Save twice replaces rather
than duplicates. A recurrence carries `recurOf` instead of an episode id, so a
symptom that came back while the phone was offline still lands as a *linked* new
episode rather than an unrelated one.

**A photo is never reported as uploaded before the backend says so** (section
60). If the description lands and a photo does not, the pending record is kept
with the now-known episode and entry ids -- so the retry uploads rather than
creating anything a second time -- and the row reads "Pending upload".

A save that the server *refuses* is not retried. That is a rule the user needs to
hear about, not a failure to keep trying.

---

## Idempotency

`client_entry_id`, generated by the app before the first attempt (PRD 6, section
61). It survives a failed request, an app restart and a week offline.

```text
POST .../entries  {client_entry_id: "entry-a4a2…", severity: 7}   → 201 created: true
POST .../entries  {client_entry_id: "entry-a4a2…", severity: 7}   → 200 created: false
```

A replay returns the stored entry **unchanged**. A retry is not an edit, and
letting one overwrite the stored entry would turn a dropped response into a way
of silently rewriting history.

Episode creation is idempotent through its first entry's id: a retry finds the
entry already stored and returns its episode. Photo uploads carry
`client_photo_id` for the same reason. Both are unique per scope in the database,
so the guarantee is a constraint rather than a convention.

---

## Authorization

The chain PRD 6 section 53 asks for, complete at every depth:

```text
signed-in account
    → owns the profile         (OwnedProfile)
        → episode belongs to the profile
            → entry belongs to the episode
                → photo belongs to the entry
```

Every lookup includes the parent in the query rather than checking it afterwards.
There is no route that takes an id and works out who it belongs to. Anything that
fails is **404, never 403** -- a 403 would confirm that an id exists, which is how
somebody enumerates other people's records.

`TestAuthorization` in `backend/tests/test_symptoms.py` walks all of it,
including the cases within one account: an entry id from another of the same
profile's episodes is not found either.

---

## Today and Health

**Today** carries a symptom block in its own response, so the card costs no extra
request (PRD 3, section 16):

```json
{
  "symptoms": {
    "active_count": 2,
    "worsening_count": 1,
    "most_recent": { "episode_id": "…", "name": "Headache", "severity": 5,
                     "change_state": "worsening", "updated_at": "…" },
    "has_episodes": true
  }
}
```

The card is on by default and **draws nothing at all** until the feature has been
used. Most people, most of the time, have no symptoms to report, and a permanent
"No active symptoms logged" panel would be a standing reminder of a feature they
are not using. Once somebody has used it, the card is there -- including PRD 6
section 39's empty state -- because from then on it is a way back in.

A symptom the user recorded as worsening reaches **Important Today** as an
ordinary row at `normal` priority. PRD 6 section 40 forbids labelling a symptom
urgent without a reviewed safety rule, and those are switched off.

**Health** lists Symptoms as its own row, between allergies and doctors, where
PRD 6 section 6 puts it. Two figures, kept apart from the condition counts
(section 48):

```text
Symptoms       2 active
               2 updated this week
```

Symptoms are deliberately **not** one of the completeness sections. Having none
logged is a good state, and a percentage that rose because somebody felt unwell
would be grotesque. `total_sections` stays 7.

---

## Privacy

PRD 6 section 62, and what it means in practice:

- **Nothing is logged but an action.** `symptom.entry.create success`,
  `symptom.photo.upload success`. No symptom name, no free text, no associated
  symptom, no photo path, no safety response -- on either side.
- **No analytics.** There is no analytics in Nura at all yet; when there is, the
  events in section 64 are generic and carry no medical values.
- **Nothing is sent to an LLM.** The conversation is rule-based and runs on the
  phone.
- **Nothing travels over BLE.** Symptom data is not part of provisioning and the
  robot has no access to it.
- **No caregiver access** (section 83). Caregiver permissions come later and must
  be category-specific.

The offline queue does hold symptom text on the device, which is unavoidable for
a draft that must survive a lost connection. It is in the app's private data
directory, and nothing in that module ever logs a value.

---

## Robot independence

Every required PRD 6 workflow runs with no robot: logging manually, the guided
conversation, follow-ups, resolution, recurrence, photos, history, Today, and the
offline path (PRD 6, sections 5, 84 and 93).

There is no BLE, no microphone, no speaker, no display, no camera and no
heartbeat anywhere in this feature. **There is no speech recognition of any kind.**
PRD 6's conversational flow is in-app text, which is what section 5 specifies.

`robot_voice_future` exists in `SYMPTOM_SOURCES` so a later PRD adds a writer
rather than re-deciding the vocabulary. Nothing writes it, and the API refuses a
client that claims it -- `SYMPTOM_SOURCES_ALLOWED` is the two app flows. When
robot speech eventually arrives it will call the same service layer and produce
the same entries; there are no robot-specific symptom tables and there will not
be (section 58).

---

## What PRD 7 will need

PRD 6 section 80 lists what Prepare for Appointment wants, and all of it is
already structured and readable:

| PRD 7 needs | Where it is |
| --- | --- |
| active symptoms | `GET /symptoms?active=true` |
| recent entries | `GET /symptoms/{id}/entries`, newest first |
| severity change | two entries' `severity`, or `safety.reasons` |
| worsening state | `safety.worsening` and the latest `change_state` |
| onset | the episode's three precision columns plus its wording |
| notes | `free_text_note` per entry |
| photo metadata | `photos` on each entry, without a storage key |

---

## Code map

```text
backend/app/models/symptom.py                  three tables
backend/app/schemas/symptom.py                 request/response models, drift guards
backend/app/api/v1/symptoms.py                 the routes
backend/app/services/symptoms/
    episodes.py                                bouts, resolution, recurrence
    entries.py                                 observations, idempotency
    photos.py                                  sniffing, storage, deletion
    safety.py                                  the reviewed copy and the rules
    summary.py                                 counts for Today and Health
backend/app/services/storage.py                private object storage
backend/tests/test_symptoms.py                 72 tests

mobile/src/features/symptoms/
    types.ts                                   the model and the shared draft
    copy.ts                                    all user-facing wording
    safetyMessages.ts                          every sentence Nura says back
    draft.ts                                   validation and payloads
    draftStore.ts                              the draft, persisted
    pendingEntries.ts                           the offline queue
    photos.ts                                  picking and compressing
    api.ts / hooks.ts                          requests and server state
    conversation/                              vocabulary, extract, questions, engine
    components/                                cards, controls, bubbles, summary
mobile/app/symptoms/                           overview, log, talk, review,
                                               history, [id], [id]/update
```

---

## Related

- [The health record](health-data.md) — conditions, medications and the rest of
  the record a symptom is deliberately kept apart from.
- [The medication system](medication-system.md) — the other feature area that
  joins Today, and the source of several patterns reused here.
- [ADR 0009](../decisions/0009-symptom-tracking.md) — the decisions behind this
  design.
