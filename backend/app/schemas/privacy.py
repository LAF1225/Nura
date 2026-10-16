"""Request and response models for the privacy layer (PRD 13).

The usual drift guards: every ``Literal`` below is asserted against the tuple
the database constrains, so a value set cannot grow in one place and not the
other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    DATA_CATEGORIES,
    DATA_EXPORT_CATEGORIES,
    DATA_EXPORT_SECTIONS,
    DATA_EXPORT_STATUSES,
)

DataCategory = Literal[
    "account",
    "health",
    "assistant",
    "caregiver",
    "safety",
    "productivity",
    "device",
    "media",
    "audit",
]
assert set(DATA_CATEGORIES) == set(DataCategory.__args__)  # type: ignore[attr-defined]

ExportStatus = Literal["requested", "generating", "ready", "failed", "expired"]
#: The same values as a type a caller can narrow to, for the route that
#: substitutes a derived ``expired`` for a stored ``ready``.
ExportStatusValue = ExportStatus
assert set(DATA_EXPORT_STATUSES) == set(ExportStatus.__args__)  # type: ignore[attr-defined]


# --- the hub ----------------------------------------------------------------


class CapabilityLineRead(BaseModel):
    """One capability row.

    ``state`` is the machine value and ``state_label`` the words. Both, because
    a client that had to parse the sentence to colour the row would be making
    copy load-bearing -- and PRD 13 section 9 forbids hard-coded optimistic
    wording, which means the words must be free to change.
    """

    key: str
    label: str
    state: str
    state_label: str


class CaregiverAccessRead(BaseModel):
    """One person with access, as the review screen shows them (section 8)."""

    relationship_id: uuid.UUID
    name: str
    role: str
    #: The categories this person can see. Already the server's answer, so the
    #: screen cannot show a category the server would refuse.
    granted: list[str]
    accepted_at: datetime | None


class ExportRead(BaseModel):
    """One export. Never carries a storage key (section 18)."""

    id: uuid.UUID
    status: ExportStatus
    status_label: str
    requested_at: datetime
    generated_at: datetime | None
    expires_at: datetime | None
    byte_size: int | None
    file_count: int
    schema_version: int
    included_categories: list[str]
    excluded_categories: list[str]
    failure_reason: str | None
    #: Derived, every time it is read (section 26). A client never has to
    #: compare the expiry itself.
    downloadable: bool


class ExportListRead(BaseModel):
    exports: list[ExportRead]
    note: str
    privacy_note: str
    secrets_note: str
    #: What the archive would contain, so the screen can say so before asking.
    sections: list[str]


class PrivacySummaryRead(BaseModel):
    """Everything the Privacy & Security hub shows, in one request."""

    profile_id: uuid.UUID

    assistant_mode: str
    privacy_mode: bool
    privacy_mode_note: str
    privacy_mode_limit: str

    microphone_note: str
    camera_note: str
    photo_permission_note: str
    #: The robot's own input hardware, from what the robot reported. Empty when
    #: no robot is linked -- which is not the same as "off".
    robot_input_capabilities: list[CapabilityLineRead]

    memory_count: int
    active_memory_count: int
    conversation_count: int

    caregivers: list[CaregiverAccessRead]

    safety_monitoring_active: bool
    safety_capabilities: list[CapabilityLineRead]

    robot_linked: bool
    robot_capabilities: list[CapabilityLineRead]
    #: Preview levels as label/value pairs, read from the device's own
    #: preferences (section 10).
    robot_previews: list[list[str]]

    external_capabilities: list[CapabilityLineRead]

    latest_export: ExportRead | None
    export_note: str
    export_privacy_note: str

    deletion_warning: str
    deletion_keeps: str
    deletion_reauth_limitation: str

    data_categories: list[str]
    security_statements: list[str]
    build_honesty_note: str


# --- deletion ---------------------------------------------------------------


class DeletionInventoryRead(BaseModel):
    """What a delete would remove (sections 21 and 22).

    Counted from the database rather than described in prose, so the warning
    cannot claim a scope the service does not have.
    """

    profile_id: uuid.UUID
    profile_name: str
    #: Table name to row count, for the tables that have rows. A screen shows
    #: the total; a developer reading the response sees where it came from.
    rows: dict[str, int]
    row_total: int
    file_count: int
    caregiver_count: int
    device_count: int
    other_profile_count: int

    title: str
    warning: str
    keeps: str
    reauth_limitation: str
    confirm_prompt: str
    #: What ``POST .../delete-confirm`` must receive back, exactly.
    confirmation_phrase: str


class DeletionConfirm(BaseModel):
    """The second step (section 44).

    Both fields are required and neither has a default. A destructive request
    that could be satisfied by an empty body is one a retry could send by
    accident.
    """

    confirmation_phrase: Annotated[str, Field(min_length=1, max_length=64)]
    #: Section 21's explicit confirmation, separate from the phrase so a client
    #: cannot satisfy the whole step by echoing a string it was handed.
    acknowledged: bool


class DeletionResultRead(BaseModel):
    """What was removed (section 23's completion state)."""

    profile_id: uuid.UUID
    rows_deleted: int
    files_deleted: int
    #: Files the row pointed at and storage did not have. Reported rather than
    #: hidden: it means something was already gone, and a privacy feature
    #: should not quietly round that up to success.
    files_missing: int
    caregivers_revoked: int
    devices_unlinked: int
    completed_at: datetime
    other_profiles_remaining: int


class ConversationsDeletedRead(BaseModel):
    """Section 7's bulk delete."""

    deleted: int
    #: Said in the response as well as on the screen, because this is the one
    #: place somebody might fear they have deleted more than they did.
    note: str


assert set(DATA_EXPORT_CATEGORIES) <= set(DataCategory.__args__)  # type: ignore[attr-defined]
assert len(DATA_EXPORT_SECTIONS) == 10
