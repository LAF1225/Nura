# 0009 — Symptom tracking and structured symptom communication

**Status:** Accepted · PRD 6

## Context

Nura has to let somebody describe what they are experiencing, well enough that
they can show it to a clinician, without ever telling them what it means. That
has to work through a form and through a conversation, on a phone with no signal,
with photographs of somebody's skin involved, and with a boundary that never
slips into diagnosis. Seven decisions shaped how.

## Decision 1 — an episode is a bout, and a recurrence is a new linked episode

`symptom_episodes` holds one bout of one symptom; `symptom_entries` holds
observations about it. A symptom that comes back produces a **new** episode with
`previous_episode_id` pointing at the one it follows and the status `recurring`.

PRD 6 section 38 asks for one documented recurrence model and forbids silently
merging unrelated events. Reopening the original was the other option and it is
worse: one episode would then carry a first-noticed date from months ago and a
gap in the middle, and no summary could describe that honestly. Each bout keeping
its own onset and resolution is what makes "how many episodes have you had?" — a
question clinicians actually ask — answerable.

The status value is what stops the chain from being merely a foreign key. Active
and recurring together are "ongoing", defined once in
`SYMPTOM_ACTIVE_STATUSES` and read by the active list, the summary and the Today
card, so the three can never disagree.

The cost is a `409` on the wrong move: recording a recurrence of an ongoing
episode is refused, because that would create two live episodes of one symptom —
the merge problem from the other direction. The follow-up flow is what an ongoing
symptom wants.

## Decision 2 — one draft, shared by both flows

There is one `SymptomDraft`, one validator, one payload builder and one endpoint.
The manual form and the guided conversation write into the same object and end on
the same review screen; the only difference is the `source` the server records.

PRD 6 section 4 asks for this and warns against separate "chat data" and "form
data" models. Making it structural rather than conventional means there is
nowhere for either flow to put something the other cannot read — no transcript
column, no second table, no field only the conversation sets.

The draft lives in a Zustand store persisted to AsyncStorage rather than in
component state. Three things follow: it survives navigating between the form,
the conversation and the review screen; it survives the app being closed, which
is what PRD 6 section 59 requires; and every field is genuinely exercised by the
test suite, because a store update re-renders reliably under React 19 where a
local `useState` update from a fired event does not.

## Decision 3 — the conversation is deterministic, and the review screen is what makes that safe

Rule-based extraction, rule-based next-question selection, no model (PRD 6,
section 27). The engine is a pure function from `(state, draft, message)` to
`(state, draft)`.

The cost is real: somebody can phrase something in a way the vocabulary misses.
Two things make it acceptable, and both are load-bearing rather than
reassurance.

An answer that matches nothing is **kept verbatim** for whatever question was
asked. Nothing is dropped for not being in a list, so the worst case is a field
that reads exactly as the person typed it (PRD 6, section 75).

And everything is shown on a review screen before it is saved, with every field
editable (sections 30 and 76). Whatever the rules got wrong, the person sees it
and fixes it. Without that screen a rule-based extractor would not be shippable;
with it, the vocabulary makes the conversation shorter when it works and harmless
when it does not.

Non-repetition — PRD 6 section 28's hard acceptance criterion — then falls out of
one line in `nextField`: a field with a value is never a candidate. It is not a
special case, and `symptomConversation.test.ts` asserts it against section 28's
own example sentence.

## Decision 4 — uncertainty and denial are stored, and they suppress escalation

Three list fields keep what somebody hedged, denied or qualified:
`negated_items`, `uncertain_items`, `context_dependent_items`.

PRD 6 section 24 asks not to flatten these into false certainty. Storing them is
half of it; the other half is that the safety rules subtract them:

```python
confirmed = stated - uncertain - negated
```

So "I'm not sure if I'm short of breath" never fires a breathing rule, and "no
chest pain" never fires a chest-pain one. That is PRD 6 section 46 — *do not
escalate from uncertain parsing alone* — as an equality test rather than a
guideline, and it is why a red flag matches canonical confirmed phrases rather
than words found in prose.

Two extraction bugs made this concrete. Negation cues had to move to word-boundary
matching, because "cannot breathe" contains the letters of "not" and was being
read as a denial of breathing. And the conditional cues had to narrow, because
"only when" was fine but "when I" swallowed "it is worse when I walk" — an
aggravating factor, not a qualification.

## Decision 5 — the red-flag rules ship built, tested and switched off

PRD 6 section 44 permits red-flag safety-netting only with a reviewed rule set,
and says that without one, ship the generic worsening guidance and leave the
urgent architecture ready but disabled. Nothing in Nura has been reviewed by a
clinician, so `symptom_red_flag_rules_enabled` defaults to False and
`red_flag_message()` returns None whatever matched.

The rules are still written down — the five categories section 44 lists — and
still evaluated by the tests, so a later clinical review has something real to
review and enabling them is a setting change rather than a code change. A test
asserts both halves: that the layer fires correctly when a deployment turns it on,
and that it is off by default.

What a running deployment says about a symptom is therefore exactly one sentence,
shown when the user recorded a change they chose: *consider contacting a
healthcare professional*. Every input to that is something they did — the
worsening they selected, a severity rise of two or more across entries they each
saved, an associated symptom they added. There is no branch on an absolute
severity anywhere, because PRD 6 section 78 rules out treating 10/10 as a
confirmed emergency.

The wording lives in one module, apart from all symptom logic (section 45), which
is what lets a test read every sentence Nura can say and fail on a named
condition, a likelihood, an attribution of cause or an instruction about
medication.

## Decision 6 — photos are authenticated downloads, and nothing looks at them

PRD 6 section 33 allows an authenticated route or a signed expiring URL. This
uses the route.

A signed URL is a bearer token in a query string. It lands in logs, in
screenshots and in share sheets, and it stays valid until it expires no matter
who is holding it. The route re-checks the whole chain — account owns the profile,
episode belongs to the profile, entry belongs to the episode, photo belongs to
the entry — for every byte it serves, which is a stronger guarantee for a small
amount of extra work.

`storage_key` therefore never appears in a response. Knowing a photo's id, or
guessing a key, gets nobody anything.

The declared content type is not believed: an upload is sniffed from its header
and a mismatch refused. The app compresses to a 1600px JPEG and strips EXIF, so
location and camera metadata do not travel with a photograph of somebody's skin.
Deletion removes the object before the row, and deleting an entry or episode
purges its objects explicitly — a database cascade cannot reach into storage.

And the boundary that matters most, stated plainly because PRD 6 section 32 does:
**nothing in Nura analyses a symptom photo.** No classification, no wound
assessment, no rash identification, no medical computer vision. The app says so
on screen every time a photo can be attached, not only in a privacy page.

## Decision 7 — symptoms are counted in Health but excluded from completeness

Symptoms are listed in the Health tab, between allergies and doctors, where PRD 6
section 6 puts them. They are reported as two figures — active, and updated this
week — kept separate from the condition counts, because a symptom is what
somebody is experiencing and a condition is what they have been told they have,
and a count that blends the two is how a summary starts implying a diagnosis
(section 48).

They are deliberately **not** one of the seven completeness sections. The health
profile's percentage is about a record somebody fills in; having no symptoms
logged is a good state, and a figure that rose because somebody felt unwell would
be grotesque. `total_sections` stays 7, and a test asserts that logging a symptom
does not move the percentage.

The same reasoning drives the Today card: it is on by default but draws nothing
at all until somebody has used the feature. Most people, most of the time, have
nothing to report, and a permanent "No active symptoms logged" panel is a
standing reminder of a feature they are not using.

## Consequences

- The recurrence model, the status invariants and the onset precision rules are
  all database constraints as well as service rules, so a bug in a service cannot
  produce a row that contradicts them.
- Idempotency is a unique constraint on a client-generated id rather than a
  server-side heuristic, so an offline retry converges on one record by
  construction — for entries, for episodes and for photo uploads alike.
- The conversation engine has no dependency on a network, a model or a renderer,
  so PRD 6's hardest requirement is asserted by unit tests rather than inferred
  from a screenshot.
- Swapping local photo storage for a private bucket is one class and one line, and
  changes no route, service or test.
- What PRD 6 forbids — diagnosis, likelihood, autonomous action, photo analysis,
  caregiver access — is not expressible anywhere in the model or the copy, rather
  than being omitted from the UI and reachable through the API.
- PRD 7's Prepare for Appointment can read everything it needs from these
  endpoints without a schema change.
