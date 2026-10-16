# ADR 0016 — Privacy, export, deletion and reliability

**Status:** accepted · **Stage:** PRD 13 · **Supersedes nothing**

## Context

PRD 0–12 built a health companion with privacy properties scattered across
twelve stages: owner and caregiver authorization kept separate, private media
behind authenticated routes, offline queues per feature, truthfulness rules
about providers and hardware. All of it worked. None of it was reviewable in
one place, there was no way for a person to see their own privacy state, no way
to take their data with them, and no way to remove it.

PRD 13 is explicitly integration-focused: *"do not rebuild working feature
systems"*, *"prefer shared policies, adapters, audits, a small number of
user-facing privacy screens, and high-value regression tests over
feature-by-feature rewrites."*

So the question this stage answers is not "how should privacy work" — twelve
PRDs already answered that — but "how do we make it visible, portable,
removable, and hard to break by accident".

## Decisions

### 1. Synchronous export and synchronous deletion. No worker, one table.

§20 permits a synchronous export if it is simple and reliable; §48 says not to
add a worker unless one is needed. An archive here is a few dozen kilobytes of
JSON plus whatever media exists, assembled from queries that already run on
every screen; a deletion is one statement plus a file sweep. A worker would add
a queue, a state machine, a poll loop and a new failure mode to jobs that
finish inside a request.

So the schema change is **one table**, `data_exports`, and nothing else in the
database moved. Deletion gets no table at all — and the reason is not only that
it is synchronous: a row recording that somebody asked to be deleted, surviving
after they were, would be the single piece of their data that outlived the
request. That is a strange thing to build into a deletion feature.

`requested` and `generating` stay in the status vocabulary, unused, so a build
that does need a worker needs no migration. Same approach PRD 6 took to future
symptom sources.

### 2. What an export contains is a declared list, not a strip-list.

The obvious implementation serializes every column and removes a few known
secrets. It is also the implementation that leaks the next secret somebody
adds.

`services/privacy/tables.py` instead states, for every table, which columns are
exported and which are excluded **and why** — and a test walks the live
SQLAlchemy metadata asserting that for each table, exported plus excluded is
exactly the column set. A column a later PRD adds is unclassified, and
unclassified fails.

The cost is real: a PRD that adds a column to an exported table cannot ship
until somebody decides which side of the line it falls on. That cost is the
point. It is the same shape as PRD 12's capability map and PRD 11's protocol
vocabulary — a decision that must be made, rather than a default that will
eventually be wrong.

### 3. Deletion reads storage keys before it deletes rows.

68 foreign keys cascade from a profile and **not one can reach a file**.
Symptom photos, report PDFs and export archives live in object storage; the
database knows a key and nothing else.

So the order is fixed and the service owns it: enumerate, read the keys, delete
the rows, *commit*, then delete the files. Keys before rows because afterwards
there is no way to find them; files after the commit because a file removed for
a transaction that then rolled back cannot be undone.

PRD 14 §56 lists "deletion leaves accessible private files" as a release
blocker. This is the decision that stops it, and `test_privacy_deletion.py`
asserts the files are gone rather than asserting the rows are.

### 4. The account survives its last profile. A robot is unlinked, not unclaimed.

Two consequences of §22's "preserve unrelated profiles" taken seriously.

An account with no profile is exactly where a new sign-up is, so there is
nothing broken about that state — and signing somebody out of a session whose
token is valid for another hour is not a deletion's business.

A robot stays claimed by the account and goes back to being set up for nobody:
`owner_profile_id` is nullable precisely for that state. The robot on the shelf
still belongs to whoever bought it, and PRD 2's claim is what says so.

### 5. Confirmation is an exact phrase, and the re-authentication gap is stated in the product.

§21 asks for re-authentication "if already supported". It is not: Nura verifies
Supabase tokens against a JWKS endpoint and never receives a password, so there
is nothing to check one against. §44 anticipates this and asks for strong
explicit confirmation plus a documented limitation.

The phrase is compared **exactly** — no trimming, no case folding — because
every softening makes it easier to arrive at by accident, and accident is what
it exists to prevent. Two required fields with no defaults, so an empty body or
a replayed request cannot delete anything.

And the limitation is said on the screen, not only in a document:

> Nura cannot ask you for your password again: it never receives one. Anyone
> holding this phone while you are signed in can complete this, which is why it
> asks you to type the phrase exactly.

That is the honest description of what the phrase does. Putting it only in an
architecture document would be hiding it where the people affected do not look.

### 6. One security suite that enumerates routes from the application.

Every stage from PRD 9 onwards wrote a denial test against a hand-typed list of
paths. Each was correct. None covered the next stage's routes: PRD 9 walked
eight, and PRD 10 and PRD 12 each added their own because the first could not
know about them.

`test_security_matrix.py` asks the app instead. It walks the router tree,
resolves each route's dependency graph, and classifies routes by which
authorization dependency they reach. The cross-profile and caregiver walks then
request **every owner route** with the wrong caller and require 404. A route
PRD 14 adds is in those loops the day it is written.

One assertion makes the rest mean anything: the walked paths are compared
against the published OpenAPI schema. A path the walk gets wrong does not
exist, so every request against it answers 404, and a suite asserting "the
wrong caller gets 404" passes for routes it never reached. That was true for
nine health-record routes nested two routers deep until the check was added —
which is the clearest argument available for writing it.

### 7. The caregiver-reachable surface is written out and asserted by equality.

Thirteen routes of 218, each with a stated purpose. Equality rather than
containment, so the list cannot rot in either direction: a fourteenth fails the
suite until somebody says what it is for, and a route that stops being
caregiver-reachable fails too.

### 8. Two shared modules, both justified by existing duplication.

§57 says not to create an abstraction unless at least two systems genuinely
reuse it. Two qualified.

**The retry policy** existed five times — medications, symptoms, appointments,
daily life, the check-in — and all five lists were already identical. Moving
them to `features/reliability/retry.ts` changed no behaviour and gave the
policy one place to be read and argued with. The list is of what *is*
retryable, so a new error kind is non-retryable until somebody decides
otherwise: it surfaces rather than spins.

**The local-data inventory** had no owner at all. Seventeen AsyncStorage keys
and seven persisted stores, each declared privately in the feature that wrote
it, and nothing that knew about all of them — which is why sign-out cleared
none of them.

What did *not* qualify: a universal offline framework (§28 rules it out), a
consolidated audit table (§57), and migrating PRD 5's and PRD 7's reminder
schedulers (§57, and PRD 12 already declined for the same reason).

### 9. Both hand-maintained lists get a drift test that reads the source.

This is the decision the stage turned on.

`PROFILE_SCOPED_KEY_PREFIXES` had stopped being maintained, and the damage was
larger than it looked: **twenty-six keys missing or wrong**, from PRD 3, 5, 6,
7, 10 and 12 — the health record, dose history, adherence, symptom entries,
appointment questions, doctor reports, check-ins, safety status, tasks,
routines. Two entries that were present matched nothing, because the real keys
are `['health', 'summary', …]` and a prefix compares element by element.

Adding the keys fixes today. What stops it recurring is that
`cacheIsolation.test.ts` reads every `queryKey` literal out of the feature
modules and requires each to be in the profile-scoped list or in a documented
account-scoped list with a reason — **and asserts the reverse**, that every key
in the list is actually declared somewhere. The reverse direction is not
hypothetical: it is what caught `health-summary`.

`privacyLocalData.test.ts` does the same for storage keys.

A hand-maintained list that nothing checks is a list that is already wrong. The
general form of this decision: when correctness depends on a human remembering
to update a list, the list needs a test that reads the thing it is supposed to
mirror.

### 10. PRD 11's robot keys are account-scoped, said out loud.

A device is claimed by an account, not owned by a profile, and no caregiver
route reaches one — so switching which person is on screen does not change
which robot is theirs. They belong in the documented account-scoped list, with
that reason, rather than being quietly added to the profile clear "to be safe".
Sign-out clears them along with everything else.

### 11. Documents and config, not columns.

§11 asks for data classification and explicitly says not to add classification
columns to every table unless actually needed. They are not needed: the
categories are one tuple read by the document, the export manifest, the
deletion inventory and the privacy hub, so there is one answer rather than four
that drift.

### 12. The hub reads the system and owns nothing.

Every control on Privacy & Security links to the screen that already owns the
setting, and every claim is a sentence the server sent. §4 asks for this
directly, and it is also the only way the screen can be trustworthy: a hub with
its own copy of what a caregiver can see would eventually disagree with the
permissions that apply.

One consequence worth recording: the privacy *service* does not import the
robot package, because PRD 11's architectural rule forbids it and a test
enforces it. The robot's states are read in the API layer — which already does
so for the Nura Device screen — and handed in. The hub describes the robot from
what the robot reported; it does not go and ask.

## Consequences

**What got easier.** A person can see their privacy state, take their data, and
remove it. A reviewer has one document per question and one suite per boundary.
A future PRD's owner routes are covered by the cross-boundary walk the day they
are written, and its new query keys and storage keys fail a test until
classified.

**What got harder, on purpose.** Adding a column to an exported table requires
a decision. Adding a caregiver-reachable route requires writing down what it is
for. Adding a query key or a storage key requires saying which scope it is in.
Each of those is a small cost at the moment somebody has the context to pay it,
instead of a silent leak a year later.

**What this stage is not.** It is not a penetration test, not a compliance
certification, and not evidence about anything outside this code. §54 and §32
both say so, and PRD 14 §32 repeats it. The security suite is evidence about
the boundaries this code enforces.

**What is still not true.** No notification, alarm or vibration has fired; no
frame has been drawn on a panel; no sound has been played; no physical
acknowledgement has reached the backend; no weather, news, calendar, push, SMS
or calling provider is configured. PRD 13 changed none of that and claims
none of it.

**What a later PRD should pick up.** A per-category export, if anybody asks for
one — the table spec already has the shape. Deleting a single *account* rather
than a profile, which needs a decision about what happens to a caregiver whose
only reason to exist was that account. And a real re-authentication step, which
needs the identity provider to offer one.
