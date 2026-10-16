"""The Nura assistant API (PRD 8, sections 89, 90, 97 and 105).

Every route hangs off ``/profiles/{profile_id}/assistant`` and depends on
``OwnedProfile``, so the authorization chain is the one the health record,
medication, symptom and appointment routes already use: a profile is
reachable only through the signed-in account's own join row, and one that
exists but belongs to someone else is answered with 404.

That single dependency is also what section 90 asks for. The tools Nura runs
take their profile from the resolved object, not from anything in a request
body and not from anything a model produced -- so "the model must never
choose a profile" is enforced by there being no route, and no argument,
through which it could.

Thin on purpose. Authorization, validation and serialisation happen here;
everything else is ``services.assistant``, because section 9 asks for a
dedicated service boundary and a route that reaches past it is how that
boundary stops being one.
"""

import uuid
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, Now, OwnedProfile, http_error
from app.core.config import get_settings
from app.models import Conversation, ConversationMessage, Profile
from app.schemas.assistant import (
    ActionConfirmed,
    AssistantHomeRead,
    ConfirmAction,
    ConversationCreate,
    ConversationDetailRead,
    ConversationListRead,
    ConversationRead,
    ConversationUpdate,
    MemoryCreate,
    MemoryListRead,
    MemoryRead,
    MemorySuggestionRead,
    MemoryUpdate,
    MessageCreate,
    MessageRead,
    MessageSent,
    PendingActionRead,
    PreferencesRead,
    PreferencesUpdate,
    ProactivePromptRead,
    PromptDismiss,
    meta_from,
)
from app.schemas.productivity import CapabilityRead, ExternalCapabilitiesRead
from app.services import checkins as checkin_service
from app.services.assistant import conversations as conversation_service
from app.services.assistant import limits, memory, preferences, proactivity
from app.services.assistant import service as assistant_service
from app.services.errors import DomainError
from app.services.productivity import capabilities as daily_life_capabilities
from app.services.productivity import providers as daily_life_providers

router = APIRouter(prefix="/profiles/{profile_id}/assistant", tags=["assistant"])

#: How many threads the Nura tab lists without asking for more.
HOME_CONVERSATIONS = 5

LocalDateQuery = Annotated[
    date | None,
    Query(description="The date on the client's own clock, as YYYY-MM-DD."),
]


def _local_date(value: date | None, now: datetime) -> date:
    """The user's own day, validated the same way check-ins validate it."""
    try:
        return checkin_service.validate_local_date(value or now.date(), now)
    except DomainError as error:
        raise http_error(error) from error


def _preferences_read(db: Session, profile: Profile) -> PreferencesRead:
    row = preferences.get_or_create(db, profile.id)
    return PreferencesRead(
        profile_id=profile.id,
        personality_preset=row.personality_preset,  # type: ignore[arg-type]
        warmth=row.warmth,  # type: ignore[arg-type]
        humour=row.humour,  # type: ignore[arg-type]
        talkativeness=row.talkativeness,  # type: ignore[arg-type]
        proactivity=row.proactivity,  # type: ignore[arg-type]
        reminder_firmness=row.reminder_firmness,  # type: ignore[arg-type]
        verbosity=row.verbosity,  # type: ignore[arg-type]
        voice_id=row.voice_id,  # type: ignore[arg-type]
        speaking_speed=row.speaking_speed,  # type: ignore[arg-type]
        assistant_language=row.assistant_language,
        custom_instructions=row.custom_instructions,
        mode=row.mode,  # type: ignore[arg-type]
        matches_preset=preferences.matches_preset(row),
    )


def _message_read(message: ConversationMessage) -> MessageRead:
    """One message, with only the metadata the API is willing to show."""
    raw = (message.meta or {}).get(assistant_service.PENDING_KEY)
    pending = (
        PendingActionRead(
            tool=str(raw.get("tool", "")),
            summary=str(raw.get("summary", "")),
            state=raw.get("state", "pending"),
        )
        if isinstance(raw, dict)
        else None
    )
    return MessageRead(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        message_type=message.message_type,  # type: ignore[arg-type]
        content=message.content,
        created_at=message.created_at,
        safety_mode=message.safety_mode,  # type: ignore[arg-type]
        meta=meta_from(message.meta),
        pending_action=pending,
    )


def _conversation(
    db: Session, profile: Profile, conversation_id: uuid.UUID
) -> Conversation:
    try:
        return conversation_service.get_conversation(db, profile.id, conversation_id)
    except DomainError as error:
        raise http_error(error) from error


# --- the Nura tab -----------------------------------------------------------


@router.get("/home", response_model=AssistantHomeRead)
def read_home(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    local_date: LocalDateQuery = None,
) -> AssistantHomeRead:
    """Everything the Nura tab shows, in one request (PRD 8, section 5)."""
    settings = get_settings()
    on_date = _local_date(local_date, now)
    row = preferences.get_or_create(db, profile.id)
    prompts = proactivity.build(
        db,
        profile.id,
        local_date=on_date,
        now=now,
        level=row.proactivity,
        mode=row.mode,
    )
    recent = conversation_service.list_conversations(db, profile.id)
    return AssistantHomeRead(
        profile_id=profile.id,
        assistant_available=settings.assistant_configured,
        preferences=_preferences_read(db, profile),
        recent_conversations=[
            ConversationRead.model_validate(row) for row in recent[:HOME_CONVERSATIONS]
        ],
        prompts=[
            ProactivePromptRead(
                kind=prompt.kind,  # type: ignore[arg-type]
                subject_key=prompt.subject_key,
                text=prompt.text,
                route=prompt.route,
                action_label=prompt.action_label,
            )
            for prompt in prompts
        ],
        memory_count=len(memory.list_memories(db, profile.id, active_only=True)),
    )


@router.post("/prompts/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_prompt(
    payload: PromptDismiss, profile: OwnedProfile, db: DbSession, now: Now
) -> Response:
    """Stops one proactive prompt coming back (PRD 8, section 36)."""
    proactivity.dismiss(
        db,
        profile.id,
        kind=payload.kind,
        subject_key=payload.subject_key,
        now=now,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- external capabilities (PRD 12, sections 25-29, 57 and 83) --------------


@router.get("/external-capabilities", response_model=ExternalCapabilitiesRead)
def read_external_capabilities(
    profile: OwnedProfile,
) -> ExternalCapabilitiesRead:
    """What Nura can actually reach (PRD 12, section 57).

    On the assistant router rather than on its own, because it is the
    assistant's question: section 29's map is what the system prompt is built
    from, and this endpoint is the same map so a screen and a model cannot
    disagree about what this build can do.

    **Every external key reads ``not_configured`` in every deployment**, and it
    is derived -- ``services.productivity.providers`` is asked whether a
    provider is both named and implemented, and none is. Section 83's
    checkpoint has one honest answer and this is where it comes from, not a
    constant somebody could edit.
    """
    rows = daily_life_capabilities.capabilities()
    return ExternalCapabilitiesRead(
        profile_id=profile.id,
        capabilities=[
            CapabilityRead(
                key=row.key,  # type: ignore[arg-type]
                state=row.state,  # type: ignore[arg-type]
                label=row.label,
                sentence=row.sentence,
            )
            for row in rows
        ],
        external=daily_life_capabilities.external_states(),  # type: ignore[arg-type]
        any_external_configured=daily_life_providers.any_external_configured(),
    )


# --- preferences ------------------------------------------------------------


@router.get("/preferences", response_model=PreferencesRead)
def read_preferences(profile: OwnedProfile, db: DbSession) -> PreferencesRead:
    """How Nura is set to sound. Created with the defaults on first read."""
    return _preferences_read(db, profile)


@router.patch("/preferences", response_model=PreferencesRead)
def update_preferences(
    payload: PreferencesUpdate, profile: OwnedProfile, db: DbSession
) -> PreferencesRead:
    """Changes what was sent and leaves the rest (PRD 8, sections 22-34).

    A custom instruction that tries to switch off the medical boundary is
    refused with ``unsafe_instruction`` rather than quietly ignored
    (section 26).
    """
    row = preferences.get_or_create(db, profile.id)
    changes = payload.model_dump(exclude_unset=True)
    try:
        preferences.update(db, row, changes)
    except DomainError as error:
        raise http_error(error) from error
    return _preferences_read(db, profile)


# --- memory -----------------------------------------------------------------


@router.get("/memories", response_model=MemoryListRead)
def list_memories(profile: OwnedProfile, db: DbSession) -> MemoryListRead:
    """What Nura remembers (PRD 8, section 43)."""
    return MemoryListRead(
        profile_id=profile.id,
        memories=[
            MemoryRead.model_validate(row) for row in memory.list_memories(db, profile.id)
        ],
        max_memories=memory.MAX_MEMORIES,
    )


@router.post("/memories", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
def create_memory(
    payload: MemoryCreate, profile: OwnedProfile, db: DbSession, now: Now
) -> MemoryRead:
    """Saves something the user agreed to (PRD 8, sections 42 and 46)."""
    try:
        row = memory.create_memory(
            db,
            profile.id,
            category=payload.category,
            content=payload.content,
            source=payload.source,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return MemoryRead.model_validate(row)


@router.patch("/memories/{memory_id}", response_model=MemoryRead)
def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> MemoryRead:
    """Edits one memory, or switches it off (PRD 8, sections 43 and 47)."""
    try:
        row = memory.get_memory(db, profile.id, memory_id)
        updated = memory.update_memory(
            db,
            row,
            content=payload.content,
            category=payload.category,
            is_active=payload.is_active,
        )
    except DomainError as error:
        raise http_error(error) from error
    return MemoryRead.model_validate(updated)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> Response:
    """Forgets one thing (PRD 8, section 47).

    Nothing else goes with it. Removing "call me Baba" does not touch the
    profile, the name on it, or any health record.
    """
    try:
        memory.delete_memory(db, memory.get_memory(db, profile.id, memory_id))
    except DomainError as error:
        raise http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- conversations ----------------------------------------------------------


@router.get("/conversations", response_model=ConversationListRead)
def list_conversations(
    profile: OwnedProfile,
    db: DbSession,
    include_archived: Annotated[bool, Query()] = False,
) -> ConversationListRead:
    """Threads, most recently spoken in first (PRD 8, section 8)."""
    rows = conversation_service.list_conversations(
        db, profile.id, include_archived=include_archived
    )
    return ConversationListRead(
        profile_id=profile.id,
        conversations=[ConversationRead.model_validate(row) for row in rows],
        assistant_available=get_settings().assistant_configured,
    )


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate, profile: OwnedProfile, db: DbSession
) -> ConversationRead:
    """Starts a thread (PRD 8, section 8)."""
    try:
        row = conversation_service.create_conversation(
            db, profile.id, title=payload.title
        )
    except DomainError as error:
        raise http_error(error) from error
    return ConversationRead.model_validate(row)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailRead)
def read_conversation(
    conversation_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> ConversationDetailRead:
    """One thread and what was said in it.

    System and tool rows are not here. They are stored, because a thread
    nobody can replay is not a record of anything, and they never leave the
    server (PRD 8, section 7).
    """
    conversation = _conversation(db, profile, conversation_id)
    return ConversationDetailRead(
        conversation=ConversationRead.model_validate(conversation),
        messages=[
            _message_read(message)
            for message in conversation_service.visible_messages(db, conversation.id)
        ],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> ConversationRead:
    """Renames or archives a thread (PRD 8, section 8)."""
    conversation = _conversation(db, profile, conversation_id)
    if payload.title is not None:
        conversation_service.rename_conversation(db, conversation, payload.title)
    if payload.archived is not None:
        conversation_service.set_archived(
            db, conversation, archived=payload.archived, now=now
        )
    return ConversationRead.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> Response:
    """Deletes a thread and its messages, and nothing else (section 61)."""
    conversation_service.delete_conversation(
        db, _conversation(db, profile, conversation_id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- talking ----------------------------------------------------------------


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageSent,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
    local_date: LocalDateQuery = None,
) -> MessageSent:
    """Sends a message and returns what came back.

    A provider failure is a 201 with ``reply`` null and a ``failure`` code,
    not a 5xx: the user's message *was* recorded, the app has something to
    show and a Retry to offer, and a thread that ends in an unanswered
    question is an accurate account of what happened (PRD 8, sections 55 and
    56). The one refusal that is a real error status is the rate limit,
    which is a 429 because the request was not accepted at all.
    """
    conversation = _conversation(db, profile, conversation_id)
    on_date = _local_date(local_date, now)
    service = assistant_service.get_service()
    try:
        result = service.send(
            db,
            profile,
            conversation,
            user=user,
            text=payload.content,
            now=now,
            local_date=on_date,
            client_message_id=payload.client_message_id,
        )
    except limits.RateLimitedError as error:
        raise http_error(error) from error
    except DomainError as error:
        raise http_error(error) from error

    suggestion = result.memory_suggestion
    return MessageSent(
        conversation=ConversationRead.model_validate(result.conversation),
        user_message=_message_read(result.user_message),
        reply=None if result.reply is None else _message_read(result.reply),
        failure=result.failure,
        failure_message=result.failure_message,
        memory_suggestion=(
            None
            if suggestion is None
            else MemorySuggestionRead(
                category=suggestion.category,  # type: ignore[arg-type]
                content=suggestion.content,
            )
        ),
        suggest_symptom_log=result.suggest_symptom_log,
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/confirm",
    response_model=ActionConfirmed,
)
def confirm_action(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ConfirmAction,
    profile: OwnedProfile,
    user: CurrentUser,
    db: DbSession,
    now: Now,
    local_date: LocalDateQuery = None,
) -> ActionConfirmed:
    """Carries out, or cancels, a change Nura offered (PRD 8, section 14).

    This is the only path by which anything Nura suggested becomes a change.
    The model does not reach it: a person pressing Confirm does.
    """
    conversation = _conversation(db, profile, conversation_id)
    message = next(
        (
            row
            for row in conversation_service.all_messages(db, conversation.id)
            if row.id == message_id
        ),
        None,
    )
    if message is None:
        raise http_error(
            conversation_service.ConversationNotFoundError(
                "That message could not be found."
            )
        )

    on_date = _local_date(local_date, now)
    service = assistant_service.get_service()
    try:
        outcome = service.confirm_pending_action(
            db,
            profile,
            message,
            user=user,
            confirmed=payload.confirmed,
            now=now,
            local_date=on_date,
        )
    except DomainError as error:
        raise http_error(error) from error

    return ActionConfirmed(
        message=_message_read(message),
        outcome=None if outcome is None else _message_read(outcome),
    )
