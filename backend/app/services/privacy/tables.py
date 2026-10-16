"""What an export contains, column by column (PRD 13, sections 17-19 and 49).

**The whole point of this file is that it is a list rather than a loop.**
Section 18 requires an archive free of secrets and tokens, and the way to be
sure of that is not to serialize every column and remember to strip a few: it
is to state, for every table, which columns go in and which stay out *and why*.
A column nobody has classified is a bug, and ``test_privacy_export.py`` fails
on one -- it walks the real metadata and asserts that for each table here,
exported plus excluded is exactly the set of columns the table has. A future
PRD adding a column to a table in this file cannot ship until somebody has
decided which side of the line it falls on.

Three kinds of thing are deliberately excluded:

**Secrets.** ``device_token_hash``, ``bootstrap_secret_hash``,
``invite_token_hash``. These are hashes, not plaintext, and they still do not
belong in a file a person can email to themselves -- a hash in an archive is a
hash somebody can attack offline.

**Internal addresses.** ``storage_key``, ``file_storage_key``,
``attachment_key``. These name a path inside Nura's private storage, which is
meaningless outside it and would invite somebody to try requesting it. The
media the keys point at *is* exported, under ``files/``, and the row carries
the archive-relative path instead.

**Other people's identifiers.** ``caregiver_account_id``,
``recipient_account_id``, ``sender_account_id``, ``actor_account_id``. A
caregiver is a person with their own account, and this archive belongs to
somebody else. What goes in is the label the user chose and the side the
message came from -- enough to read the conversation back, without handing over
another account's primary key.

``users.auth_provider_id`` is excluded for the same reason as a token: it is
this account's subject at the identity provider, and an export is not the place
for a credential-adjacent identifier.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableSpec:
    """One table's contribution to the archive."""

    #: The table name, as the metadata knows it.
    table: str
    #: Which archive section the rows land in.
    section: str
    #: The key the rows appear under inside that section's JSON object.
    key: str
    #: Columns written out, in this order.
    exported: tuple[str, ...]
    #: Columns deliberately left out. The docstring above groups the reasons;
    #: this is the audit list the drift test compares against the metadata.
    excluded: tuple[str, ...] = ()
    #: How rows are found. ``profile`` means ``profile_id`` matches; the others
    #: need a join and are spelled out in ``export.py``.
    scope: str = "profile"
    #: Column to sort by, so two exports of unchanged data are byte-identical
    #: (section 18: deterministic).
    order_by: tuple[str, ...] = ("created_at", "id")


#: Columns every table has and every section writes, named once.
_TIMESTAMPS = ("created_at", "updated_at")


SPECS: tuple[TableSpec, ...] = (
    # --- profile.json --------------------------------------------------------
    TableSpec(
        table="users",
        section="profile",
        key="account",
        exported=(
            "id",
            "email",
            "phone",
            "setup_mode",
            "onboarding_status",
            "terms_accepted_at",
            "privacy_acknowledged_at",
            *_TIMESTAMPS,
        ),
        # The subject at the identity provider. See the module docstring.
        excluded=("auth_provider_id",),
        scope="account",
        order_by=("created_at",),
    ),
    TableSpec(
        table="user_settings",
        section="profile",
        key="settings",
        exported=(
            "id",
            "theme",
            "language",
            "larger_text",
            "high_contrast",
            "reduce_motion",
            "voice_first_preference",
            "simplified_interface",
            "daily_checkin_reminder_enabled",
            "daily_checkin_reminder_time",
            "notify_caregiver_messages",
            "notify_suggestion_requests",
            "notify_appointment_suggestions",
            "notify_routine_suggestions",
            "safety_bedtime",
            *_TIMESTAMPS,
        ),
        # Redundant: the account is in the same file.
        excluded=("user_id",),
        scope="account_settings",
        order_by=("created_at",),
    ),
    TableSpec(
        table="profiles",
        section="profile",
        key="profile",
        exported=(
            "id",
            "preferred_name",
            "age_range",
            "country_region",
            "pronouns",
            "avatar_url",
            "blood_type",
            "health_profile_status",
            "health_profile_step",
            *_TIMESTAMPS,
        ),
        scope="self",
        order_by=("created_at",),
    ),
    TableSpec(
        table="account_profile_roles",
        section="profile",
        key="roles",
        exported=("id", "role", *_TIMESTAMPS),
        # Both sides of the link are already in this file.
        excluded=("account_id", "profile_id"),
    ),
    TableSpec(
        table="dashboard_preferences",
        section="profile",
        key="today_cards",
        exported=("id", "card_key", "visible", "position", *_TIMESTAMPS),
        excluded=("profile_id",),
        order_by=("position", "card_key"),
    ),
    TableSpec(
        table="daily_checkins",
        section="profile",
        key="daily_check_ins",
        exported=(
            "id",
            "checkin_date",
            "wellbeing_level",
            "note",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("checkin_date", "id"),
    ),
    # --- health.json ---------------------------------------------------------
    TableSpec(
        table="medical_conditions",
        section="health",
        key="conditions",
        exported=(
            "id",
            "name",
            "status",
            "diagnosed_date",
            "diagnosed_year",
            "diagnosing_clinician",
            "notes",
            "source",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="allergies",
        section="health",
        key="allergies",
        exported=(
            "id",
            "allergen",
            "allergy_type",
            "reaction",
            "severity",
            "notes",
            "source",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="procedures",
        section="health",
        key="procedures",
        exported=(
            "id",
            "name",
            "performed_date",
            "performed_year",
            "hospital",
            "clinician",
            "outcome_notes",
            "notes",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="medical_notes",
        section="health",
        key="notes",
        exported=("id", "title", "body", "category", *_TIMESTAMPS),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="clinicians",
        section="health",
        key="clinicians",
        exported=(
            "id",
            "name",
            "specialty",
            "clinic_name",
            "phone",
            "email",
            "address",
            "notes",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    # --- medications.json ----------------------------------------------------
    TableSpec(
        table="medications",
        section="medications",
        key="medications",
        exported=(
            "id",
            "name",
            "dose",
            "dose_unit",
            "form",
            "frequency_text",
            "instructions",
            "start_date",
            "end_date",
            "prescribing_clinician",
            "reason",
            "is_active",
            "notes",
            "source",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="medication_schedules",
        section="medications",
        key="schedules",
        exported=(
            "id",
            "medication_id",
            "schedule_type",
            "timezone",
            "start_date",
            "end_date",
            "is_active",
            "paused_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="medication_schedule_times",
        section="medications",
        key="schedule_times",
        exported=("id", "schedule_id", "time_of_day", "weekday", *_TIMESTAMPS),
        scope="via_medication_schedule",
        order_by=("schedule_id", "time_of_day", "id"),
    ),
    TableSpec(
        table="medication_doses",
        section="medications",
        key="doses",
        exported=(
            "id",
            "medication_id",
            "schedule_id",
            "scheduled_for",
            "local_date",
            "status",
            "action_at",
            "source",
            "skip_reason_code",
            "skip_reason_text",
            "snoozed_until",
            "snooze_count",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("scheduled_for", "id"),
    ),
    TableSpec(
        table="medication_supply",
        section="medications",
        key="supply",
        exported=(
            "id",
            "medication_id",
            "tracking_enabled",
            "remaining_doses",
            "refill_threshold_doses",
            "last_refill_date",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    # --- symptoms.json -------------------------------------------------------
    TableSpec(
        table="symptom_episodes",
        section="symptoms",
        key="episodes",
        exported=(
            "id",
            "name",
            "body_site",
            "status",
            "first_noticed_at",
            "first_noticed_date",
            "first_noticed_year",
            "first_noticed_text",
            "resolved_at",
            "previous_episode_id",
            "source",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="symptom_entries",
        section="symptoms",
        key="entries",
        exported=(
            "id",
            "symptom_episode_id",
            "recorded_at",
            "main_symptom",
            "site",
            "onset_text",
            "onset_at",
            "onset_date",
            "character",
            "radiation",
            "associated_symptoms",
            "timing",
            "exacerbating_factors",
            "relieving_factors",
            "severity",
            "change_state",
            "free_text_note",
            "negated_items",
            "uncertain_items",
            "context_dependent_items",
            "source",
            "client_entry_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("recorded_at", "id"),
    ),
    TableSpec(
        table="symptom_photos",
        section="symptoms",
        key="photos",
        exported=(
            "id",
            "symptom_entry_id",
            "content_type",
            "byte_size",
            "client_photo_id",
            *_TIMESTAMPS,
        ),
        # The path inside private storage. The bytes are in ``files/`` and the
        # row carries ``archive_path`` instead; see the module docstring.
        excluded=("profile_id", "storage_key"),
    ),
    # --- appointments.json ---------------------------------------------------
    TableSpec(
        table="appointments",
        section="appointments",
        key="appointments",
        exported=(
            "id",
            "clinician_id",
            "title",
            "appointment_type",
            "scheduled_at",
            "timezone",
            "location_name",
            "address",
            "phone",
            "notes",
            "visit_notes",
            "follow_up_date",
            "status",
            "preparation_status",
            "reminders_enabled",
            "cancelled_at",
            "completed_at",
            "client_appointment_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("scheduled_at", "id"),
    ),
    TableSpec(
        table="appointment_questions",
        section="appointments",
        key="questions",
        exported=(
            "id",
            "appointment_id",
            "text",
            "position",
            "is_answered",
            "answer_note",
            "client_question_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("appointment_id", "position", "id"),
    ),
    TableSpec(
        table="appointment_reports",
        section="appointments",
        key="reports",
        exported=(
            "id",
            "appointment_id",
            "version",
            "period_start",
            "period_end",
            "period_preset",
            "include_appendix",
            "selection",
            "snapshot",
            "generated_at",
            "byte_size",
            "page_count",
            "status",
            "client_report_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id", "file_storage_key"),
        order_by=("appointment_id", "version"),
    ),
    # --- assistant.json ------------------------------------------------------
    TableSpec(
        table="assistant_preferences",
        section="assistant",
        key="preferences",
        exported=(
            "id",
            "personality_preset",
            "warmth",
            "humour",
            "talkativeness",
            "proactivity",
            "reminder_firmness",
            "verbosity",
            "voice_id",
            "speaking_speed",
            "assistant_language",
            "custom_instructions",
            "mode",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="assistant_memories",
        section="assistant",
        key="memories",
        exported=(
            "id",
            "category",
            "content",
            "source",
            "is_active",
            "confirmed_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="conversations",
        section="assistant",
        key="conversations",
        exported=(
            "id",
            "title",
            "archived_at",
            "last_message_at",
            "message_count",
            "summary",
            "summary_through_position",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="conversation_messages",
        section="assistant",
        key="messages",
        exported=(
            "id",
            "conversation_id",
            "position",
            "role",
            "message_type",
            "content",
            "source",
            "safety_mode",
            "client_message_id",
            "created_at",
        ),
        # ``meta`` is engineering telemetry -- model name, latency, which tools
        # ran (PRD 8). It is about Nura's machinery rather than about the
        # person, and a model name in a personal archive invites a reader to
        # think the reply was something other than what they read.
        excluded=("meta",),
        scope="via_conversation",
        order_by=("conversation_id", "position"),
    ),
    TableSpec(
        table="assistant_prompt_dismissals",
        section="assistant",
        key="dismissed_prompts",
        exported=("id", "prompt_kind", "subject_key", "dismissed_at"),
        excluded=("profile_id",),
        order_by=("dismissed_at", "id"),
    ),
    # --- caregivers.json -----------------------------------------------------
    TableSpec(
        table="caregiver_relationships",
        section="caregivers",
        key="caregivers",
        exported=(
            "id",
            "role",
            "status",
            "invited_name",
            "invite_email",
            "invite_phone",
            "invite_expires_at",
            "invite_consumed_at",
            "accepted_at",
            "declined_at",
            "revoked_at",
            "notify_messages",
            "notify_appointment_updates",
            "notify_suggestion_outcomes",
            "notify_safety_alerts",
            *_TIMESTAMPS,
        ),
        excluded=(
            "profile_id",
            # A secret, even hashed. See the module docstring.
            "invite_token_hash",
            # Other accounts' primary keys.
            "caregiver_account_id",
            "invited_by_account_id",
        ),
    ),
    TableSpec(
        table="caregiver_permissions",
        section="caregivers",
        key="permissions",
        exported=("id", "relationship_id", "permission_key", "allowed", *_TIMESTAMPS),
        scope="via_relationship",
        order_by=("relationship_id", "permission_key"),
    ),
    TableSpec(
        table="caregiver_suggestions",
        section="caregivers",
        key="suggestions",
        exported=(
            "id",
            "relationship_id",
            "category",
            "action_type",
            "target_resource_type",
            "target_resource_id",
            "payload",
            "status",
            "client_suggestion_id",
            "reviewed_at",
            "decline_note",
            "applied_resource_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id", "reviewed_by_account_id"),
    ),
    TableSpec(
        table="family_threads",
        section="caregivers",
        key="threads",
        exported=(
            "id",
            "relationship_id",
            "message_count",
            "last_message_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="family_messages",
        section="caregivers",
        key="messages",
        exported=(
            "id",
            "thread_id",
            "position",
            "sender_side",
            "message_type",
            "text",
            "check_in_code",
            "client_message_id",
            "created_at",
            "read_at",
        ),
        excluded=(
            # Another account's primary key; ``sender_side`` says who wrote it.
            "sender_account_id",
            # PRD 9 reserved this and never built the upload. Nothing writes
            # it, so there is nothing to export -- and when something does, it
            # is an internal storage path like the other two.
            "attachment_key",
        ),
        scope="via_thread",
        order_by=("thread_id", "position"),
    ),
    TableSpec(
        table="emergency_contacts",
        section="caregivers",
        key="emergency_contacts",
        exported=(
            "id",
            "name",
            "phone",
            "relationship_label",
            "priority",
            "is_active",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id", "account_id"),
        order_by=("priority", "id"),
    ),
    # --- safety.json ---------------------------------------------------------
    TableSpec(
        table="safety_monitoring_sessions",
        section="safety",
        key="monitoring_sessions",
        exported=(
            "id",
            "status",
            "started_at",
            "ends_at",
            "duration_mode",
            "timezone",
            "response_timeout_seconds",
            "second_prompt_enabled",
            "second_prompt_timeout_seconds",
            "source",
            "ended_at",
            "end_reason",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id", "started_by_account_id"),
        order_by=("started_at", "id"),
    ),
    TableSpec(
        table="safety_events",
        section="safety",
        key="events",
        exported=(
            "id",
            "monitoring_session_id",
            "device_id",
            "event_type",
            "trigger_source",
            "triggered_at",
            "status",
            "user_response",
            "response_at",
            "check_started_at",
            "response_deadline_at",
            "second_prompt_at",
            "second_prompt_deadline_at",
            "escalation_started_at",
            "escalation_finished_at",
            "escalation_outcome",
            "escalation_snapshot",
            "resolved_at",
            "resolution",
            "false_positive",
            "false_positive_reason",
            "client_event_id",
            *_TIMESTAMPS,
        ),
        # An idempotency key is a deduplication token for the device route. It
        # is not information about what happened.
        excluded=("profile_id", "idempotency_key"),
        order_by=("triggered_at", "id"),
    ),
    TableSpec(
        table="safety_escalation_attempts",
        section="safety",
        key="escalation_attempts",
        exported=(
            "id",
            "safety_event_id",
            "contact_id",
            "caregiver_relationship_id",
            "recipient_label",
            "priority",
            "channel",
            "status",
            "provider",
            "attempted_at",
            "confirmed_at",
            "failure_code",
            "retry_count",
            *_TIMESTAMPS,
        ),
        # ``recipient_key`` is the deduplication key PRD 10 uses so one worker
        # run cannot contact somebody twice; ``recipient_label`` is the part a
        # person reads.
        excluded=("profile_id", "recipient_key"),
        order_by=("safety_event_id", "priority", "id"),
    ),
    TableSpec(
        table="safety_alerts",
        section="safety",
        key="caregiver_alerts",
        exported=(
            "id",
            "safety_event_id",
            "relationship_id",
            "created_at",
            "read_at",
            "acknowledged_at",
        ),
        excluded=("profile_id", "recipient_account_id"),
        order_by=("created_at", "id"),
    ),
    # --- daily-life.json -----------------------------------------------------
    TableSpec(
        table="tasks",
        section="daily-life",
        key="tasks",
        exported=(
            "id",
            "title",
            "notes",
            "status",
            "priority",
            "due_at",
            "due_local_date",
            "timezone",
            "source",
            "client_task_id",
            "completed_at",
            "archived_at",
            "cancelled_at",
            "content_updated_at",
            "status_changed_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="general_reminders",
        section="daily-life",
        key="reminders",
        exported=(
            "id",
            "title",
            "body",
            "recurrence",
            "timezone",
            "start_date",
            "end_date",
            "time_of_day",
            "weekdays",
            "day_of_month",
            "status",
            "notification_enabled",
            "source",
            "client_reminder_id",
            "paused_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="general_reminder_occurrences",
        section="daily-life",
        key="reminder_occurrences",
        exported=(
            "id",
            "reminder_id",
            "scheduled_for",
            "local_date",
            "status",
            "action_at",
            "snoozed_until",
            "snooze_count",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("scheduled_for", "id"),
    ),
    TableSpec(
        table="alarms",
        section="daily-life",
        key="alarms",
        exported=(
            "id",
            "label",
            "time_of_day",
            "timezone",
            "recurrence",
            "weekdays",
            "on_date",
            "enabled",
            "sound_key",
            "vibration",
            "source",
            "client_alarm_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="routines",
        section="daily-life",
        key="routines",
        exported=(
            "id",
            "title",
            "description",
            "schedule_type",
            "timezone",
            "time_of_day",
            "weekdays",
            "start_date",
            "end_date",
            "status",
            "paused_at",
            "source",
            "client_routine_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    TableSpec(
        table="routine_steps",
        section="daily-life",
        key="routine_steps",
        exported=("id", "routine_id", "title", "position", "optional", *_TIMESTAMPS),
        excluded=("profile_id",),
        order_by=("routine_id", "position"),
    ),
    TableSpec(
        table="routine_runs",
        section="daily-life",
        key="routine_runs",
        exported=(
            "id",
            "routine_id",
            "scheduled_for",
            "local_date",
            "status",
            "started_at",
            "completed_at",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("scheduled_for", "id"),
    ),
    TableSpec(
        table="routine_step_completions",
        section="daily-life",
        key="routine_step_completions",
        exported=(
            "id",
            "run_id",
            "step_id",
            "state",
            "completed_at",
            "client_completion_id",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
        order_by=("run_id", "step_id"),
    ),
    # --- devices.json --------------------------------------------------------
    TableSpec(
        table="devices",
        section="devices",
        key="devices",
        exported=(
            "id",
            "hardware_id",
            "display_name",
            "device_type",
            "firmware_version",
            "provisioning_status",
            "claimed_at",
            "last_seen_at",
            "setup_completed_at",
            "introduction_requested_at",
            "introduced_at",
            *_TIMESTAMPS,
        ),
        excluded=(
            "owner_profile_id",
            "claimed_by_account_id",
            # Two secrets. See the module docstring.
            "bootstrap_secret_hash",
            "device_token_hash",
        ),
        scope="owned_device",
        order_by=("created_at", "id"),
    ),
    TableSpec(
        table="device_capabilities",
        section="devices",
        key="capabilities",
        exported=(
            "id",
            "device_id",
            "capability_key",
            "state",
            "source",
            "reported_at",
            "firmware_version",
            *_TIMESTAMPS,
        ),
        scope="via_device",
        order_by=("device_id", "capability_key"),
    ),
    TableSpec(
        table="device_presentation_preferences",
        section="devices",
        key="presentation_preferences",
        exported=(
            "id",
            "device_id",
            "brightness",
            "volume",
            "reduced_motion",
            "medication_privacy_level",
            "read_medications_aloud",
            "read_messages_aloud",
            "read_assistant_aloud",
            "sleep_screen_mode",
            "face_animation_enabled",
            "family_message_display_enabled",
            "daily_life_privacy_level",
            "daily_life_display_enabled",
            *_TIMESTAMPS,
        ),
        excluded=("profile_id",),
    ),
    #: Presentation history is not exported, and the manifest does not claim
    #: it is: a queued card is Nura's working state rather than something the
    #: person recorded, every one of them was built from data that *is* in the
    #: archive, and a payload is a redacted copy of a row already exported in
    #: full. The row below exists so the drift test still covers the table's
    #: columns -- ``exported`` being empty is the decision, written down.
    TableSpec(
        table="device_presentations",
        section="devices",
        key="presentations",
        exported=(),
        excluded=(
            "id",
            "device_id",
            "profile_id",
            "presentation_type",
            "priority",
            "layout",
            "payload",
            "source",
            "dedupe_key",
            "status",
            "protocol_version",
            "available_at",
            "expires_at",
            "sent_at",
            "acknowledged_at",
            "displayed_at",
            "completed_at",
            "ack_state",
            "failure_code",
            "cancel_reason",
            *_TIMESTAMPS,
        ),
        scope="none",
    ),
    #: Pairing state, likewise. A provisioning session is a single-use token
    #: with an expiry; it is consumed within minutes and says nothing about
    #: the person.
    TableSpec(
        table="provisioning_sessions",
        section="devices",
        key="provisioning_sessions",
        exported=(),
        excluded=(
            "id",
            "account_id",
            "profile_id",
            "hardware_id",
            "token_hash",
            "expires_at",
            "consumed_at",
            "device_id",
            *_TIMESTAMPS,
        ),
        scope="none",
    ),
    #: And the exports themselves. An archive listing previous archives is
    #: noise at best, and each row carries a storage key.
    TableSpec(
        table="data_exports",
        section="profile",
        key="exports",
        exported=(),
        excluded=(
            "id",
            "profile_id",
            "status",
            "requested_at",
            "generated_at",
            "expires_at",
            "file_storage_key",
            "byte_size",
            "file_count",
            "schema_version",
            "categories",
            "failure_reason",
            *_TIMESTAMPS,
        ),
        scope="none",
    ),
)


#: The two audit tables, named so the drift test can prove the omission is
#: deliberate rather than forgotten (section 19's ``excluded_categories``).
AUDIT_TABLES: tuple[str, ...] = ("caregiver_audit_events", "safety_audit_events")

#: Why a category is left out, quoted into the manifest (section 19).
EXCLUSION_REASONS: dict[str, str] = {
    "audit": (
        "Records of who accessed what, kept as the evidence trail for the "
        "access controls themselves. It describes other people's actions as "
        "well as yours, so it is not part of a self-service export."
    ),
}

#: What the manifest says about the archive itself, so a reader is not left
#: inferring it. Truthfulness rules apply here as much as on a screen: an
#: archive that quietly omitted presentation history while claiming to hold
#: "device" data would be overstating itself.
MANIFEST_NOTES: tuple[str, ...] = (
    "This archive holds one profile's data. Nothing in it belongs to another "
    "profile or another account.",
    "Caregivers appear as the name and contact details you entered for them, "
    "never as their own account identifiers.",
    "No access tokens, invitation tokens, device secrets or internal storage "
    "paths are included.",
    "Photos and report documents are under files/, and the row that describes "
    "each one carries its path in this archive.",
    "Nura's own working state is not included: the robot presentation queue, "
    "pairing sessions and previous exports are machinery rather than records "
    "you made.",
)


def exclusion_reason(category: str) -> str:
    """Why one category is absent from the archive."""
    return EXCLUSION_REASONS[category]


#: Tables no export touches, with the reason. Everything in the metadata must
#: appear either here or in ``SPECS``.
UNEXPORTED_TABLES: dict[str, str] = {
    "caregiver_audit_events": (
        "Audit: the access-control evidence trail, about other people's actions."
    ),
    "safety_audit_events": (
        "Audit: the access-control evidence trail, about other people's actions."
    ),
}

_SEEN: set[str] = set()
for _spec in SPECS:
    assert _spec.table not in _SEEN, f"{_spec.table} is specified twice"
    _SEEN.add(_spec.table)

assert set(UNEXPORTED_TABLES) == set(AUDIT_TABLES)
assert not (_SEEN & set(UNEXPORTED_TABLES))


def spec_for(table: str) -> TableSpec:
    """The spec for one table, by name."""
    for spec in SPECS:
        if spec.table == table:
            return spec
    raise KeyError(table)


def specs_for_section(section: str) -> tuple[TableSpec, ...]:
    """Every spec that writes into one archive section, in declaration order."""
    return tuple(spec for spec in SPECS if spec.section == section and spec.exported)


#: Every column any spec excludes, for the test that asserts no secret-looking
#: name is on the exported side anywhere.
def excluded_columns() -> set[str]:
    names: set[str] = set()
    for spec in SPECS:
        names.update(spec.excluded)
    return names
