"""Model definition tests (PRD 0, section 16).

Checks the foundational schema is what the PRD specifies, and -- just as
importantly -- that nothing from a later PRD has crept in. Reads metadata only,
so no database is required.
"""

from app.db.base import Base
from app.models import Device, User, UserSettings


def test_only_foundational_tables_are_defined() -> None:
    assert set(Base.metadata.tables) == {"users", "user_settings", "devices"}


def test_user_columns_match_the_prd() -> None:
    columns = set(User.__table__.columns.keys())
    assert columns == {
        "id",
        "auth_provider_id",
        "email",
        "phone",
        "created_at",
        "updated_at",
    }


def test_user_settings_columns_match_the_prd() -> None:
    columns = set(UserSettings.__table__.columns.keys())
    assert columns == {
        "id",
        "user_id",
        "theme",
        "language",
        "created_at",
        "updated_at",
    }


def test_device_columns_match_the_prd() -> None:
    columns = set(Device.__table__.columns.keys())
    assert columns == {
        "id",
        "owner_user_id",
        "device_identifier",
        "display_name",
        "device_type",
        "firmware_version",
        "last_seen_at",
        "created_at",
        "updated_at",
    }


def test_device_identity_is_the_uuid_not_the_hardware_id() -> None:
    """PRD 0, section 17: the internal UUID is the identity."""
    primary_key = [column.name for column in Device.__table__.primary_key.columns]
    assert primary_key == ["id"]
    # The hardware-provisioned id is unique, but it is not the key.
    assert Device.__table__.columns["device_identifier"].index is True
