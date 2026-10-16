# Data classification and retention

PRD 13 §11 asks for one shared document covering nine categories, and §25 for a
retention policy that is "truthful and implementation-backed". Both are here.

**Everything in this document is backed by code**, and where the answer is
"until the user removes it" that is because nothing deletes it — not because a
policy says to keep it. PRD 13 §25 is explicit about not inventing legal
retention obligations, and none are invented here.

The categories are one tuple, `DATA_CATEGORIES` in `models/enums.py`, read by
this document, the export manifest, the deletion inventory and the privacy hub,
so "what categories are there" has one answer rather than four that drift.

---

## 1. The nine categories

### account

| | |
|---|---|
| **sensitivity** | Low. An email address, a phone number, display preferences. |
| **storage** | `users`, `user_settings`, `profiles`, `account_profile_roles`, `dashboard_preferences`, `daily_checkins` |
| **authorization** | The verified token's own account. A profile is reachable only through `account_profile_roles`. |
| **retention** | Until the user removes it. A profile goes on deletion; the **account survives**, because an account with no profile is where a new sign-up starts. |
| **export** | Yes — `profile.json`, minus `auth_provider_id` (the identity provider's subject). |
| **deletion** | The profile and everything cascading from it. |
| **logging** | A profile id may be logged. A preferred name, a check-in note and an email address may not. |

A daily check-in note is in this category rather than `health` because of where
it lives, and it is treated as health-sensitive for logging: somebody's answer
to "how are you today" is about their health.

### health

| | |
|---|---|
| **sensitivity** | **Highest.** Medical history, in the user's own words. |
| **storage** | `medical_conditions`, `medications`, `allergies`, `procedures`, `medical_notes`, `clinicians`, plus the medication system (`medication_schedules`, `medication_schedule_times`, `medication_doses`, `medication_supply`) and the symptom system (`symptom_episodes`, `symptom_entries`, `symptom_photos`) |
| **authorization** | Owner through `OwnedProfile`; a caregiver only through PRD 9's category permissions, and never through a PRD 0–8 route. |
| **retention** | Until the user removes it. Nothing expires, nothing is archived, and a dose row is kept after it is answered because adherence history is the point. |
| **export** | Yes — `health.json`, `medications.json`, `symptoms.json`. |
| **deletion** | Cascades with the profile. Photos are deleted from object storage by `ProfileDeletionService`, which no cascade could do. |
| **logging** | **Never**, at any level. No condition name, medication name, dose, skip reason, symptom name, free text, or photo path. |

### assistant

| | |
|---|---|
| **sensitivity** | High. Conversations are about health, and a memory is something the user confirmed about themselves. |
| **storage** | `assistant_preferences`, `assistant_memories`, `conversations`, `conversation_messages`, `assistant_prompt_dismissals` |
| **authorization** | Owner only. No caregiver route reaches a conversation or a memory. |
| **retention** | Until the user removes it. Conversations can be deleted one at a time or all at once (§7), which removes their messages by cascade and **nothing else** — not memories, not the health record. |
| **export** | Yes — `assistant.json`, excluding each message's `meta` (model name, latency, which tools ran: Nura's machinery rather than the person). |
| **deletion** | Cascades with the profile. |
| **logging** | **Never** — not a message, not a reply, not a memory, not a custom instruction, at any level (PRD 8 §58). |

### caregiver

| | |
|---|---|
| **sensitivity** | High, and it concerns **two** people. |
| **storage** | `caregiver_relationships`, `caregiver_permissions`, `caregiver_suggestions`, `family_threads`, `family_messages`, `emergency_contacts` |
| **authorization** | Owner for the list and permissions; a caregiver for their own surface; either side for a two-sided conversation. |
| **retention** | Until the user removes it. A revoked relationship is **kept** with `revoked_at` set, because the history of who had access is part of the record; it grants nothing — `granted_keys` returns an empty set for any non-active relationship. An invitation token hash is cleared on consumption. |
| **export** | Yes — `caregivers.json`, with the caregiver's **name as the user typed it** and never their account id. |
| **deletion** | Cascades with the profile, so caregiver access ends immediately. The caregiver's own *account* is untouched. |
| **logging** | **Never** a message, a check-in code's context, a phone number or an invitation token. |

### safety

| | |
|---|---|
| **sensitivity** | High. Where somebody was, when, and who was tried. |
| **storage** | `safety_monitoring_sessions`, `safety_events`, `safety_escalation_attempts`, `safety_alerts` |
| **authorization** | Owner for monitoring and history; either side for alerts, then the `safety_alerts` permission. |
| **retention** | Until the user removes it. A false alarm is kept and labelled rather than deleted, because a detector's false positives are the thing a later review needs. |
| **export** | Yes — `safety.json`, excluding `recipient_key` and `idempotency_key` (deduplication tokens, not information about what happened). |
| **deletion** | Cascades with the profile. |
| **logging** | **Never** a free-text response or a recipient's number. Event ids, types and statuses are fine. |

### productivity

| | |
|---|---|
| **sensitivity** | Medium, and easy to underestimate. "Ring the clinic about the results" is health information in a task. |
| **storage** | `tasks`, `general_reminders`, `general_reminder_occurrences`, `alarms`, `routines`, `routine_steps`, `routine_runs`, `routine_step_completions` |
| **authorization** | Owner only, except routines, which a caregiver may read with the `routines` permission. |
| **retention** | Until the user removes it. Occurrences and runs are generated a fortnight ahead and **replenished on read**; a missed one is computed rather than stored. Nothing prunes the past. |
| **export** | Yes — `daily-life.json`. |
| **deletion** | Cascades with the profile. |
| **logging** | **Never** a title, note, body or step. The action and a count, which is PRD 12 §45's own example. |

### device

| | |
|---|---|
| **sensitivity** | Low in itself. It carries **two secrets**. |
| **storage** | `devices`, `device_capabilities`, `device_presentation_preferences`, `device_presentations`, `provisioning_sessions` |
| **authorization** | A device token for the robot's own routes; the claiming account for the app's. **No caregiver route reaches a device at all.** |
| **retention** | A claimed device is kept until the account unpairs it. A provisioning session is single-use and short-lived. A presentation expires and is swept by `robot_maintenance.py`, which nothing depends on because expiry is applied on read. |
| **export** | Partly — `devices.json` holds the device, its capabilities and its presentation preferences. **Not** `bootstrap_secret_hash` or `device_token_hash`. Not the presentation queue (Nura's working state, built from data already exported in full) and not provisioning sessions. |
| **deletion** | A device is **unlinked, not unclaimed**: `owner_profile_id` and `setup_completed_at` are cleared and the claim stays, because the robot still belongs to whoever bought it. |
| **logging** | A hardware id and a device id may be logged. **Never** a bootstrap secret, a device token, a Wi-Fi password or a pairing code. |

### media

| | |
|---|---|
| **sensitivity** | **Highest.** A photograph of a symptom, and a generated doctor report. |
| **storage** | Private object storage. The database holds a key; `symptom_photos.storage_key`, `appointment_reports.file_storage_key`, `data_exports.file_storage_key`. |
| **authorization** | An authenticated route that re-checks the whole chain **for every byte**. There are no signed URLs anywhere in Nura. |
| **retention** | A photo and a report live as long as their row. An **export archive expires after 24 hours**, compared on every read and swept by `scripts/privacy_maintenance.py`. |
| **export** | Yes — under `files/`, with each row carrying its archive-relative path. The internal storage key is never exported. |
| **deletion** | The one thing a cascade cannot do, and the reason `ProfileDeletionService` exists: keys are read before the rows go, files deleted after the transaction commits. |
| **logging** | **Never** a storage key, a path or a file name the user chose. |

### audit

| | |
|---|---|
| **sensitivity** | Medium, and it is about **other people's actions**. |
| **storage** | `caregiver_audit_events`, `safety_audit_events` |
| **authorization** | Nothing reads them through the API. There is no audit-log screen (PRD 13 §53 rules one out). |
| **retention** | Kept with the profile. Cascades with it, so deleting a profile removes its audit trail too — the trail is about access to *that* profile, and keeping it after the data is gone would be the one piece of somebody's record that outlived their deletion. |
| **export** | **No**, and the manifest says so with a reason. An audit row records that somebody's caregiver read something; it is the evidence trail for the access controls themselves and it describes third parties. |
| **deletion** | Cascades. No security metadata is retained after a deletion, because there is no real reason to and §22 says not to invent one. |
| **logging** | Event types and ids. **No** `meta` contents. |

---

## 2. Retention, by lifetime

| what | how long | enforced by |
|---|---|---|
| Active user data | Until the user removes it | nothing deletes it |
| A profile the user deleted | Gone, with its files, within one request | `ProfileDeletionService` |
| An export archive | **24 hours** | compared on every read; swept by `privacy_maintenance.py` |
| A robot presentation | Its own `expires_at` | compared on every read; swept by `robot_maintenance.py` |
| A provisioning session | Single-use, short expiry | checked at use |
| An invitation token | Short-lived, single-use, stored hashed | checked at use |
| A report PDF | As long as its row | deleted with the row |
| A symptom photo | As long as its row | deleted with the row |
| Audit events | As long as the profile | cascade |
| Revoked caregiver relationships | Kept, inert | `granted_keys` returns empty for non-active |

**Three of those sweeps are optional and one is not.** Export expiry and
presentation expiry are applied on every read, so the scripts keep storage tidy
rather than keeping a rule. `safety_maintenance.py` is the other kind: PRD 10's
escalation deadlines only fire if something runs it, and nothing in this
repository schedules it.

### Temporary files

| what | where | cleaned by |
|---|---|---|
| Export archives | private object storage, `exports/<id>.zip` | 24-hour expiry; `privacy_maintenance.py`; deleted with the row |
| Report PDFs on the phone | app-private cache, `nura-reports/` | PRD 7's export path removes earlier files on each share |
| Photos waiting to upload | the symptom offline queue | removed when the upload succeeds; cleared on sign-out |
| Pending queues and drafts | AsyncStorage | cleared on sign-out by `clearLocalData` |

No new scheduler was added for any of this (§26, §48). `privacy_maintenance.py`
exists because an archive is the first artefact with an expiry, and it follows
the pattern of the two maintenance scripts already there.

---

## 3. What is never logged

§12's list, enforced by `tests/test_privacy_logging.py`, which captures the
whole `app` logger tree at `DEBUG` and drives one write per domain:

```text
medical records      symptoms            medications
conversations        memories            caregiver messages
safety event text    tasks and reminders report contents
phone numbers        attachment URLs     invitation tokens
```

The last is not in §12's list and belongs there: an invitation token grants
caregiver access to somebody's medical record.

What logs *do* carry: ids, action names, counts, timestamps and error types.
`privacy.export create {'id': …, 'files': 11, 'bytes': 48210}` is the shape.

---

## 4. What a user can do about any of it

| | where |
|---|---|
| See what Nura stores | More → Privacy & Security |
| Read and remove what Nura remembers | Nura → What Nura remembers |
| Delete one conversation, or all of them | Nura → Conversations |
| Review and change caregiver access | Privacy & Security → Caregiver access |
| See what Nura can and cannot reach | Privacy & Security, and More → Tasks & routines |
| Export everything on a profile | Privacy & Security → Export your data |
| Delete everything on a profile | Privacy & Security → Delete your data |

---

## Related

- [privacy-security-reliability.md](privacy-security-reliability.md) — the
  export format, the deletion order, the authorization matrix
- [ADR 0016](../decisions/0016-privacy-export-deletion-and-reliability.md) —
  the decisions
- [health-data.md](health-data.md) — the records themselves
