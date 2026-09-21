# 0007 — The health record foundation

**Status:** Accepted · PRD 4

## Context

Nura has to hold conditions, medications, allergies, clinicians, procedures and
notes for a person who may be filling them in over weeks, may not remember
when things happened, and may be doing it on someone else's behalf. Five
decisions shaped how.

## Decision 1 — records belong to a profile, not an account

Every health table has a `profile_id` and nothing else that identifies a
person. The account that typed a record in is not recorded on it.

In assisted setup the account holder is not the person the record is about. If
medical data hung off the account, every later feature — caregiver access,
reports, a second person on one account — would have to unpick it, and the
first migration would have to guess whose data was whose. Attaching to the
profile costs nothing now and is the only version that stays true.

Authorization follows from it: an account reaches a record only through its own
link to that profile, and anything else is `404`. That phrasing — *reaches*,
not *owns* — is what lets caregiver permissions become another kind of link
later rather than a rewrite.

## Decision 2 — dates keep the precision the user has

Each approximate date is **two columns**, an exact date and a year, with a
database constraint that at most one is set. Both null is valid.

The alternative — storing "2015" as `2015-01-01` — makes the record say
something the person did not, and it is unrecoverable: nothing downstream can
tell a real January date from a year that was padded. A report that says
"diagnosed 1 January 2015" to a clinician is worse than one that says "2015".

The cost is two columns and a constraint per date, and a third UI-only value in
the form so the question can be asked properly. Worth it.

## Decision 3 — provenance is set by the server

`source` (`user` | `caregiver` | `clinician_import` | `system_import`) is on
the three record types that will one day be imported. **The API ignores any
value a client sends** and stores `user`.

A field that says where data came from is worthless if the client can write it.
Once caregiver entry and clinical imports exist they will set it on the paths
that genuinely have that provenance — until then, everything in the database
honestly says a person typed it.

## Decision 4 — one screen in the app, six routers on the server

The app describes each section once — fields, wording, how to summarise a
record — and a single list screen and a single form screen read that
description. The backend writes its four routes out per resource.

These look inconsistent and are not. On the client the risk is *drift*: six
hand-written CRUD screens are six chances for a delete confirmation, an empty
state or a required-field message to diverge, on the part of the app holding
someone's medical history. On the server the risk is *obscurity*: this is the
authorization surface for medical records, and being able to read each
resource's routes in full, without following an abstraction, is worth the
repetition. The shared part on the server is the service layer, where the
authorization rule lives exactly once.

## Decision 5 — completeness is informational, and imperfect

Seven equal-weight sections; a section counts once it has something in it.
There is deliberately no "I have nothing to add" flag, so someone with no
allergies cannot reach 100%.

Adding a flag per section would put state in the data model whose only job is
to make a progress bar happier, and it would need its own UI, its own
migration and its own meaning in reports. The figure is a gentle prompt, not a
score: nothing is blocked by an incomplete profile, there is no warning state,
and the wording says how many sections *have information* rather than how many
are done.

## Consequences

- Caregiver access, reports and imports all attach to what already exists.
- No stored date is more precise than the answer that produced it.
- A record's provenance can be trusted, because only the server writes it.
- Adding a seventh record type is a section spec in the app and a router on the
  server — no new screens.
- A profile that is 71% complete stays 71% complete, and nothing in the product
  treats that as a problem.
