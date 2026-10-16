# 0012 — Caregiver access, approval and the limits of helping

**Status:** Accepted · PRD 9

## Context

PRD 9 lets somebody else see part of a person's health record. Every PRD before
it answered "can this account reach its own data?", and the answer was always the
same single join. This one asks a harder question with an answer per category,
per person, per moment — and gets it wrong in the direction that matters if the
design is merely *mostly* right.

Six decisions shaped it.

## Decision 1 — a caregiver is a second authorization path, not a third role

`account_profile_roles` stays `self` and `setup_helper`. Caregivers live in
`caregiver_relationships`, reached by a different dependency.

The alternative — a `caregiver` row in the existing table — was tempting: one
join, every route works, nothing to build. That is exactly why it is wrong.
`deps.get_owned_profile` is what every profile-scoped route from PRD 0–8
authorizes through, so inserting caregivers into that table would have granted
the complete health record, every symptom photo, every doctor report and the
assistant's own conversations **without changing a single route** — no diff to
review, no test to fail, nothing to notice.

The cost is a second surface: new routes, assembled narrower, which is more code
and more to keep right. The benefit is that an authorization mistake made in PRD
9 cannot widen PRD 0–8, and that the narrower reads §67 asks for are the only
reads a caregiver has.

The test that holds it: a caregiver with every category granted gets 404 from
eight PRD 0–8 endpoints.

## Decision 2 — a role grants nothing, and the authorization code does not read it

`role` is a label. No function in `permissions.py`, `deps.py` or any route reads
it to decide anything.

§10 says roles are descriptive and §54 that changing one must not expand access.
Both could have been satisfied by a careful review of every place `role` is read.
This satisfies them by there being no such place, which is a property somebody
can check in a minute rather than a habit they have to maintain.

What this gives up is role-based convenience: there is no "primary caregiver sees
everything" shortcut, so inviting somebody to see everything means ticking eight
boxes. That is the trade §66 asks for — no broad default permission — and the
invite screen is where the cost lands.

## Decision 3 — the invitation is the relationship, and Nura does not send it

A `pending` relationship row carries the token hash, the expiry and the
consumed-at. §79 allows this, and it removes a class of bug: there is no second
table to keep in step, accepting is a status change, and "accept twice" is
idempotent because the token is already spent.

The harder half: **this backend cannot deliver an invitation.** There is no mail
sender, no SMS gateway and no push infrastructure. The options were to build one,
to fake one, or to say so.

Building one is out of scope and would be the only outbound integration in the
system. Faking one — a `send_invitation_email` that logs a line and returns
success — is the single worst option available, because the primary user would
believe their daughter had been contacted.

So the token comes back to the inviter, once, with `delivery:
"share_manually"` in the response body and a sentence on the screen. This is the
same handoff PRD 2 uses for a provisioning token.

The consequence is accepted rather than hidden: **the link is the credential**,
and anybody holding it can accept. What bounds it is 256 bits of randomness,
SHA-256 at rest, a 7-day expiry, single use, and revocation at any moment. The
documentation says this where somebody can read it rather than leaving it to be
discovered.

**Contact matching was considered and rejected.** Requiring the accepting
account's email to match the invitation would lock out somebody who signed up by
phone, or whose Apple relay address differs from the one their mother knows. The
token authorizes; the contact is a note for the inviter.

## Decision 4 — a caregiver proposes, and a person applies

There is no caregiver route that writes to a medication schedule or an
appointment. A caregiver creates a suggestion; the primary user's own account
applies it, through the same service function their own routes call.

§21 asks for important changes not to be applied silently by a caregiver
account. The weaker reading — a caregiver may write, but a flag records that they
did — would have been less code. It fails the moment the primary user disagrees,
because the change has already happened.

Two details carry most of the weight.

**The forbidden changes are absent, not refused.** §85 rules out
`change_medication_dose`, `delete_condition` and `change_diagnosis`. There is no
action type for any of them, the schema's `Literal` refuses the request, and the
CHECK constraint is built from the same tuple the registry is keyed by. A
validation rule can be bypassed by a new caller; a vocabulary with no word for
the thing cannot.

**Approval re-checks the permission against the current relationship.** Not
against what was true when the suggestion was made. A suggestion is not a
capability somebody keeps after their access ends, and this is the step that is
easiest to leave out — so the test revokes the caregiver between proposing and
approving.

## Decision 5 — a missing permission answers 404, and an absent section is absent

404 rather than 403, because the whole codebase answers 404 for "not yours" and a
403 confirms something exists.

§18 goes further than status codes: the absence of a permission must not reveal
anything. So the caregiver home **omits** a section the caregiver was not granted
rather than returning it empty. A caregiver with only `medications` gets no
symptom key at all — not `[]`, not `0` — which is indistinguishable from a person
who has never recorded one.

The cost is a nullable field per section and a client that must distinguish
`null` ("not granted") from `[]` ("granted, nothing there"). The app's parser
keeps that distinction deliberately rather than defaulting `null` to `[]`, and a
test plants a real symptom and asserts the caregiver's view is byte-identical
before and after.

## Decision 6 — build what can be honest, and say what cannot

Three features in PRD 9 are named and not finished, each for a stated reason.

**Audio calling** (§38). The provider interface, the state model and the
authorization are real; the only implementation refuses. §38 forbids simulating a
successful call, and a stub returning `active` would do exactly that. The app
offers no Call control while no provider is configured, and the server answers
`503 calling_not_configured` if one is reached anyway.

**Photo messages** (§33). Optional, and requiring private storage, signed access
and size limits. The private-storage half exists from PRD 6; the upload route and
picker flow do not. `photo` stays in the stored vocabulary so the column and
constraint are already right, and is absent from what a client may send.

**Routines.** §85 lists `add_routine` and §27 says a caregiver may suggest one —
but nothing in PRD 0–9 defines what a routine *is*: no table, no fields, no
screen in §83. Inventing one is not this PRD's call. The `routines` permission
exists, is stored faithfully, unlocks nothing, and the screens say so — which is
exactly the treatment §94 prescribes for `safety_alerts`, applied consistently.

**And nothing contacts anybody.** §47 puts escalation in PRD 10. The chain is
built, ordered and reorderable; no code reads `priority` to decide who to reach.
The screens say so where somebody is entering phone numbers, because that is the
one assumption somebody is most likely to make and most likely to be hurt by.

## Consequences

**Good.** The security boundary is checkable by reading a schema and one
dependency. PRD 0–8 is untouched. Revocation needs no cache invalidation.
Forbidden changes are unrepresentable. A caregiver's view is smaller than the
owner's by construction rather than by filtering.

**Bad.** Two authorization paths to keep right instead of one. Caregiver reads
are assembled by hand, so a new field the owner sees does not appear for a
caregiver until somebody adds it — which is the safe direction, but is work.
Granting broad access means eight toggles. And Nura cannot send an invitation,
which every primary user will notice.

**Unverified.** No notification has ever been delivered, no call has ever been
placed, and no caregiver has ever used this on a phone. The authorization is
tested against a real database with two real accounts; the experience is not.
