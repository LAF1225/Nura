# 0010 — Appointments and the doctor report

**Status:** Accepted · PRD 7

## Context

PRD 7 is where everything Nura has recorded points outward: a page somebody puts
on a doctor's desk. That turns three previously internal questions into
externally visible ones — what may the summary *say*, what is in it when the
records change afterwards, and who can read the file. Seven decisions shaped the
answers.

## Decision 1 — a report is a stored snapshot of finished text

`appointment_reports.snapshot` holds the report's content as sentences, exactly
as it read at the moment the user pressed Generate. The PDF is rendered from that
stored copy, and so is the in-app preview.

PRD 7 section 30 asks for a snapshot "so an exported report does not silently
change when health records later change". Storing the *selection* and re-running
the query would have satisfied the letter of that and not the point: a symptom
entry corrected next week would change what a document handed over last week
says. Storing structured data and rendering it later would have the same problem
one level up — a change to the wording would rewrite old reports.

Storing finished text costs duplication (the same fact is in the entry and in the
snapshot) and gains three things: an exported report is immutable in the strongest
sense; the preview and the PDF cannot disagree, because they render the same
strings; and "does Nura say anything it should not?" becomes a test that reads a
JSON column rather than an inspection of a rendering pipeline.

## Decision 2 — one file writes prose, and nothing else does

`services/appointments/snapshot.py` is the only module in the feature that turns
a value into a sentence. Everything before it counts rows; everything after it
lays text out.

The alternative — wording spread across the service that fetched each kind of
record — is how a no-diagnosis rule quietly fails. With one file,
`all_text(snapshot)` can return every string a report can contain, and the tests
that forbid a diagnosis, a likelihood, an attributed cause, a treatment
suggestion or a graded adherence figure read *all* of it rather than the parts
somebody remembered to check. A section added later is covered without the test
changing.

The same shape is used on the phone: `features/appointments/copy.ts` holds every
sentence the screens say, and its own test enumerates them against the same
forbidden list.

## Decision 3 — the user picks symptoms one at a time, and Nura never orders them

The selection carries `symptom_episode_ids`, not a single `symptoms: true`
switch. The review lists symptoms by when they were last written about — a fact
about the data — with no severity ordering, no "significant" flag and no
recommendation.

PRD 7 section 15 says Nura must not choose which symptom matters more. One switch
would make that choice; so would sorting by severity, which is the obvious and
wrong default. The cost is a longer selection screen. The gain is that the only
thing deciding what a doctor reads is the person who is going to be in the room.

Medications are the mirror image: `medication_ids` of `null` means "the active
ones", which is what the screen shows, and unticking one turns the implicit list
into an explicit one so the server cannot include it anyway.

## Decision 4 — the report period explains itself

`periods.resolve` returns the dates *and* `preset`, `requested_preset` and
`fallback_reason`.

PRD 7 section 14 prefers "since the previous appointment with the same clinician"
and falls back to 30 days. Two things follow. First, "the same clinician" means
the same **linked clinician record** — two appointments whose titles both mention
cardiology are not evidence of the same doctor, and a report period set from a
coincidence of wording is worse than the fallback. Second, when the preference
cannot be honoured the app says why: *Nura has no earlier appointment with this
clinician, so it can't work out when you last met.* A range the user did not
choose and cannot explain is the thing section 14's "show the selected range
clearly" exists to prevent.

## Decision 5 — regeneration adds a version; nothing is ever overwritten

Every Generate writes a new row with the next version number. The previous
snapshot and the previous file stay exactly as they were.

PRD 7 section 31 requires it, and the reason is that a report leaves the app: by
the time somebody regenerates, v1 may be in an email. `version` is taken from the
highest currently stored, so deleting v1 while v2 exists and regenerating gives
v3 — a version number never sits between two others. Deleting the *newest*
version does free its number, which is accepted: the user removed that document
on purpose, and every version is shown with the moment it was generated, exactly
as section 31's own example metadata does.

## Decision 6 — a report PDF is stored and served like a symptom photo

Private object storage under a server-built key, no URL in any response, and an
authenticated route that re-checks account → profile → appointment → report before
serving a byte.

PRD 7 section 52 allows a signed temporary URL as an alternative. It was refused
for the reason PRD 6 refused it: a signed URL is a bearer token in a query string
— it lands in logs, in screenshots and in share sheets, and it stays valid until
it expires no matter who ends up holding it. A doctor summary is at least as
sensitive as the photograph, and the authenticated route costs one function.

Two ordering rules come with it. The file is written *before* the row that claims
it exists, and a CHECK constraint makes `status = 'ready'` imply a stored key —
so the app can never be offered an export that is not there. Deletion goes the
other way: the file first, then the row, because a row with no file is
recoverable while a file with no row is invisible forever.

## Decision 7 — display strings for appointment times are rendered on the server

`day_label`, `time_label`, `when_label` and `relative_day` are computed by the
backend and sent with the appointment.

This is unusual — the app formats everything else itself — and it follows from
PRD 7 section 42. An appointment must be shown in *its own* IANA zone, which needs
the time-zone database; `Intl` with full zone data is not something this project
can rely on across both React Native platforms. Doing it on the server also gives
one implementation of "Tomorrow at 3:30 PM" rather than one per platform, and it
is why the mobile app contains no time-zone arithmetic for appointments at all.

The visible consequence during travel is documented rather than hidden: an
appointment reads "Tomorrow" when it is tomorrow where the appointment is.

## Consequences

**A report is auditable in one place.** The stored snapshot is the whole content,
and one function returns all of it.

**An exported report is genuinely immutable.** Re-rendering an old row produces
the file that was already sent — asserted at the byte level, with the PDF's
creation date pinned to the snapshot's own moment.

**Nothing in the feature knows a robot exists.** No BLE, no device token, no
heartbeat, so PRD 7 section 43's four hardware states are not states here at all.

**Report text is English only.** The date and count formatting is hand-rolled to
be locale-independent, which is what makes the output deterministic; translating
it is later work and will start in `wording.py`.

**A non-Latin script will not render in the PDF** until a Unicode font is
configured. `report_font_path` is the one setting that fixes it, with no code
change; until somebody sets it, the limitation is in the README's known issues.

**Photos are not in reports.** PRD 7 section 28 permits deferring them, and
embedding one would remove the per-byte authorization that is the whole point of
how symptom photos are stored.
