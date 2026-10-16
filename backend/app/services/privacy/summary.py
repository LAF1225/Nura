"""What the Privacy & Security hub reads (PRD 13, sections 4-10).

**This module adds no settings and owns no state.** Section 109 of PRD 13's
scope rule -- "do not duplicate caregiver, memory, robot, or safety settings" --
is the whole design: every value here is read from the service that already
owns it, and every sentence comes from ``wording.py``. The hub is a reading of
the system, not a second place to configure it.

**It does not import the robot package, and that is deliberate.** PRD 11's
architectural claim is that nothing outside ``services/robot`` reaches into it,
and a test enforces it. So the robot's capability states and preview
preferences arrive as an argument from the route, which is the layer that
already reads them for the Nura Device screen. The privacy hub describes the
robot from what the robot reported; it does not go and ask.

**Every capability line is chosen from a state, never written.** Section 9 and
section 10 both say "no hard-coded optimistic wording" and section 38 lists what
must stay ``not_verified`` and ``not_connected``. A sentence picked from a map
cannot drift from the map; a sentence typed into a screen can.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssistantMemory,
    Conversation,
    DataExport,
)
from app.models.enums import DATA_CATEGORIES
from app.services.assistant import preferences as assistant_preferences
from app.services.caregivers import permissions as permission_service
from app.services.caregivers import relationships as relationship_service
from app.services.privacy import export as export_service
from app.services.privacy import wording
from app.services.productivity import capabilities as daily_life_capabilities
from app.services.safety import capabilities as safety_capabilities
from app.services.safety import monitoring as safety_monitoring
from app.services.safety import wording as safety_wording


@dataclass(frozen=True)
class CapabilityLine:
    """One capability, as a privacy row reads it.

    ``state`` travels with the label so a client can style the row without
    parsing the sentence, which is the mistake that makes copy load-bearing.
    """

    key: str
    label: str
    state: str
    state_label: str


@dataclass(frozen=True)
class CaregiverLine:
    """One person with access, and what they can see."""

    relationship_id: uuid.UUID
    name: str
    role: str
    granted: tuple[str, ...]
    #: Null while an invitation has not been accepted.
    accepted_at: datetime | None


@dataclass(frozen=True)
class PrivacySummary:
    """Everything the hub shows, in one read."""

    profile_id: uuid.UUID
    #: PRD 8's mode, read not set.
    assistant_mode: str
    privacy_mode: bool
    privacy_mode_note: str
    privacy_mode_limit: str
    #: Section 6. Two sentences about the phone and the robot's own hardware.
    microphone_note: str
    camera_note: str
    photo_permission_note: str
    robot_input_capabilities: tuple[CapabilityLine, ...]
    #: Section 7.
    memory_count: int
    active_memory_count: int
    conversation_count: int
    #: Section 8.
    caregivers: tuple[CaregiverLine, ...]
    #: Section 9, from PRD 10's own map.
    safety_monitoring_active: bool
    safety_capabilities: tuple[CapabilityLine, ...]
    #: Section 10, from PRD 11's own map, handed in by the route.
    robot_linked: bool
    robot_capabilities: tuple[CapabilityLine, ...]
    robot_previews: tuple[tuple[str, str], ...]
    #: PRD 12's three external capabilities, which are the ones a person is
    #: most likely to assume are live.
    external_capabilities: tuple[CapabilityLine, ...]
    #: Sections 17 and 21.
    latest_export: DataExport | None
    export_note: str
    export_privacy_note: str
    deletion_warning: str
    deletion_keeps: str
    deletion_reauth_limitation: str
    #: Section 11's categories, so the screen can list what Nura stores.
    data_categories: tuple[str, ...]
    security_statements: tuple[str, ...]
    build_honesty_note: str


def build_summary(
    db: Session,
    profile_id: uuid.UUID,
    now: datetime,
    *,
    robot_capabilities: tuple[CapabilityLine, ...],
    robot_previews: tuple[tuple[str, str], ...],
    robot_linked: bool,
) -> PrivacySummary:
    """Assembles the hub.

    The robot arguments come from the route. See the module docstring.
    """
    preferences = assistant_preferences.get_or_create(db, profile_id)
    privacy_mode = preferences.mode == "privacy"

    memories = (
        db.execute(
            select(AssistantMemory.is_active).where(
                AssistantMemory.profile_id == profile_id
            )
        )
        .scalars()
        .all()
    )
    conversation_count = len(
        db.execute(
            select(Conversation.id).where(Conversation.profile_id == profile_id)
        ).all()
    )

    relationships = relationship_service.list_relationships(db, profile_id)
    caregivers = tuple(
        CaregiverLine(
            relationship_id=relationship.id,
            name=relationship.invited_name,
            role=relationship.role,
            granted=tuple(sorted(permission_service.granted_keys(relationship))),
            accepted_at=relationship.accepted_at,
        )
        for relationship in relationships
        if relationship.status == "active"
    )

    session = safety_monitoring.peek_session(db, profile_id, now)

    safety_lines = tuple(
        CapabilityLine(
            key=capability.key,
            label=safety_wording.CAPABILITY_LABELS[capability.key],
            state=capability.state,
            state_label=safety_wording.CAPABILITY_STATE_LABELS[capability.state],
        )
        for capability in safety_capabilities.capabilities()
    )

    external_lines = tuple(
        CapabilityLine(
            key=capability.key,
            label=capability.label,
            state=capability.state,
            # PRD 12's capability carries a whole sentence rather than a short
            # label, and a sentence is what this row wants: "not configured"
            # beside "Weather" invites the question this answers.
            state_label=capability.sentence,
        )
        for capability in daily_life_capabilities.capabilities()
        if capability.key in daily_life_capabilities.EXTERNAL_CAPABILITY_KEYS
    )

    latest = db.execute(
        select(DataExport)
        .where(DataExport.profile_id == profile_id)
        .order_by(DataExport.requested_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if (
        latest is not None
        and latest.status == "ready"
        and export_service.is_expired(latest, now)
    ):
        # Expiry is derived on read, as everywhere else. The row is not written
        # here -- a GET that changed a status would make the hub load-bearing
        # for a rule the download route already enforces.
        latest = None

    return PrivacySummary(
        profile_id=profile_id,
        assistant_mode=preferences.mode,
        privacy_mode=privacy_mode,
        privacy_mode_note=(
            wording.PRIVACY_MODE_ON if privacy_mode else wording.PRIVACY_MODE_OFF
        ),
        privacy_mode_limit=wording.PRIVACY_MODE_LIMIT,
        microphone_note=wording.NO_MICROPHONE_FEATURE,
        camera_note=wording.NO_CAMERA_FEATURE,
        photo_permission_note=wording.PHOTO_PERMISSION_NOTE,
        robot_input_capabilities=tuple(
            line
            for line in robot_capabilities
            if line.key in ("microphone", "camera", "speaker")
        ),
        memory_count=len(memories),
        active_memory_count=sum(1 for active in memories if active),
        conversation_count=conversation_count,
        caregivers=caregivers,
        safety_monitoring_active=session is not None,
        safety_capabilities=safety_lines,
        robot_linked=robot_linked,
        robot_capabilities=robot_capabilities,
        robot_previews=robot_previews,
        external_capabilities=external_lines,
        latest_export=latest,
        export_note=wording.EXPORT_NOTE,
        export_privacy_note=wording.EXPORT_PRIVACY_NOTE,
        deletion_warning=wording.DELETION_WARNING,
        deletion_keeps=wording.DELETION_KEEPS,
        deletion_reauth_limitation=wording.DELETION_REAUTH_LIMITATION,
        data_categories=DATA_CATEGORIES,
        security_statements=wording.SECURITY_STATEMENTS,
        build_honesty_note=wording.BUILD_HONESTY_NOTE,
    )


def delete_all_conversations(db: Session, profile_id: uuid.UUID) -> int:
    """Section 7's bulk delete, and nothing more than it says.

    One service, as section 7 allows. It removes conversations and -- through
    the cascade PRD 8 already declared -- their messages. It touches no
    memory, no health record and no task: section 7 is explicit that deleting
    conversations must not take anything else with it, and the test asserts
    the counts either side.
    """
    conversations = (
        db.execute(select(Conversation).where(Conversation.profile_id == profile_id))
        .scalars()
        .all()
    )
    for conversation in conversations:
        db.delete(conversation)
    if conversations:
        db.commit()
    return len(conversations)
