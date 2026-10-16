"""Model definition tests (PRD 0 section 16; PRD 1 sections 32-34).

Checks the schema is what the PRDs specify, and -- just as importantly -- that
nothing from a later PRD has crept in. Reads metadata only, so no database is
required.
"""

import inspect

from app.db.base import Base
from app.models import (
    AccountProfileRole,
    Allergy,
    Appointment,
    AppointmentQuestion,
    AppointmentReport,
    AssistantMemory,
    AssistantPreferences,
    AssistantPromptDismissal,
    CaregiverAuditEvent,
    CaregiverRelationship,
    Clinician,
    Conversation,
    ConversationMessage,
    DailyCheckIn,
    DashboardPreference,
    Device,
    EmergencyContact,
    FamilyMessage,
    MedicalCondition,
    MedicalNote,
    Medication,
    Procedure,
    Profile,
    ProvisioningSession,
    SafetyAlert,
    SafetyEscalationAttempt,
    SafetyEvent,
    SafetyMonitoringSession,
    User,
    UserSettings,
)
from app.models.enums import (
    CAREGIVER_AUDIT_EVENT_TYPES,
    CAREGIVER_PERMISSION_KEYS,
    CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE,
    CAREGIVER_SUGGESTION_ACTION_TYPES,
    FAMILY_CHECK_IN_CODES_FROM_CAREGIVER,
    FAMILY_CHECK_IN_CODES_FROM_USER,
    FAMILY_MESSAGE_TYPES,
    FAMILY_MESSAGE_TYPES_ALLOWED,
    PROFILE_ROLES,
    ROBOT_CAPABILITY_KEYS,
    ROBOT_CAPABILITY_STATES,
    ROBOT_PRESENTATION_PRIORITIES,
    ROBOT_PRESENTATION_PRIORITY_BANDS,
    ROBOT_PRESENTATION_TYPES,
    ROBOT_SAFETY_PRIORITY_CEILING,
    SAFETY_AUDIT_EVENT_TYPES,
    SAFETY_ESCALATION_CHANNELS,
    SAFETY_ESCALATION_CHANNELS_AVAILABLE,
    SAFETY_EVENT_TYPES,
    SAFETY_EVENT_TYPES_REQUIRING_MONITORING,
)
from app.models.robot import (
    DeviceCapability,
    DevicePresentation,
    DevicePresentationPreferences,
)
from app.services.robot import capabilities as robot_capabilities
from app.services.robot import preferences as robot_preferences


def test_table_set_matches_the_prds() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "user_settings",
        "devices",
        "profiles",
        "account_profile_roles",
        "provisioning_sessions",
        "daily_checkins",
        "dashboard_preferences",
        "medical_conditions",
        "medications",
        "allergies",
        "clinicians",
        "procedures",
        "medical_notes",
        "medication_schedules",
        "medication_schedule_times",
        "medication_doses",
        "medication_supply",
        "symptom_episodes",
        "symptom_entries",
        "symptom_photos",
        "appointments",
        "appointment_questions",
        "appointment_reports",
        "conversations",
        "conversation_messages",
        "assistant_memories",
        "assistant_preferences",
        "assistant_prompt_dismissals",
        "caregiver_relationships",
        "caregiver_permissions",
        "caregiver_suggestions",
        "family_threads",
        "family_messages",
        "emergency_contacts",
        "caregiver_audit_events",
        "safety_monitoring_sessions",
        "safety_events",
        "safety_escalation_attempts",
        "safety_alerts",
        "safety_audit_events",
        "device_presentations",
        "device_presentation_preferences",
        "device_capabilities",
        # PRD 12
        "tasks",
        "general_reminders",
        "general_reminder_occurrences",
        "alarms",
        "routines",
        "routine_steps",
        "routine_runs",
        "routine_step_completions",
        # PRD 13. One table for the whole stage, which is the point of it:
        # export needs a row because it has a file and an expiry, and deletion
        # needs none because it is synchronous.
        "data_exports",
    }


def test_account_columns() -> None:
    assert set(User.__table__.columns.keys()) == {
        "id",
        "auth_provider_id",
        "email",
        "phone",
        "setup_mode",
        "onboarding_status",
        "terms_accepted_at",
        "privacy_acknowledged_at",
        "created_at",
        "updated_at",
    }


def test_settings_columns_include_accessibility_preferences() -> None:
    assert set(UserSettings.__table__.columns.keys()) == {
        "id",
        "user_id",
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
        "created_at",
        "updated_at",
    }


def test_profile_holds_only_the_health_values_that_are_single_answers() -> None:
    """PRD 4, sections 15 and 18.

    A profile carries the three health values that are *one answer about the
    person* -- their blood type and where they got to in setup. Everything
    people keep a list of belongs in its own table, so this guards against the
    profile quietly becoming the medical record.
    """
    columns = set(Profile.__table__.columns.keys())
    assert columns == {
        "id",
        "preferred_name",
        "age_range",
        "country_region",
        "pronouns",
        "avatar_url",
        "blood_type",
        "health_profile_status",
        "health_profile_step",
        "created_at",
        "updated_at",
    }
    forbidden = {
        "diagnosis",
        "diagnoses",
        "medication",
        "medications",
        "symptoms",
        "allergies",
        "insurance",
        "doctor",
    }
    assert columns & forbidden == set()


def test_account_profile_role_is_a_join_with_only_two_roles() -> None:
    assert set(AccountProfileRole.__table__.columns.keys()) == {
        "id",
        "account_id",
        "profile_id",
        "role",
        "created_at",
        "updated_at",
    }
    # No permission columns yet -- caregiver permissions are a later PRD.
    assert "permissions" not in AccountProfileRole.__table__.columns


def test_device_identity_is_the_uuid_not_the_hardware_id() -> None:
    """PRD 0, section 17: the internal UUID is the identity."""
    primary_key = [column.name for column in Device.__table__.primary_key.columns]
    assert primary_key == ["id"]
    assert Device.__table__.columns["hardware_id"].index is True
    assert Device.__table__.columns["hardware_id"].unique is True


def test_device_credentials_are_stored_only_as_hashes() -> None:
    """PRD 2, section 55: no plaintext token or secret columns."""
    columns = set(Device.__table__.columns.keys())
    assert {"bootstrap_secret_hash", "device_token_hash"} <= columns
    assert not {"device_token", "bootstrap_secret", "wifi_password", "ssid"} & columns

    session_columns = set(ProvisioningSession.__table__.columns.keys())
    assert "token_hash" in session_columns
    assert "token" not in session_columns


def test_device_tables_hold_no_medical_information() -> None:
    """PRD 2, section 56: provisioning needs no medical data."""
    forbidden = {
        "diagnosis",
        "medication",
        "medications",
        "symptoms",
        "emergency_contact",
    }
    for model in (Device, ProvisioningSession):
        assert set(model.__table__.columns.keys()) & forbidden == set()


def test_daily_checkin_is_a_wellbeing_answer_not_a_symptom_record() -> None:
    """PRD 3, sections 10 and 61: three levels and a note, nothing more."""
    columns = set(DailyCheckIn.__table__.columns.keys())
    assert columns == {
        "id",
        "profile_id",
        "checkin_date",
        "wellbeing_level",
        "note",
        "created_at",
        "updated_at",
    }
    forbidden = {
        "severity",
        "symptom",
        "symptoms",
        "pain_score",
        "diagnosis",
        "medication",
        "photo_url",
        "temperature",
    }
    assert columns & forbidden == set()


def test_a_check_in_belongs_to_a_profile_not_an_account() -> None:
    """The record is about the person Nura is for, not whoever submitted it."""
    assert "profile_id" in DailyCheckIn.__table__.columns
    assert "user_id" not in DailyCheckIn.__table__.columns
    assert "account_id" not in DailyCheckIn.__table__.columns


def test_only_one_check_in_can_exist_per_profile_per_day() -> None:
    """PRD 3, section 11, enforced by the database rather than by the API."""
    constraints = {
        tuple(column.name for column in constraint.columns)
        for constraint in DailyCheckIn.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("profile_id", "checkin_date") in constraints


def test_dashboard_preference_is_one_row_per_card() -> None:
    assert set(DashboardPreference.__table__.columns.keys()) == {
        "id",
        "profile_id",
        "card_key",
        "visible",
        "position",
        "created_at",
        "updated_at",
    }


def test_every_health_record_belongs_to_a_profile() -> None:
    """PRD 4, section 8: never to the account that typed it in."""
    for model in (
        MedicalCondition,
        Medication,
        Allergy,
        Clinician,
        Procedure,
        MedicalNote,
    ):
        columns = set(model.__table__.columns.keys())
        assert "profile_id" in columns, model.__tablename__
        assert "user_id" not in columns, model.__tablename__
        assert "account_id" not in columns, model.__tablename__
        # Every one cascades with the profile, so removing a person removes
        # their record rather than orphaning it.
        foreign_key = next(iter(model.__table__.columns["profile_id"].foreign_keys))
        assert foreign_key.ondelete == "CASCADE", model.__tablename__


def test_approximate_dates_keep_their_precision() -> None:
    """PRD 4, section 31: a year is a year, not the 1st of January."""
    assert {"diagnosed_date", "diagnosed_year"} <= set(
        MedicalCondition.__table__.columns.keys()
    )
    assert {"performed_date", "performed_year"} <= set(Procedure.__table__.columns.keys())

    for model, prefix in ((MedicalCondition, "diagnosed"), (Procedure, "performed")):
        checks = {
            constraint.name
            for constraint in model.__table__.constraints
            if constraint.__class__.__name__ == "CheckConstraint"
        }
        assert f"ck_{model.__tablename__}_{prefix}_precision" in checks


def test_medication_records_carry_no_schedule() -> None:
    """PRD 4, sections 10 and 56: PRD 4 stores records, PRD 5 makes them act."""
    columns = set(Medication.__table__.columns.keys())
    forbidden = {
        "reminder_time",
        "reminder_times",
        "schedule",
        "taken_at",
        "adherence",
        "refill_date",
        "snoozed_until",
    }
    assert columns & forbidden == set()


def test_records_that_can_be_imported_later_record_where_they_came_from() -> None:
    """PRD 4, section 32."""
    for model in (MedicalCondition, Medication, Allergy):
        assert "source" in model.__table__.columns, model.__tablename__


def test_an_appointment_carries_its_own_time_zone() -> None:
    """PRD 7, section 42. An instant alone cannot say "3:30 PM in London"."""
    columns = set(Appointment.__table__.columns.keys())
    assert {"scheduled_at", "timezone"} <= columns


def test_an_appointment_has_no_calendar_sync_fields() -> None:
    """PRD 7, section 4: entry is manual, and nothing here implies otherwise."""
    columns = set(Appointment.__table__.columns.keys())
    forbidden = {
        "external_id",
        "calendar_id",
        "ical_uid",
        "sync_token",
        "provider",
        "last_synced_at",
    }
    assert columns & forbidden == set()


def test_a_status_implies_its_timestamp() -> None:
    """PRD 7, section 7. The two can never disagree."""
    checks = {
        constraint.name
        for constraint in Appointment.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_appointments_cancelled_at" in checks
    assert "ck_appointments_completed_at" in checks


def test_a_question_keeps_the_users_words_and_their_order() -> None:
    """PRD 7, sections 22, 23 and 39."""
    columns = set(AppointmentQuestion.__table__.columns.keys())
    assert {"text", "position", "is_answered", "answer_note"} <= columns
    # Nothing that would let a suggestion be treated differently from a typed
    # question: once accepted, it is theirs (PRD 7, section 24).
    assert "is_suggested" not in columns
    assert "suggestion_key" not in columns


def test_a_report_stores_its_own_content() -> None:
    """PRD 7, section 30: a snapshot, not a query re-run on every read."""
    columns = set(AppointmentReport.__table__.columns.keys())
    assert {"selection", "snapshot", "version", "generated_at"} <= columns
    assert {"period_start", "period_end", "period_preset"} <= columns


def test_a_report_that_says_it_is_ready_has_a_file() -> None:
    checks = {
        constraint.name
        for constraint in AppointmentReport.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }
    assert "ck_appointment_reports_ready_file" in checks
    assert "ck_appointment_reports_version" in checks
    assert "ck_appointment_reports_period" in checks


def test_appointment_tables_have_no_caregiver_or_clinician_access() -> None:
    """PRD 7, sections 55 and 56: no cross-account access exists yet."""
    for model in (Appointment, AppointmentQuestion, AppointmentReport):
        columns = set(model.__table__.columns.keys())
        forbidden = {
            "shared_with_account_id",
            "caregiver_id",
            "clinician_account_id",
            "share_token",
            "public_url",
            "is_public",
        }
        assert columns & forbidden == set(), model.__tablename__


# --- the assistant (PRD 8) --------------------------------------------------


def test_a_conversation_is_a_thread_with_an_end() -> None:
    """PRD 8, section 8: not one endless permanent thread."""
    columns = set(Conversation.__table__.columns.keys())
    assert {"title", "archived_at", "last_message_at", "message_count"} <= columns


def test_a_message_is_not_edited() -> None:
    """PRD 8, section 7. A thread is a record of what was said.

    No ``updated_at``: correcting something means saying the next thing,
    which is how a conversation works and how this stays an accurate account
    of one. ``position`` is what makes the order a stored fact rather than a
    tie-break on timestamps that can collide.
    """
    columns = set(ConversationMessage.__table__.columns.keys())
    assert "updated_at" not in columns
    assert "edited_at" not in columns
    assert {"position", "role", "message_type", "source", "safety_mode"} <= columns


def test_assistant_memory_is_a_preference_and_not_a_health_record() -> None:
    """PRD 8, sections 40 and 45.

    There is nowhere here to put a condition, a medication or a symptom --
    which is the most reliable way of not copying one in. Health data stays
    in the tables built for it, where it is dated, editable and exportable.
    """
    columns = set(AssistantMemory.__table__.columns.keys())
    assert {"category", "content", "source", "is_active", "confirmed_at"} <= columns
    forbidden = {
        "condition_id",
        "medication_id",
        "symptom_episode_id",
        "appointment_id",
        "health_record_id",
        "diagnosis",
        "severity",
    }
    assert columns & forbidden == set()


def test_memory_categories_contain_nothing_clinical() -> None:
    """PRD 8, section 41. A "health" category would invite section 45's mistake."""
    from app.models.enums import ASSISTANT_MEMORY_CATEGORIES

    for category in ASSISTANT_MEMORY_CATEGORIES:
        assert category not in ("health", "medical", "conditions", "medications")


def test_a_memory_was_always_agreed_to() -> None:
    """PRD 8, sections 42 and 46: no path saves one quietly."""
    from app.models.enums import ASSISTANT_MEMORY_SOURCES

    assert set(ASSISTANT_MEMORY_SOURCES) == {"user", "conversation"}


def test_assistant_preferences_cannot_choose_a_model() -> None:
    """PRD 8, section 76: provider, model and key are server-side only."""
    columns = set(AssistantPreferences.__table__.columns.keys())
    forbidden = {
        "model",
        "ai_model",
        "provider",
        "api_key",
        "temperature",
        "system_prompt",
    }
    assert columns & forbidden == set()


def test_serious_mode_is_not_a_stored_setting() -> None:
    """PRD 8, sections 37 and 69.

    Seriousness is a property of a moment, not of a person: it is derived per
    message and recorded on the message. A user who could switch it on could
    switch it off.
    """
    from app.models.enums import ASSISTANT_MODES

    assert "serious" not in ASSISTANT_MODES
    assert "emergency" not in ASSISTANT_MODES
    assert set(ConversationMessage.__table__.columns.keys()) >= {"safety_mode"}


def test_assistant_tables_have_no_caregiver_or_sharing_columns() -> None:
    """PRD 8, sections 60 and 107: no hidden caregiver sharing exists yet."""
    for model in (
        Conversation,
        ConversationMessage,
        AssistantMemory,
        AssistantPreferences,
        AssistantPromptDismissal,
    ):
        columns = set(model.__table__.columns.keys())
        forbidden = {
            "shared_with_account_id",
            "caregiver_id",
            "share_token",
            "public_url",
            "is_public",
            "visible_to_caregivers",
        }
        assert columns & forbidden == set(), model.__tablename__


def test_no_assistant_table_references_a_health_record() -> None:
    """PRD 8, section 61: deleting a conversation must reach nothing else.

    Checked structurally rather than by trying it: if there is no foreign key
    out of these tables into the record, no cascade can be added by accident.
    """
    health_tables = {
        "medical_conditions",
        "medications",
        "allergies",
        "procedures",
        "medical_notes",
        "symptom_episodes",
        "symptom_entries",
        "medication_doses",
        "appointments",
    }
    for model in (
        Conversation,
        ConversationMessage,
        AssistantMemory,
        AssistantPreferences,
        AssistantPromptDismissal,
    ):
        referenced = {key.column.table.name for key in model.__table__.foreign_keys}
        assert referenced & health_tables == set(), model.__tablename__


# --- PRD 9: caregivers, family messaging and emergency contacts -------------


def test_a_caregiver_is_not_an_account_profile_role() -> None:
    """The single most important shape in PRD 9.

    ``account_profile_roles`` is what ``deps.get_owned_profile`` walks, and every
    profile-scoped route from PRD 0-8 authorizes through it. A ``caregiver`` role
    here would have granted the complete health record, every symptom photo and
    every doctor report without changing one route. The caregiver path is a
    separate table with its own per-category permissions.
    """
    assert set(PROFILE_ROLES) == {"self", "setup_helper"}
    assert "caregiver" not in PROFILE_ROLES


def test_no_caregiver_table_points_into_the_health_record() -> None:
    """PRD 9's tables reach profiles and each other, and nothing else.

    What this rules out: a suggestion holding a medication id, a thread holding
    an appointment id, an audit row holding a condition id. A suggestion names
    its target as a type plus an id and the service resolves it inside the
    profile at approval time, which is what makes "verify the target still
    exists" (section 24) a real check rather than a trusted reference.
    """
    caregiver_tables = {
        "caregiver_relationships",
        "caregiver_permissions",
        "caregiver_suggestions",
        "family_threads",
        "family_messages",
        "emergency_contacts",
        "caregiver_audit_events",
    }
    allowed_targets = caregiver_tables | {"profiles", "users"}
    for name in caregiver_tables:
        table = Base.metadata.tables[name]
        for key in table.foreign_keys:
            assert key.column.table.name in allowed_targets, (
                f"{name}.{key.parent.name} points at {key.column.table.name}"
            )


def test_no_caregiver_table_has_a_global_permission_flag() -> None:
    """Section 7 forbids one "caregiver can see everything" boolean.

    Checked by absence: no column on any PRD 9 table is named in a way that
    could act as one. Permissions are rows in ``caregiver_permissions``, one
    category at a time.
    """
    forbidden = {
        "can_view_all",
        "full_access",
        "is_admin",
        "all_permissions",
        "see_everything",
        "can_view_everything",
    }
    for name in (
        "caregiver_relationships",
        "caregiver_permissions",
        "caregiver_suggestions",
    ):
        columns = set(Base.metadata.tables[name].columns.keys())
        assert not columns & forbidden


def test_a_relationship_keeps_the_invitation_rather_than_a_second_table() -> None:
    """Section 79 allows it, and it removes a class of bug.

    Accepting is a status change, so there is no second row to keep in step, and
    "accept twice" is idempotent because the token is already consumed.
    """
    assert "caregiver_invitations" not in Base.metadata.tables
    columns = set(CaregiverRelationship.__table__.columns.keys())
    assert {"invite_token_hash", "invite_expires_at", "invite_consumed_at"} <= columns


def test_an_invitation_token_is_only_ever_stored_hashed() -> None:
    """Section 13. A database dump must contain no usable invitation."""
    columns = set(CaregiverRelationship.__table__.columns.keys())
    assert "invite_token" not in columns
    assert "invite_token_hash" in columns
    assert CaregiverRelationship.__table__.c.invite_token_hash.unique is True


def test_a_forbidden_suggestion_action_cannot_be_stored() -> None:
    """Section 85, enforced by the vocabulary rather than by validation.

    ``change_medication_dose``, ``delete_condition`` and ``change_diagnosis``
    are not refused by a check somewhere -- there is no action type for them, so
    the CHECK constraint built from this tuple rejects the row.
    """
    for forbidden in (
        "change_medication_dose",
        "delete_condition",
        "change_diagnosis",
    ):
        assert forbidden not in CAREGIVER_SUGGESTION_ACTION_TYPES


def test_a_family_message_is_never_edited() -> None:
    """No ``updated_at``, the same as an assistant message.

    A sent message is not revised; ``read_at`` is the only thing that changes
    after it is written.
    """
    columns = set(FamilyMessage.__table__.columns.keys())
    assert "updated_at" not in columns
    assert "read_at" in columns


def test_an_audit_row_is_never_edited() -> None:
    """An audit row that can be changed is not an audit row (section 50)."""
    assert "updated_at" not in set(CaregiverAuditEvent.__table__.columns.keys())


def test_the_audit_vocabulary_records_no_read() -> None:
    """Sections 49 and 50: auditability without surveillance.

    There is no event type for *viewing* anything. A care app that logs every
    glance is the experience section 2 rules out, and the trail is more useful
    for being only about changes.
    """
    for event in CAREGIVER_AUDIT_EVENT_TYPES:
        for reading in ("view", "read", "opened", "accessed"):
            assert reading not in event


def test_an_emergency_contact_has_no_verification_column() -> None:
    """Section 46 recommends verification *if the infrastructure exists*.

    Nothing in this system can send a code to a phone, so a column that could
    only ever read "unverified" would be a worse answer than its absence.
    """
    columns = set(EmergencyContact.__table__.columns.keys())
    assert "is_verified" not in columns
    assert "verified_at" not in columns


def test_a_photo_message_cannot_be_sent_yet() -> None:
    """Section 33 makes attachments optional, and the upload route does not exist.

    ``photo`` stays in the stored vocabulary so the column and the constraint are
    already right when it is built -- the same approach PRD 6 took to future
    symptom sources -- and is absent from what a client may send.
    """
    assert "photo" in FAMILY_MESSAGE_TYPES
    assert "photo" not in FAMILY_MESSAGE_TYPES_ALLOWED


def test_the_two_check_in_lists_are_different_gestures() -> None:
    """Sections 35 and 36. The person says how they are; the caregiver asks."""
    assert not set(FAMILY_CHECK_IN_CODES_FROM_USER) & set(
        FAMILY_CHECK_IN_CODES_FROM_CAREGIVER
    )
    assert "im_okay" in FAMILY_CHECK_IN_CODES_FROM_USER
    assert "how_are_you" in FAMILY_CHECK_IN_CODES_FROM_CAREGIVER


def test_a_caregiver_relationship_cannot_be_active_without_an_account() -> None:
    """Stated as a constraint rather than trusted to every future writer.

    A pending invitation deliberately has no account: section 14 allows a
    caregiver who has not signed up yet.
    """
    names = {
        constraint.name
        for constraint in CaregiverRelationship.__table__.constraints
        if constraint.name
    }
    assert "ck_caregiver_relationships_active_has_account" in names


# --- safety monitoring and SOS (PRD 10) --------------------------------------


def test_no_safety_table_points_at_the_health_record() -> None:
    """PRD 10, sections 90 and 92.

    Safety data is about what happened and who was tried. It is not a second
    route into somebody's medical history, and the surest way to be certain is
    that no foreign key from any of these five tables can reach one.
    """
    safety_tables = {
        "safety_monitoring_sessions",
        "safety_events",
        "safety_escalation_attempts",
        "safety_alerts",
        "safety_audit_events",
    }
    allowed_targets = safety_tables | {
        "profiles",
        "users",
        "devices",
        "emergency_contacts",
        "caregiver_relationships",
    }
    for name in safety_tables:
        table = Base.metadata.tables[name]
        for key in table.foreign_keys:
            assert key.column.table.name in allowed_targets, (
                f"{name}.{key.parent.name} points at {key.column.table.name}"
            )


def test_a_safety_event_stores_no_media_and_no_confidence() -> None:
    """PRD 10, sections 54, 92 and 117.

    No video, no audio, no image -- section 92 says future detectors should
    emit events rather than continuous raw media, and there is nowhere here to
    put any.

    And no ``confidence``. Section 54 calls it engineering metadata rather than
    a diagnosis probability; a column is a thing a screen eventually reads, and
    a number next to "possible seizure-like activity" would read as exactly the
    medical claim section 52 forbids.
    """
    columns = set(SafetyEvent.__table__.columns.keys())
    for forbidden in (
        "confidence",
        "video_url",
        "audio_url",
        "image_url",
        "media_key",
        "recording_key",
        "severity",
        "diagnosis",
    ):
        assert forbidden not in columns, forbidden


def test_every_sensor_observed_event_type_says_possible() -> None:
    """PRD 10, sections 16 and 52, at the vocabulary rather than the screen."""
    for event_type in SAFETY_EVENT_TYPES_REQUIRING_MONITORING:
        assert event_type.startswith("possible_"), event_type
    for forbidden in ("fall", "seizure", "vomiting", "unconscious"):
        assert forbidden not in SAFETY_EVENT_TYPES, forbidden


def test_only_one_monitoring_session_can_be_active() -> None:
    """A partial unique index, so a person is monitored once at a time.

    Partial on ``status = 'active'``, so every past session keeps its history
    and somebody can be monitored again tomorrow.
    """
    indexes = {index.name: index for index in SafetyMonitoringSession.__table__.indexes}
    index = indexes["uq_safety_monitoring_sessions_active"]
    assert index.unique
    assert index.dialect_options["postgresql"]["where"] == "status = 'active'"


def test_a_monitoring_session_cannot_be_active_and_ended() -> None:
    """The state a monitoring system must never be able to reach."""
    names = {
        constraint.name
        for constraint in SafetyMonitoringSession.__table__.constraints
        if constraint.name
    }
    assert "ck_safety_monitoring_sessions_ended" in names
    assert "ck_safety_monitoring_sessions_ends_at" in names


def test_a_resolved_event_always_says_how_it_ended() -> None:
    """PRD 10, section 127: no event may sit finished with no account of it."""
    names = {
        constraint.name
        for constraint in SafetyEvent.__table__.constraints
        if constraint.name
    }
    assert "ck_safety_events_resolved" in names


def test_escalation_is_unique_per_recipient_and_channel() -> None:
    """PRD 10, section 75.

    A single text ``recipient_key`` rather than three nullable foreign keys,
    because PostgreSQL treats NULLs as distinct: a unique constraint over
    nullable columns would never collide, and a duplicated worker run would
    contact somebody twice.
    """
    names = {
        constraint.name
        for constraint in SafetyEscalationAttempt.__table__.constraints
        if constraint.name
    }
    assert "uq_safety_escalation_attempt_recipient" in names
    assert "recipient_key" in SafetyEscalationAttempt.__table__.columns
    assert not SafetyEscalationAttempt.__table__.columns["recipient_key"].nullable


def test_one_alert_per_caregiver_per_event() -> None:
    """PRD 10, section 75, for the one artefact a caregiver can open."""
    names = {
        constraint.name
        for constraint in SafetyAlert.__table__.constraints
        if constraint.name
    }
    assert "uq_safety_alert_recipient" in names


def test_the_safety_audit_records_no_views() -> None:
    """PRD 10, sections 89 and 90, and PRD 9's rule carried forward.

    ``alert_acknowledged`` is in the vocabulary because a caregiver saying
    "I'm checking on them" is an action somebody may need to account for.
    Nothing records a *view*: there is no event for opening the safety
    history, for the same reason PRD 9 has none for opening a medication list.
    """
    for event_type in SAFETY_AUDIT_EVENT_TYPES:
        for forbidden in ("view", "opened", "accessed", "looked"):
            assert forbidden not in event_type, event_type


def test_only_the_in_app_channel_is_available() -> None:
    """PRD 10, sections 34 and 35.

    The capability map is built from this tuple, so "only report a channel as
    available when a real provider exists" is a property of the vocabulary
    rather than of a screen. Three of the four channels exist in the schema
    and in no deployment.
    """
    assert SAFETY_ESCALATION_CHANNELS_AVAILABLE == ("in_app",)
    assert set(SAFETY_ESCALATION_CHANNELS_AVAILABLE) < set(SAFETY_ESCALATION_CHANNELS)


def test_routines_left_the_permissions_without_a_source() -> None:
    """PRD 12 builds the source ``routines`` was reserved for.

    PRD 9 section 94 allowed a permission key to exist before its data did and
    warned against fabricating one; PRD 10 did this for ``safety_alerts`` and
    PRD 12 does it for ``routines``. The tuple is now empty, and an empty
    tuple is the honest statement that every granted permission unlocks
    something.

    It is not deleted. The next PRD that reserves a key before its data exists
    puts it here, and ``CareScope.usable`` keeps working.
    """
    assert CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE == ()
    # Both keys that ever sat in this tuple are still grantable, which is the
    # half that was never in doubt: a permission with no data behind it was
    # always stored faithfully, and the screens said so.
    assert "routines" in CAREGIVER_PERMISSION_KEYS
    assert "safety_alerts" in CAREGIVER_PERMISSION_KEYS
    # And the rule that holds whatever is in the tuple.
    assert set(CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE) <= set(CAREGIVER_PERMISSION_KEYS)


# --- PRD 11: the robot's presentation tables ---------------------------------


def test_a_presentation_cannot_claim_a_display_nobody_acknowledged() -> None:
    """PRD 11, sections 14 and 141, in the schema rather than in a service.

    The most important constraint PRD 11 adds. The backend handing a command
    to a robot is not the robot showing it, and with this constraint there is
    no code path -- now or in a later release -- that can mark a presentation
    displayed without a device having said it rendered it.

    The parenthesised half of the condition matters more than it looks: a SQL
    CHECK is satisfied when it evaluates to TRUE *or null*, and
    ``ack_state IN (...)`` is null when ``ack_state`` is -- which is precisely
    the row this constraint exists to refuse. Written the short way, it
    accepted it, and a test that writes past the service is what caught that.
    """
    constraint = next(
        candidate
        for candidate in DevicePresentation.__table__.constraints
        if candidate.name == "ck_device_presentations_displayed"
    )
    text = str(constraint.sqltext)
    assert "ack_state IS NOT NULL" in text
    assert "render_started" in text and "render_completed" in text


def test_a_withdrawn_presentation_says_why_and_a_failed_one_says_what() -> None:
    """PRD 11, section 13, and the reason there are two columns.

    ``cancel_reason`` and ``failure_code`` are separate for the same reason
    PRD 10 keeps an event's status apart from how its escalation went: "the
    dose was taken" and "the renderer broke" are different facts, and one
    column would have blurred them within a release.
    """
    names = {
        constraint.name
        for constraint in DevicePresentation.__table__.constraints
        if constraint.name
    }
    assert "ck_device_presentations_cancelled" in names
    assert "ck_device_presentations_failed" in names
    columns = DevicePresentation.__table__.columns
    assert columns["cancel_reason"].nullable
    assert columns["failure_code"].nullable


def test_a_duplicate_build_cannot_make_a_second_open_card() -> None:
    """PRD 11, section 57.

    Partial over the four open statuses, so a retried build folds into the
    card that is already waiting while tomorrow's dose still gets its own.
    """
    index = next(
        candidate
        for candidate in DevicePresentation.__table__.indexes
        if candidate.name == "uq_device_presentations_dedupe"
    )
    assert index.unique
    assert [column.name for column in index.columns] == ["device_id", "dedupe_key"]
    where = index.dialect_options["postgresql"]["where"]
    for status in ("queued", "sent", "acknowledged", "displayed"):
        assert status in where


def test_a_presentation_holds_no_health_foreign_key() -> None:
    """PRD 11, sections 51 to 54: the robot is additive.

    A medication reminder row holds a copy of what the robot should draw; the
    dose is still the record. There is no foreign key from a presentation into
    a dose, an appointment or a message -- only a ``dedupe_key`` naming the
    thing it came from -- so a card can be expired, cancelled or never shown
    without any effect on the health data it was built from.
    """
    targets = {key.column.table.name for key in DevicePresentation.__table__.foreign_keys}
    assert targets == {"devices", "profiles"}


def test_a_presentation_payload_holds_no_media() -> None:
    """PRD 11, sections 108 and 110.

    One JSONB column holding a validated envelope -- a layout name from a
    closed set and a handful of short strings. No URL column, no attachment
    key, no blob, and nothing that would need local storage on the device.
    """
    columns = set(DevicePresentation.__table__.columns.keys())
    for forbidden in ("url", "image", "media", "attachment", "blob", "asset"):
        assert not any(forbidden in name for name in columns), forbidden


def test_reduced_motion_has_three_states() -> None:
    """PRD 11, sections 30 and 105.

    Null means *follow the account's accessibility preference*; true and false
    are deliberate overrides. A plain boolean would have had to pick a value
    and would then have stopped following that preference the first time
    anybody opened the screen.
    """
    column = DevicePresentationPreferences.__table__.columns["reduced_motion"]
    assert column.nullable
    assert column.server_default is None


def test_the_conservative_defaults_are_the_ones_in_the_schema() -> None:
    """PRD 11, section 104, checked against the columns rather than the prose.

    A reminder on a screen other people can see starts private, all three
    read-aloud switches start off, and the sleep screen dims.
    """
    columns = DevicePresentationPreferences.__table__.columns
    assert columns["medication_privacy_level"].server_default.arg == "private"
    assert columns["sleep_screen_mode"].server_default.arg == "dim"
    for name in (
        "read_medications_aloud",
        "read_messages_aloud",
        "read_assistant_aloud",
    ):
        assert columns[name].server_default.arg == "false", name
    assert columns["face_animation_enabled"].server_default.arg == "true"
    # And the service's copy of the same defaults agrees, because the service
    # is what creates the row for a robot claimed by an older build.
    assert robot_preferences.DEFAULTS["medication_privacy_level"] == "private"
    assert robot_preferences.DEFAULTS["reduced_motion"] is None
    assert robot_preferences.DEFAULTS["read_messages_aloud"] is False


def test_a_capability_is_one_row_per_key_with_its_own_timestamp() -> None:
    """PRD 11, sections 11, 119 and 124.

    Section 119 invites a decision on where capabilities live, and this is it.
    ``reported_at`` being per capability is what makes "the screen was proven
    last Tuesday and the speaker has never been tested" representable, which
    is section 124's stale-report case.
    """
    names = {
        constraint.name
        for constraint in DeviceCapability.__table__.constraints
        if constraint.name
    }
    assert "uq_device_capabilities_key" in names
    columns = DeviceCapability.__table__.columns
    assert not columns["reported_at"].nullable
    assert "firmware_version" in columns


def test_the_backend_cannot_write_not_verified_by_itself() -> None:
    """PRD 11, sections 12 and 91.

    ``not_verified`` means "the driver is there and nothing has been proven",
    which is a statement about a build. The backend has never seen a build, so
    the only writer is a device report -- and the state a missing row reads as
    is ``not_connected``.
    """
    assert robot_capabilities.UNREPORTED_STATE == "not_connected"
    assert "not_verified" in ROBOT_CAPABILITY_STATES
    source = inspect.getsource(robot_capabilities)
    # The only places the string appears are the downgrade of a stale
    # ``available`` and the documentation of why.
    assert source.count('"not_verified"') == 1


def test_every_presentation_type_is_ranked_exactly_once() -> None:
    """PRD 11, section 16.

    Checked against the tuple rather than by trying the queue: a type added
    without a rank would make selection depend on insertion order, which is
    the kind of bug that only shows up when two things are queued in the same
    second.
    """
    ranked = [name for name, _ in ROBOT_PRESENTATION_PRIORITIES]
    assert sorted(ranked) == sorted(ROBOT_PRESENTATION_TYPES)
    assert len(ranked) == len(set(ranked))
    assert set(ROBOT_PRESENTATION_PRIORITY_BANDS) == {
        rank for _, rank in ROBOT_PRESENTATION_PRIORITIES
    }


def test_nothing_to_do_with_safety_can_be_outranked() -> None:
    """PRD 11, sections 16, 17 and 72.

    Personality and assistant output cannot override safety state, and this is
    where that stops being a promise: every safety type ranks at or above the
    ceiling the preemption rule uses, and nothing else does.
    """
    ranks = dict(ROBOT_PRESENTATION_PRIORITIES)
    for safety_type in ("emergency_status", "safety_check", "safety_status"):
        assert ranks[safety_type] <= ROBOT_SAFETY_PRIORITY_CEILING
    for other, rank in ranks.items():
        if other not in ("emergency_status", "safety_check", "safety_status"):
            assert rank > ROBOT_SAFETY_PRIORITY_CEILING, other


def test_every_sensor_capability_is_named_for_the_part_and_not_the_promise() -> None:
    """PRD 11, section 10, and PRD 10's rule carried forward.

    There is no ``fall_detection`` capability and no ``monitoring`` capability.
    ``camera_detection`` is as close as the vocabulary gets, and it is about a
    camera reporting events rather than about anything being detected
    reliably -- PRD 10 section 117 forbids claiming a validated detector and
    PRD 11 does not add one.
    """
    for key in ROBOT_CAPABILITY_KEYS:
        for forbidden in ("fall", "seizure", "vomit", "monitoring", "health"):
            assert forbidden not in key, key
