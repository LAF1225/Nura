"""Assistant request/response models (PRD 8, sections 7, 88, 89 and 105).

Four things a reader should check for and find.

**No message response carries a system or tool row.** The read path filters on
role before it reaches here, and ``MessageRead`` has no field a system prompt
or a raw tool result could be put in even by mistake (section 7).

**No response carries a prompt, a provider name a user could act on, or a
chain of thought.** ``MessageMeta`` is the metadata section 80 allows --
model, latency, which tools ran, which safety mode applied -- and stops
there.

**No request names a profile except in the path.** The profile comes from
``OwnedProfile``, resolved from the signed-in account, and no body below has
a profile field for a client to disagree with it (section 90).

**No request chooses a model, a provider or a prompt.** Section 76 puts all
of that server-side; a client that could pick the model could pick a cheaper
one with different safety behaviour.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.assistant import (
    CONVERSATION_TITLE_MAX_LENGTH,
    CUSTOM_INSTRUCTIONS_MAX_LENGTH,
    MEMORY_MAX_LENGTH,
    MESSAGE_MAX_LENGTH,
    PROMPT_SUBJECT_MAX_LENGTH,
)
from app.models.enums import (
    ASSISTANT_MEMORY_CATEGORIES,
    ASSISTANT_MEMORY_SOURCES,
    ASSISTANT_MODES,
    ASSISTANT_PROMPT_KINDS,
    ASSISTANT_VOICES,
    CONVERSATION_MESSAGE_SOURCES_ALLOWED,
    CONVERSATION_MESSAGE_TYPES,
    CONVERSATION_VISIBLE_ROLES,
    PERSONALITY_LEVELS,
    PERSONALITY_PRESETS,
    PROACTIVITY_LEVELS,
    SAFETY_MODES,
    SPEAKING_SPEEDS,
    VERBOSITY_LEVELS,
)
from app.models.symptom import CLIENT_ID_MAX_LENGTH

MemoryCategory = Literal[
    "preferences",
    "communication",
    "routine",
    "personal_context",
    "assistant_behavior",
]
MemorySource = Literal["user", "conversation"]
PersonalityPreset = Literal["gentle", "friendly", "focused", "professional"]
PersonalityLevel = Literal["low", "medium", "high"]
ProactivityLevel = Literal["off", "low", "medium", "high"]
Verbosity = Literal["concise", "balanced", "detailed"]
SpeakingSpeed = Literal["slow", "normal", "fast"]
AssistantVoice = Literal["calm", "clear", "warm", "bright"]
AssistantMode = Literal["normal", "focus", "sleep", "privacy"]
SafetyMode = Literal["normal", "serious", "emergency_unconfigured", "emergency_active"]
MessageRole = Literal["user", "assistant"]
MessageType = Literal["text", "tool_call", "tool_result", "notice"]
MessageSource = Literal["mobile_text"]
PromptKind = Literal["appointment_preparation", "daily_checkin", "medication_supply"]

# Same guard as everywhere else: a Literal that drifts from the tuple the
# database CHECK constraints are built from is a startup failure, not a
# request Postgres rejects at three in the morning.
assert set(ASSISTANT_MEMORY_CATEGORIES) == set(MemoryCategory.__args__)  # type: ignore[attr-defined]
assert set(ASSISTANT_MEMORY_SOURCES) == set(MemorySource.__args__)  # type: ignore[attr-defined]
assert set(PERSONALITY_PRESETS) == set(PersonalityPreset.__args__)  # type: ignore[attr-defined]
assert set(PERSONALITY_LEVELS) == set(PersonalityLevel.__args__)  # type: ignore[attr-defined]
assert set(PROACTIVITY_LEVELS) == set(ProactivityLevel.__args__)  # type: ignore[attr-defined]
assert set(VERBOSITY_LEVELS) == set(Verbosity.__args__)  # type: ignore[attr-defined]
assert set(SPEAKING_SPEEDS) == set(SpeakingSpeed.__args__)  # type: ignore[attr-defined]
assert set(ASSISTANT_VOICES) == set(AssistantVoice.__args__)  # type: ignore[attr-defined]
assert set(ASSISTANT_MODES) == set(AssistantMode.__args__)  # type: ignore[attr-defined]
assert set(SAFETY_MODES) == set(SafetyMode.__args__)  # type: ignore[attr-defined]
assert set(CONVERSATION_VISIBLE_ROLES) == set(MessageRole.__args__)  # type: ignore[attr-defined]
assert set(CONVERSATION_MESSAGE_TYPES) == set(MessageType.__args__)  # type: ignore[attr-defined]
assert set(CONVERSATION_MESSAGE_SOURCES_ALLOWED) == set(MessageSource.__args__)  # type: ignore[attr-defined]
assert set(ASSISTANT_PROMPT_KINDS) == set(PromptKind.__args__)  # type: ignore[attr-defined]

MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX_LENGTH),
]
MemoryText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MEMORY_MAX_LENGTH),
]
TitleText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CONVERSATION_TITLE_MAX_LENGTH
    ),
]
InstructionsText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=CUSTOM_INSTRUCTIONS_MAX_LENGTH),
]
ClientId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=CLIENT_ID_MAX_LENGTH
    ),
]


# --- preferences ------------------------------------------------------------


class PreferencesRead(BaseModel):
    """Everything the Personality, Voice and Proactivity screens show."""

    model_config = ConfigDict(from_attributes=True)

    profile_id: uuid.UUID
    personality_preset: PersonalityPreset
    warmth: PersonalityLevel
    humour: PersonalityLevel
    talkativeness: PersonalityLevel
    proactivity: ProactivityLevel
    reminder_firmness: PersonalityLevel
    verbosity: Verbosity
    voice_id: AssistantVoice
    speaking_speed: SpeakingSpeed
    assistant_language: str
    custom_instructions: str | None
    mode: AssistantMode
    #: False once a dial has been moved away from the stored preset, so the
    #: screen can show "Gentle (adjusted)" rather than claiming a preset the
    #: settings have left behind.
    matches_preset: bool
    #: Whether any voice can actually speak yet. False in PRD 8: the settings
    #: are stored for the future rather than pretending to do something now
    #: (section 27).
    voice_playback_available: bool = False


class PreferencesUpdate(BaseModel):
    """A partial change. Anything omitted is left alone."""

    model_config = ConfigDict(extra="forbid")

    personality_preset: PersonalityPreset | None = None
    warmth: PersonalityLevel | None = None
    humour: PersonalityLevel | None = None
    talkativeness: PersonalityLevel | None = None
    proactivity: ProactivityLevel | None = None
    reminder_firmness: PersonalityLevel | None = None
    verbosity: Verbosity | None = None
    voice_id: AssistantVoice | None = None
    speaking_speed: SpeakingSpeed | None = None
    #: Only ``en`` is implemented. Section 31 asks for the architecture to
    #: support more rather than for translation to be faked, so the field is
    #: here and the value set is not yet open.
    assistant_language: Literal["en"] | None = None
    custom_instructions: InstructionsText | None = None
    mode: AssistantMode | None = None


# --- memory -----------------------------------------------------------------


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: MemoryCategory
    content: str
    source: MemorySource
    is_active: bool
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory = "preferences"
    content: MemoryText
    #: ``conversation`` is what the app sends when the user presses Remember
    #: on a suggestion. Either way a person agreed (section 46).
    source: MemorySource = "user"


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: MemoryCategory | None = None
    content: MemoryText | None = None
    is_active: bool | None = None


class MemoryListRead(BaseModel):
    profile_id: uuid.UUID
    memories: list[MemoryRead]
    max_memories: int


# --- conversations ----------------------------------------------------------


class MessageMeta(BaseModel):
    """The metadata section 80 allows, and nothing beyond it."""

    model: str | None = None
    latency_ms: int | None = None
    tools: list[str] = Field(default_factory=list)
    safety_mode: SafetyMode = "normal"
    prompt_version: int | None = None
    #: True when the reply hit the output ceiling, so the app can offer to
    #: continue rather than leaving a sentence half-finished.
    truncated: bool = False


class PendingActionRead(BaseModel):
    """A change Nura has offered to make (section 14)."""

    tool: str
    summary: str
    state: Literal["pending", "confirmed", "cancelled"] = "pending"


class MessageRead(BaseModel):
    id: uuid.UUID
    role: MessageRole
    message_type: MessageType
    content: str
    created_at: datetime
    safety_mode: SafetyMode
    meta: MessageMeta = Field(default_factory=MessageMeta)
    pending_action: PendingActionRead | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None
    archived_at: datetime | None
    message_count: int


class ConversationDetailRead(BaseModel):
    conversation: ConversationRead
    messages: list[MessageRead]


class ConversationListRead(BaseModel):
    profile_id: uuid.UUID
    conversations: list[ConversationRead]
    #: False when no provider is configured, so the app can say so once at
    #: the top rather than after every message the user types (section 55).
    assistant_available: bool


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: TitleText | None = None


class ConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: TitleText | None = None
    archived: bool | None = None


# --- sending a message ------------------------------------------------------


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: MessageText
    #: Only ``mobile_text`` is accepted (section 71). A request claiming to
    #: be a robot's voice is refused rather than stored, exactly as PRD 6
    #: refuses a symptom claiming one.
    source: MessageSource = "mobile_text"
    #: Lets a retry after a timeout answer the question already recorded
    #: rather than recording it twice (section 55).
    client_message_id: ClientId | None = None


class MemorySuggestionRead(BaseModel):
    """Something Nura noticed and is offering to remember (section 94)."""

    category: MemoryCategory
    content: str


class MessageSent(BaseModel):
    """What one exchange produced."""

    conversation: ConversationRead
    user_message: MessageRead
    #: Null when nothing could be said. The app shows ``failure_message`` and
    #: a Retry, and does not invent a reply (section 56).
    reply: MessageRead | None = None
    failure: str | None = None
    failure_message: str | None = None
    memory_suggestion: MemorySuggestionRead | None = None
    #: True when the user described something they have not logged, so the
    #: app can offer the symptom flow (section 18).
    suggest_symptom_log: bool = False


class ConfirmAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool


class ActionConfirmed(BaseModel):
    message: MessageRead | None
    outcome: MessageRead | None


# --- the Nura tab -----------------------------------------------------------


class ProactivePromptRead(BaseModel):
    """One thing Nura is offering to help with (section 35)."""

    kind: PromptKind
    subject_key: str
    text: str
    route: str | None = None
    action_label: str | None = None


class PromptDismiss(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PromptKind
    subject_key: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=PROMPT_SUBJECT_MAX_LENGTH,
        ),
    ]


class AssistantHomeRead(BaseModel):
    """What the Nura tab needs in one request (section 5)."""

    profile_id: uuid.UUID
    #: False when no provider is configured. Says so plainly rather than
    #: letting every conversation fail one message at a time (section 55).
    assistant_available: bool
    preferences: PreferencesRead
    recent_conversations: list[ConversationRead]
    prompts: list[ProactivePromptRead]
    memory_count: int


def meta_from(raw: dict[str, Any] | None) -> MessageMeta:
    """Reads a stored ``meta`` blob into the fields the API exposes.

    Deliberately not a passthrough. Anything a future version writes into
    ``meta`` stays server-side until somebody adds a field here and decides
    it is safe to show.
    """
    values = raw or {}
    tools = values.get("tools")
    return MessageMeta(
        model=values.get("model"),
        latency_ms=values.get("latency_ms"),
        tools=[str(name) for name in tools] if isinstance(tools, list) else [],
        safety_mode=values.get("safety_mode", "normal"),
        prompt_version=values.get("prompt_version"),
        truncated=bool(values.get("truncated", False)),
    )
