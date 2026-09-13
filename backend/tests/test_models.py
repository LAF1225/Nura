"""Model definition tests (PRD 0 section 16; PRD 1 sections 32-34).

Checks the schema is what the PRDs specify, and -- just as importantly -- that
nothing from a later PRD has crept in. Reads metadata only, so no database is
required.
"""

from app.db.base import Base
from app.models import (
    AccountProfileRole,
    Device,
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
        "created_at",
        "updated_at",
    }


def test_profile_holds_no_medical_information() -> None:
    """PRD 1, section 50: none of this belongs in PRD 1."""
    columns = set(Profile.__table__.columns.keys())
    assert columns == {
        "id",
        "preferred_name",
        "age_range",
        "country_region",
        "pronouns",
        "avatar_url",
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
