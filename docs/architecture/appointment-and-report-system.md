# The appointment and report system

PRD 7. Appointments, the questions to ask at them, and the one-page summary
somebody hands a doctor.

This is the stage where everything Nura has recorded finally points outward. The
symptom entries, the dose history, the check-ins and the health record stop being
things the app shows you and become a page you can put on a desk. That makes the
boundary PRD 7 section 3 draws the most important thing in the feature:

> The workflow should help the user **prepare and communicate clearly**, not
> diagnose.

Everything below follows from that sentence and from one architectural
consequence of it: **a report is a snapshot, not a query.**

---

## The three tables

```text
appointments                  a visit, entered by hand
    |
    +-- appointment_questions     what the person wants to ask
    |
    +-- appointment_reports       a frozen summary, and the PDF made from it
```

All three belong to a profile and cascade with it. The only reference out into
the older tables is `appointments.clinician_id`, and it is `ON DELETE SET NULL`:
deleting a doctor from the user's own list must not delete the appointments that
mention them.

### Manual entry, and nothing else

There is no calendar integration in PRD 7 (section 4) and no column that implies
one — no external id, no sync token, no provider. A test asserts their absence,
so adding sync later is a deliberate schema change rather than a field that crept
in.

### An appointment carries its own time zone

`scheduled_at` is the instant; `timezone` is the IANA zone it was arranged in.
Both are stored, for the same reason a medication schedule stores both (PRD 5
section 12): an appointment at 3:30 PM in London is still at 3:30 PM in London
after the clocks change and after the user flies to Karachi.

**Display strings come from the server.** `day_label`, `time_label`,
`when_label` and `relative_day` are rendered by the backend and sent with the
appointment. That is unusual and deliberate: resolving an instant into a named
zone needs the IANA database, which the server has and a React Native runtime may
not — `Intl` with full time-zone data is not something this app can rely on across
both platforms. It also means one implementation of "Tomorrow at 3:30 PM" rather
than one per platform, and it is why the mobile app contains no time-zone
arithmetic for appointments at all.

The consequence during travel, stated plainly: an appointment reads "Tomorrow"
when it is tomorrow *where the appointment is*. For nearly every appointment that
is also the user's calendar; while abroad it is the more useful of the two
answers.

### Nothing is inferred from the clock

An appointment whose time has passed is *listed* under Past, and its status stays
`scheduled` until the user says what happened. PRD 7 section 7 rules out
inferring `missed`, and the reason is empirical: the commonest reason an
appointment is not marked completed is that nobody opened the app.

`cancelled_at` and `completed_at` are enforced by CHECK constraints against their
status, so the two can never disagree. The reverse is not forced — an appointment
put back to `scheduled` keeps the timestamp of a decision that was once made.

### `preparation_status` is a cache of a derivation

PRD 7 section 6 lists it as a field, and the project's rule is that a value
meaning "right now" is never stored. Both are satisfied: the column exists, and
`appointments.preparation_state()` is the only thing that writes it. It is worked
out from what exists —

| state | means |
| --- | --- |
| `not_started` | no questions, no report |
| `in_progress` | at least one question, no report yet |
| `complete` | at least one generated report |

— so the column can never claim a report that is not there.

---

## Questions

`appointment_questions` holds the user's own words, in their own order
(PRD 7, sections 22 and 23). Nothing rewrites a question, merges two that look
similar, expands an abbreviation or sorts by importance: it is going to be read
out in a consulting room by the person who wrote it.

### Suggestions are offers, and stop being suggestions once accepted

`services/appointments/suggestions.py` produces deterministic prompts from the
review the user is already looking at — a symptom they recorded as worsening, a
new symptom, doses that went unrecorded, and one generic prompt about follow-up
tests. **There is no model behind this**, which PRD 7 section 24 requires
outright.

Three rules make a prompt safe:

1. **It points at something the user recorded, and says nothing about it.**
   "Would you like to ask about your worsening headaches?" restates their own
   answer. It never explains, connects or predicts — no "could your medication be
   causing this?", because that is a clinical hypothesis.
2. **Nothing is added until the user presses the button.**
3. **Accepting one writes an ordinary question.** There is no `is_suggested`
   column and no way to tell afterwards, because from that point it is theirs.

A test feeds every prompt through a forbidden-phrase list — cause, likelihood,
diagnosis, treatment — so a prompt added later cannot quietly cross the line.

---

## The report pipeline

PRD 7 section 29 asks for a deterministic pipeline, and this is it, in order:

```text
preparation.build   read the records                 no interpretation
        v
snapshot.build      turn them into sentences         the only file that writes prose
        v
pdf.render          lay the sentences out            no database, no clock
        v
reports.generate    store the row and the file       versioned, private
```

Each step is a function of the one before it. Only the last touches the database
or the disk.

### `preparation` counts; it does not interpret

Everything in the review is counted from rows the user entered. Four boundaries
are kept here rather than left to whoever writes the screen:

- **No symptom is more important than another.** The list is ordered by when it
  was last written about, because that is a fact about the data. Not by severity,
  not filtered to the "significant" ones, and with no flag saying which to
  include — PRD 7 section 15 puts that decision with the user, and an ordering by
  severity would quietly make it for them.
- **Adherence is counts first.** `13 of 14 scheduled doses were marked as taken`
  is what the report says. The percentage exists and is never labelled adequate or
  inadequate (sections 18 and 19).
- **A skipped dose's own words are not included unless asked for.** The counts
  come out automatically; the free text is theirs to offer (section 19).
- **Uncertainty survives.** A symptom's `uncertain_items` and `negated_items` are
  carried through rather than dropped, so a review cannot read as more definite
  than the person was (sections 16 and 47).

One deliberate inclusion is worth naming: **an ongoing symptom with no entries in
the period still appears**, reporting zero entries. An ongoing symptom nobody has
updated for six weeks is exactly the thing a person forgets to mention, and
leaving it out because the window is 30 days would help them forget it.

### `snapshot` is the only file that writes prose

This is where recorded facts become sentences, and it is the only such place —
so "does Nura say anything it should not?" has exactly one file to read, and a
test can enumerate every sentence the system can produce.

What it may say comes from PRD 7 section 16's own example:

> Headache was logged 6 times during the selected period. Severity ranged from
> 3/10 to 6/10. The latest entry was marked worsening.

Restatement, with the user's own words quoted and the counts counted. What it may
not say — diagnosis, likelihood, cause, treatment, a judgement of adherence, an
interpretation of a wellbeing pattern — has no code path: every sentence is a
template with values substituted in.

`all_text(snapshot)` returns every string a report can contain, which is what the
no-diagnosis tests read. Having one such function means a section somebody adds
later is covered without the test changing.

### Aiming for one page

PRD 7 section 26 gives three instructions in priority order, and the builder
applies them in that order:

1. **Summarise more tightly.** Over budget, the symptom detail lines — factors,
   associated symptoms, quoted notes — drop out of the summary. They are in the
   appendix.
2. **Move detail to the appendix**, which is what the appendix is.
3. **Never shrink text to unreadable size.** So if the user's own selections still
   do not fit, the summary runs onto a second page at full size. That is the
   honest outcome for somebody who chose a lot of content, and the snapshot
   records `summary_condensed` so the app can say detail was moved.

The budget is a line count, not a layout engine: `ONE_PAGE_LINE_BUDGET` with an
estimate of how each line wraps. It decides only *how much detail to include*,
never the font size.

### The PDF

`fpdf2`. Pure Python with no system libraries behind it, which matters for a
project developed on Windows and deployed on Linux, and its output is
byte-identical for identical input once the creation date is pinned — which this
module pins to the snapshot's own `generated_at`. So "regenerate the PDF for
report v1" produces the file that was already sent, not a new one that merely says
the same thing. A test asserts that the stored bytes equal a fresh render of the
stored snapshot.

The design is printable rather than themed (section 59): black on white, one
accent colour for headings, no images, no background fills. The app renders the
same snapshot in Light or Dark for reading on a phone; a document that comes out
of a surgery printer should look like a document.

**Fonts, and a real limitation.** With no font configured the document is set in
the PDF standard Helvetica, whose encoding covers Latin-1. `sanitise` folds the
typographic punctuation this codebase uses — em dashes, curly quotes, ellipses —
down to ASCII, and replaces anything else it cannot draw with `?` rather than
dropping it silently. A name in Arabic or Devanagari will therefore not render.
The fix is one setting: point `report_font_path` at a TrueType font and every
glyph in it renders, with no code change. Until somebody does, the limitation is
in the README's known issues.

### Versions

`reports.generate` writes a new row every time. The previous snapshot and the
previous file are left exactly as they were, because somebody may already have
emailed it (PRD 7, section 31). `version` counts from the highest currently
stored, so deleting v1 while v2 exists and regenerating gives v3 — a version
number never sits between two others.

Deleting the *newest* version does free its number. That is deliberate: the user
removed that document on purpose, and every version is shown with the time it was
generated, which is what section 31's own example metadata does.

### Storage and privacy

A report's PDF is as private as a symptom photo and is stored the same way
(PRD 7, sections 35 and 52):

- the bytes go to the private object store under a key **the server builds** from
  ids it generated;
- the key never appears in a response — there is no URL, public or signed;
- the only way to the file is a route that re-checks account → profile →
  appointment → report before serving a byte, with `Cache-Control: private,
  no-store`;
- the row is written only *after* the file is in storage, and a row that says
  `ready` has a file behind it — the database CHECK says so. So the app cannot be
  offered an export that does not exist.

Deleting a version removes the file first and then the row: a row with no file is
recoverable, a file with no row is invisible and stays on disk forever. Deleting
an appointment purges its report objects before the cascade takes the rows.

### Photos are not in reports

PRD 7 section 28 permits deferring them, and they are deferred. A symptom photo is
the one thing in Nura that never leaves the backend without an authenticated
per-byte check (PRD 6, section 63); embedding one in a shareable PDF would remove
that control, and it would work against a one-page summary. The count is reported
on the selection screen so nobody thinks their photos were lost.

---

## The report period

PRD 7 section 14 prefers "since the previous appointment with the same clinician"
and falls back to the last 30 days. Both halves need care.

**"The same clinician" means the same linked clinician record.** Two appointments
whose titles both say "cardiology" are not evidence of the same doctor, and
setting a report period from a coincidence of wording would be worse than the
fallback. So the preference applies only when the appointment points at a
clinician the user chose from their own list.

**The fallback is recorded, not silent.** `preset` says what was applied,
`requested_preset` says what was asked for, and `fallback_reason` says why they
differ — so the app can tell somebody their report covers the last 30 days
*because* Nura has no earlier visit with that clinician, rather than showing a
range they did not ask for and cannot explain.

**A period never runs past today**, and it ends on the appointment's own day or
today, whichever comes first. Preparing for Thursday on Tuesday covers up to
Tuesday; writing a report a month after a visit covers up to the visit.

---

## What the user controls

PRD 7 section 25's switch list, with one structural decision: **symptoms are
chosen individually, not by a single switch.** Section 15 forbids Nura deciding
which symptom matters more, and one "symptoms" toggle would be Nura deciding.

The selection carries:

| field | meaning |
| --- | --- |
| `include` | the nine section switches |
| `symptom_episode_ids` | which symptoms, one by one |
| `symptom_note_entry_ids` | which of their notes to quote |
| `medication_ids` | `null` means the active ones; a list means exactly those |
| `checkin_note_dates` | which wellbeing notes to quote |
| `medical_note_ids` | which medical notes to attach |
| `focus` | the user's own reason for the visit |
| `include_appendix` | section 27's toggle |
| `include_skip_reason_notes` | section 19's free text, off by default |

It is stored on the report row beside the result, so regenerating starts from the
user's last answers rather than from defaults.

### Missing data

A section the user asked for with nothing in it reads `Not recorded.` rather than
being omitted (PRD 7, section 46). That is worth saying: a doctor learning that no
allergies are recorded is different from a doctor being shown nothing at all. A
section they did *not* ask for is absent entirely.

---

## On the phone

```text
Care ─┬─ Medications
      └─ Appointments ─┬─ list (Upcoming / Past / Cancelled)
                       ├─ new / [id]/edit          the form
                       └─ [id] ─┬─ prepare         review + tick symptoms
                                ├─ questions       the list, and the offers
                                ├─ select          sections + appendix
                                ├─ preview         the frozen text, then Share
                                └─ reports         every version
```

### Three stores, for the same reason

The appointment form draft, the report selection and the chosen history list all
live in Zustand stores rather than component state. Two reasons, both load-bearing:

1. **They outlive the screen.** Preparing is four routes editing one thing, and
   PRD 7 section 32 requires Back to work. The form draft and the selection are
   persisted to AsyncStorage, which is the draft preservation section 53 asks for.
2. **A store update re-renders under React 19 where a local `useState` update
   from a fired event does not** — the limitation recorded in the README since
   PRD 3. It is why the appointment form's typing is testable at all.

One consequence learned the hard way and worth repeating: a press that arrives
before a store update has re-rendered reads stale state. The report generator
therefore reads the selection at press time rather than from the render closure,
and the tests wait for the *control* to show its new state before pressing the
next thing.

### The preview is the snapshot, not a picture of a PDF

`ReportPreviewCard` renders the report's own frozen content in the app's own
styles. A rasterised PDF page cannot be read by a screen reader, does not reflow
at larger text sizes and does not follow Light/Dark — all of which PRD 7 section
58 asks for. Rendering the same snapshot the PDF is made from is also what makes
"what you approve is what you export" true rather than hoped for.

### Export

```text
authenticated download -> app-private cache -> native share sheet
```

The file is downloaded with a bearer token (there is no URL to hand anybody),
written into `Paths.cache/nura-reports`, and passed to the platform's own share
sheet. Cache rather than documents: an exported PDF is a copy of something the
backend still holds, so the OS reclaiming it costs nothing. Each export clears
the directory first, so the phone never accumulates a folder of doctor summaries.

Nura sends it nowhere itself. PRD 7 section 34 rules out delivering it to a
doctor, and the share sheet is the whole mechanism.

The filename is `Nura_Health_Summary_2026-10-02.pdf` — a date and nothing else
(section 33). A filename shows up in a share sheet, a downloads list, a file
manager and a notification, none of which the user chose to put it in.

---

## Offline

PRD 7 section 53, split by what can honestly be done without a connection:

| action | offline behaviour |
| --- | --- |
| viewing appointments | served from the TanStack Query cache |
| adding an appointment | kept on the phone, shown as pending, sent later |
| adding a question | the same |
| generating a report | **refused, and said so** |

The last row is the important one. A PDF is built by the backend, so there is
nothing useful to keep on the phone, and section 53 says plainly not to pretend
generation succeeded. The screen says Nura needs a connection and that the
selections are saved — which they are, in a persisted store — so nothing the user
chose is lost.

Both queues are keyed by a client-generated id, and the server answers a replay
with the row it already stored. Appointments are drained before questions, so a
pair saved together lands in one pass rather than two.

---

## Reminders

Two per appointment: a day before and two hours before (PRD 7, section 36). They
reuse PRD 5's machinery — same permission flow, same reconciliation, same storage
shape — with a lower Android channel importance, because an appointment tomorrow
is something to know rather than something to do this minute.

`rebuildAppointmentReminders` is the single entry point section 54 asks for.
Changing the time, changing the date, cancelling the appointment and turning
reminders off all go through it, because the plan is computed from the upcoming
list and every write invalidates that list. There is no per-case cancel logic to
get wrong.

Nothing medical is in a notification (section 57): the appointment's own title,
the time, and the offer to prepare. No clinician, no location, no symptom, no
medication.

---

## Authorization

Every route is nested under the profile the records belong to and resolves it
through `OwnedProfile`. The chain is complete at every depth: a question is
fetched by profile *and* appointment *and* id; a report the same way; and the PDF
route re-walks all of it before it serves a byte. Anything else is a 404 rather
than a 403, so an id is never confirmed to exist (PRD 7, section 51).

A clinician id is checked against the profile's own list before it can be linked,
so an appointment cannot point at another account's contact details and read the
name back out of it.

---

## Robot independence

Nothing in the appointment or report code paths knows a robot exists. There is no
BLE, no device token, no heartbeat and no hardware check anywhere in the feature —
so PRD 7 section 43's four states (no robot, offline, simulated, online) are not
four states here at all, and there is nothing to disable.

Section 44 asks for reusable service methods for future voice behaviours. They are
the ordinary ones: `questions.create_question` is what "would you like me to add
that question for your doctor?" would call, and `preparation.build` is what a
spoken review would read from. No physical voice implementation exists, and none
is claimed.

---

## Privacy and logging

Never logged: appointment titles, notes, clinician names, locations, question
text, answer notes, report headings, report content, or any filename
(PRD 7, section 57). Every log line in the feature is a verb and a count —
`appointments: created an appointment`, `reports: rendered a report of 2 pages`.

Analytics carries no health content. The event names section 57 allows are the
shape of what would be sent if analytics existed; none is wired up yet.

---

## Code map

```text
backend/app/models/appointment.py              three tables
backend/app/schemas/appointment.py             request/response models, drift guards
backend/app/api/v1/appointments.py             the routes
backend/app/services/appointments/
    appointments.py                            the visit: CRUD, status, previous visit
    questions.py                               the user's words, and their order
    periods.py                                 which stretch of time, and why
    preparation.py                             reading the records back. No interpretation
    suggestions.py                             deterministic prompts. No model, ever
    snapshot.py                                the only file that writes prose
    pdf.py                                     snapshot in, bytes out
    reports.py                                 versions, private storage, export
    summary.py                                 what Today and Care need
    wording.py                                 dates, counts, lists
backend/tests/test_appointments.py             64 tests
backend/tests/test_reports.py                  42 tests

mobile/src/features/appointments/
    types.ts                                   the model
    copy.ts                                    all user-facing wording
    draft.ts                                   validation and payloads
    formStore.ts                               the appointment form, persisted
    selectionStore.ts                          what goes in the report, persisted
    listStore.ts                               which history list is on screen
    pending.ts                                 the two offline queues
    notifications.ts                           the two reminders
    reportExport.ts                            download, cache, share
    api.ts / hooks.ts                          requests and server state
    components/                                form, rows, selection cards, preview
mobile/app/appointments/                       list, new, [id], edit, prepare,
                                               questions, select, preview, reports
```

---

## Related

- [The symptom system](symptom-system.md) — where the symptom half of a report
  comes from, and the privacy pattern the report storage copies.
- [The medication system](medication-system.md) — the adherence figures a report
  quotes, defined once there.
- [The health record](health-data.md) — conditions, allergies and procedures, the
  background a report can carry.
- [ADR 0010](../decisions/0010-appointments-and-reports.md) — the decisions behind
  this design.
