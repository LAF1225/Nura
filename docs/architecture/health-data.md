# Health data

How Nura stores what someone tells it about their health, who it belongs to,
and what is deliberately *not* done with it.

This covers the health record introduced in PRD 4: conditions, medications,
allergies, clinicians, procedures, medical notes and blood type. Daily
wellbeing check-ins are health-adjacent but separate — see
[the system overview](system-overview.md).

**A medication record is what a medication *is*.** When to be reminded about
it is a schedule, which lives in its own tables and is described in
[the medication system](medication-system.md). PRD 5 did not change a single
column here: a record still carries no schedule, and nothing in this document
reminds anybody of anything.

> **None of this needs the robot.** Every health feature works with no robot
> linked, with one that is offline, and with one the backend has heard from.
> No health endpoint touches the device tables, and no health data is ever
> sent over BLE or embedded in a provisioning payload.

## Who it belongs to

Health records belong to a **profile**, never to the account that typed them
in.

```text
users (the account: who signs in)
  └── account_profile_roles (role: self | setup_helper)
        └── profiles (the person Nura is for)
              ├── medical_conditions
              ├── medications
              ├── allergies
              ├── clinicians
              ├── procedures
              ├── medical_notes
              └── blood_type, health_profile_status, health_profile_step
```

In assisted setup the account holder is not the person the record is about, so
attaching medical data to the account would be wrong from the first row and
very hard to unpick later. Every health table has a `profile_id` and nothing
else that identifies a person.

Three values live on `profiles` rather than in a table of their own, because
each is a single answer about the person rather than a list they keep:
`blood_type`, and the two columns that remember where they got to in setup.
They are still medical data: they are reachable only through the health
routes, and `/api/v1/me` does not return them.

## Authorization

One rule, enforced in one place — the `OwnedProfile` dependency in
`backend/app/api/deps.py`:

1. The caller is identified by a **verified token**, never by anything in the
   request body or path.
2. The profile in the path must be reachable through that account's own join
   row.
3. A record is fetched *by profile and id together*, so there is no path where
   a record is loaded first and authorized afterwards.
4. Anything that fails these is **`404`, not `403`** — the same answer an id
   that never existed would get, so ids cannot be enumerated.

This is the same rule as profiles and devices, deliberately: one convention,
applied everywhere, is easier to keep right than three.

### Room for caregivers later

Authorization is expressed as "this account reaches this profile", not as
"this account owns this data". When caregiver permissions arrive, they become
another way for an account to reach a profile — with a category filter on top
— rather than a rewrite of every endpoint. Nothing in PRD 4 assumes the
account-profile link is exclusive.

## The tables

| Table | Holds | Notes |
| ----- | ----- | ----- |
| `medical_conditions` | name, status, when diagnosed, who diagnosed it, notes | `status` includes `uncertain` |
| `medications` | name, dose, unit, form, frequency, instructions, dates, reason, whether current | record only — schedules live in their own tables |
| `allergies` | allergen, type, reaction, severity | severity is the user's own judgement |
| `clinicians` | name, specialty, clinic, phone, email, address | only `name` is required |
| `procedures` | name, when, hospital, surgeon, outcome | approximate dates supported |
| `medical_notes` | title, body, category | never parsed into anything |

Value sets (`status`, `form`, `allergy_type`, `severity`, `category`,
`blood_type`, `health_profile_status`) are enforced by database CHECK
constraints generated from the same tuples the API validates against, so the
two cannot drift.

### Dates people only half remember

"Diagnosed in 2015" is a year, not the 1st of January 2015. Each approximate
date is **two columns** — an exact date and a year — with a constraint that at
most one is set:

```sql
NOT (diagnosed_date IS NOT NULL AND diagnosed_year IS NOT NULL)
```

Both null is a valid answer: "I don't remember when" is a real thing to say,
and inventing a date to store it would make the record say something the
person did not.

The app carries a third, UI-only value — `exact`, `year` or `unknown` — so the
form can ask the question properly. It is never sent.

### Provenance

`medical_conditions`, `medications` and `allergies` carry a `source`:

```text
user | caregiver | clinician_import | system_import
```

Everything written in PRD 4 is `user`. **The server sets this, not the
client** — a record must never be able to claim it came from a clinician
import when a person typed it in. When caregiver entry and clinical imports
arrive, they set it themselves on the paths that genuinely have that
provenance.

The other three tables have no `source` yet; they gain one when there is a
path that would set something other than `user`.

## Privacy

- **HTTPS outside local development**, as for every other endpoint.
- **Authorization is server-side.** The app decides what to show; it never
  decides what is allowed.
- **Values are never logged.** Health logs name the resource and the action
  and stop: `health.conditions.create success`. A condition name, medication
  name, allergen or note body must not appear in a log, an error message or an
  analytics event.
- **The summary carries no content.** `health-summary` returns counts,
  a percentage and section titles. It is what the Health overview and the
  optional Today card render, so neither can leak a diagnosis onto a screen
  someone else glances at. A test asserts the response contains no record
  names.
- **Nothing reaches the robot.** The robot does not need the health profile to
  operate, and no health data is sent over BLE or included in a provisioning
  payload.
- **Nothing reaches a language model.** PRD 4 stores and displays; it does not
  interpret.

### On the device

One thing is written to the phone: the values in a form the user has not
managed to save. It goes to AsyncStorage, in the app's private data directory,
and is removed as soon as the record is stored — so a save that fails does not
throw away what someone typed. It is never logged and never sent anywhere
else.

## What Nura does not do with it

- It does not check, verify or confirm anything. Every record is what a person
  said, and the app says so on the screens that show them.
- It does not infer. Severity is not read from the reaction text, "active" is
  not derived from an end date, and no condition is suggested from typed text.
- It does not advise. Nothing here tells anyone to start, stop or change a
  medication, and nothing computes an interaction risk.
- It does not alert. A record being added or changed notifies nobody.

## Completeness

The health profile reports a percentage across seven equally-weighted
sections. A section counts once it has something in it; blood type counts once
it has an answer, including "I don't know" and "Prefer not to say", because
both are answers.

It is informational and nothing else: nothing is blocked by an incomplete
profile, there is no warning state, and the wording says how many sections
have information rather than how many are "done".

There is deliberately no "I have nothing to add" flag per section, so someone
with no allergies will not reach 100%. That is accepted rather than solved:
the figure is a gentle prompt, and a flag per section would add state to the
data model to make a progress bar happier.

## What later PRDs need

The schema is structured for what is already known to be coming, and the
first of these has now happened:

- **PRD 5 (medication scheduling)** attached schedules to `medications`
  rather than reshaping it, exactly as anticipated. Not one column in this
  document changed. It did add one rule to this file's routes: a medication
  with recorded dose history cannot be deleted — it is archived by marking it
  inactive instead, which also pauses its schedules (`409
  medication_has_history`). Deleting it would take somebody's adherence
  history with it.
- **PRD 6 (symptoms)** gets its own model. Symptom logs must not be kept as
  medical notes — a note is something a person wrote, and a symptom log is a
  measurement over time.
- **PRD 7 (doctor reports)** needs active conditions, active medications,
  allergies, procedures, clinicians and important notes. All six are
  structured and filterable today; `status`, `is_active` and the note
  `category` are what make that possible.
- **Caregivers** attach to the account-profile link, as described above.

---

## Symptoms are not conditions

PRD 6 adds `symptom_episodes`, `symptom_entries` and `symptom_photos`. They are
health data and everything on this page applies to them: they belong to a
profile, they are reachable only through that profile, a missing one is a 404
rather than a 403, and no value of theirs is ever logged.

What they are **not** is part of the record described above. A condition is what
somebody has been told they have; a symptom is what they are experiencing. Nothing
converts one into the other, in either direction (PRD 6, section 6), and the
counts are reported separately so a summary cannot imply a diagnosis
(section 48).

They are also deliberately outside the completeness figure. The seven sections
above are things somebody fills in; having no symptoms logged is a good state, and
a percentage that rose because somebody felt unwell would be grotesque.
`total_sections` stays 7.

Symptom photos are the one piece of health data that is not a database row. They
are described in [the symptom system](symptom-system.md), which is also where the
privacy chain for them is written down.
