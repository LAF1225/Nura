"""Model definition tests (PRD 0 section 16; PRD 1 sections 32-34).

Checks the schema is what the PRDs specify, and -- just as importantly -- that
nothing from a later PRD has crept in. Reads metadata only, so no database is
required.
"""

from app.db.base import Base
from app.models import (
    AccountProfileRole,
    Allergy,
    Clinician,
    DailyCheckIn,
    DashboardPreference,
    Device,
    MedicalCondition,
    MedicalNote,
    Medication,
    Procedure,
    Profile,
    ProvisioningSession,
    User,
    UserSettings,
)


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
