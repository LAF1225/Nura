"""Symptom request/response models (PRD 6, sections 11, 50-52 and 57).

Models, never ORM rows, for the same reason as everywhere else: the API's shape
is decided here rather than falling out of whatever columns a table happens to
have.

Four things a reader should check for and find:

**One entry shape for both flows.** ``SymptomEntryCreate`` is what the manual
form sends and what the guided conversation sends. There is no second model for
"chat data" (PRD 6, section 4).

**No client sets a source it chooses freely.** ``source`` is limited to the two
flows that exist, so a request cannot claim to be a future robot's voice or a
caregiver's entry (PRD 6, section 57).

**A photo's storage key is never returned.** ``SymptomPhotoRead`` carries an id,
a type and a size. Where the bytes are is the backend's business, and a photo is
fetched through an authenticated route rather than by holding a path
(PRD 6, section 63).

**Nothing carries a diagnosis, a probability or a risk score.** The only
interpretive field anywhere is ``SymptomSafetyRead``, and its text is always one
of the reviewed sentences in ``app.services.symptoms.safety``
(PRD 6, sections 51 and 81).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.models.enums import (
    SYMPTOM_CHANGE_STATES,
    SYMPTOM_EPISODE_STATUSES,
    SYMPTOM_PHOTO_CONTENT_TYPES,
    SYMPTOM_SOURCES,
    SYMPTOM_SOURCES_ALLOWED,
)
from app.models.symptom import (
    DESCRIPTOR_MAX_LENGTH,
    SEVERITY_MAX,
    SEVERITY_MIN,
    SYMPTOM_NAME_MAX_LENGTH,
    SYMPTOM_NOTE_MAX_LENGTH,
)
from app.services.symptoms.entries import MAX_LIST_ITEMS
from app.services.symptoms.safety import WORSENING_REASONS

EpisodeStatus = Literal["active", "resolved", "recurring", "historical"]
ChangeState = Literal["improving", "same", "worsening", "unsure"]
SymptomSource = Literal[
    "manual_app", "guided_app", "robot_voice_future", "caregiver_future", "import_future"
]
#: What a client may declare. The reserved sources are readable but not
#: writable (PRD 6, section 57).
SymptomSourceInput = Literal["manual_app", "guided_app"]
PhotoContentType = Literal["image/jpeg", "image/png", "image/heic", "image/heif"]
WorseningReason = Literal[
    "reported_worsening", "severity_increase", "new_associated_symptom"
]

# Guard every Literal against drifting from the tuple the database CHECK
# constraints are generated from. A mismatch is a startup failure rather than a
# request the API accepts and Postgres rejects.
assert set(SYMPTOM_EPISODE_STATUSES) == set(EpisodeStatus.__args__)  # type: ignore[attr-defined]
assert set(SYMPTOM_CHANGE_STATES) == set(ChangeState.__args__)  # type: ignore[attr-defined]
assert set(SYMPTOM_SOURCES) == set(SymptomSource.__args__)  # type: ignore[attr-defined]
assert set(SYMPTOM_SOURCES_ALLOWED) == set(SymptomSourceInput.__args__)  # type: ignore[attr-defined]
assert set(SYMPTOM_PHOTO_CONTENT_TYPES) == set(PhotoContentType.__args__)  # type: ignore[attr-defined]
assert set(WORSENING_REASONS) == set(WorseningReason.__args__)  # type: ignore[attr-defined]

SymptomName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=SYMPTOM_NAME_MAX_LENGTH
    ),
]
Descriptor = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTOR_MAX_LENGTH)
]
LongNote = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=SYMPTOM_NOTE_MAX_LENGTH)
]
#: 0 = no symptom, 10 = worst imaginable. Null wherever a number is the wrong
#: shape of answer for the symptom (PRD 6, section 22).
Severity = Annotated[int, Field(ge=SEVERITY_MIN, le=SEVERITY_MAX)]
ItemList = Annotated[list[Descriptor], Field(max_length=MAX_LIST_ITEMS)]
#: A client-generated id, so a retry cannot create the record twice.
ClientId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=8, max_length=64)
]
#: The calendar year of an approximate onset ("some time in 2024").
OnsetYear = Annotated[int, Field(ge=1900, le=2200)]


def _blank_to_none(value: str | None) -> str | None:
    """A cleared text box is no answer, not an empty string."""
    if value is None:
        return None
    return value.strip() or None


# --- photos -----------------------------------------------------------------


class SymptomPhotoRead(BaseModel):
    """A photo, described without saying where it is.

    The bytes come from
    ``.../entries/{entry_id}/photos/{photo_id}/content``, which authorizes the
    profile on every request. There is deliberately no URL in this body: a URL
    in a response is a URL in a log, a crash report and a screenshot
    (PRD 6, section 63).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symptom_entry_id: uuid.UUID
    content_type: PhotoContentType
    byte_size: int
    created_at: datetime


# --- entries ----------------------------------------------------------------


class SymptomEntryBase(BaseModel):
    """The structured description, as either flow captures it.

    Every field is optional. PRD 6 section 11 is explicit that the model has to
    tolerate an incomplete description, and section 12 that pain-specific
    fields must not be forced onto symptoms they make no sense for -- radiation
    means nothing for fatigue, so it simply stays null.
    """

    #: When the observation is about. Defaults to the server's clock; the app
    #: sends the moment the user actually saved it, which may be hours earlier
    #: if the phone was offline (PRD 6, section 59).
    recorded_at: datetime | None = None
    main_symptom: Descriptor | None = None
    site: Descriptor | None = None
    #: The user's own wording for how it began -- "suddenly", "after exercise".
    #: Kept alongside the structured time, not instead of it (section 74).
    onset_text: Descriptor | None = None
    onset_at: datetime | None = None
    onset_date: date | None = None
    character: Descriptor | None = None
    radiation: Descriptor | None = None
    timing: Descriptor | None = None
    severity: Severity | None = None
    change_state: ChangeState | None = None
    free_text_note: LongNote | None = None
    associated_symptoms: ItemList = []
    exacerbating_factors: ItemList = []
    relieving_factors: ItemList = []
    #: Explicitly denied, hedged, or true only in a context. Preserved so no
    #: summary can claim more certainty than the person expressed (section 24).
    negated_items: ItemList = []
    uncertain_items: ItemList = []
    context_dependent_items: ItemList = []

    @field_validator(
        "main_symptom",
        "site",
        "onset_text",
        "character",
        "radiation",
        "timing",
        "free_text_note",
    )
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _one_onset_precision(self) -> "SymptomEntryBase":
        """An exact instant or a day, never both.

        Checked here as well as in the database so a client that sends both
        gets a 422 it can act on, rather than a 500 from a CHECK constraint
        firing deep inside a transaction.
        """
        if self.onset_at is not None and self.onset_date is not None:
            raise ValueError("Send an exact onset time or a date, not both.")
        return self


class SymptomEntryCreate(SymptomEntryBase):
    """A new observation.

    ``client_entry_id`` is generated by the app *before* it tries to send, so
    the id survives a failed request and a retry returns the entry that was
    already stored rather than creating a second one (PRD 6, section 61).
    """

    client_entry_id: ClientId | None = None
    #: Which flow captured it. Defaults to the manual form.
    source: SymptomSourceInput = "manual_app"


class SymptomEntryUpdate(SymptomEntryBase):
    """A PATCH. Everything omitted is left exactly as it was.

    Correcting an entry is a first-class action: PRD 6 section 30 requires the
    user to be able to fix what was captured, and section 67 that no answer
    becomes permanently locked.
    """


class SymptomEntryRead(SymptomEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    profile_id: uuid.UUID
    symptom_episode_id: uuid.UUID
    recorded_at: datetime
    #: How it was captured. Read-only, set by the server (section 57).
    source: SymptomSource
    photos: list[SymptomPhotoRead] = []
    created_at: datetime
    updated_at: datetime


# --- safety -----------------------------------------------------------------


class SymptomSafetyRead(BaseModel):
    """Cautious, non-diagnostic guidance, and why it is being shown.

    ``notice`` is always one of the reviewed sentences in
    ``app.services.symptoms.safety`` -- never assembled from the user's own
    words. ``urgent`` is False in every shipped deployment: the red-flag rules
    are built and tested but switched off until a clinician has reviewed them
    (PRD 6, sections 42, 44 and 45).
    """

    #: True only because the user recorded a change, never because Nura
    #: concluded one (PRD 6, section 41).
    worsening: bool
    reasons: list[WorseningReason]
    notice: str | None
    #: True only when a reviewed red-flag rule matched *and* the rules are
    #: enabled for this deployment.
    urgent: bool


# --- episodes ---------------------------------------------------------------


class SymptomEpisodeBase(BaseModel):
    name: SymptomName
    body_site: Descriptor | None = None
    #: Exactly one of these three, or none: an exact instant, a day, or a year.
    #: "I think it was 2023" stays a year rather than becoming a January date
    #: (PRD 4, section 31; PRD 6, section 15).
    first_noticed_at: datetime | None = None
    first_noticed_date: date | None = None
    first_noticed_year: OnsetYear | None = None
    first_noticed_text: Descriptor | None = None

    @field_validator("body_site", "first_noticed_text")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _one_first_noticed_precision(self) -> "SymptomEpisodeBase":
        """An instant, a day or a year -- at most one of the three.

        The same rule as the database CHECK, applied here so a client learns
        what is wrong from a 422 instead of a 500.
        """
        given = [
            self.first_noticed_at,
            self.first_noticed_date,
            self.first_noticed_year,
        ]
        if len([value for value in given if value is not None]) > 1:
            raise ValueError("Send one onset precision: a time, a date or a year.")
        return self


class SymptomEpisodeCreate(SymptomEpisodeBase):
    """A new episode, optionally with its first observation.

    Both arrive together because both flows end at one Save: the review screen
    holds a description, and splitting it into two requests would leave an
    episode with no entry behind whenever the second one failed
    (PRD 6, sections 4 and 30).
    """

    first_entry: SymptomEntryCreate | None = None
    source: SymptomSourceInput = "manual_app"


class SymptomEpisodeUpdate(BaseModel):
    """A PATCH on the episode itself.

    ``status`` is here for the two changes a user makes directly -- marking
    something historical, or undoing a resolution they made too soon. Resolving
    has its own route because it also has to record *when*.
    """

    name: SymptomName | None = None
    body_site: Descriptor | None = None
    status: EpisodeStatus | None = None
    first_noticed_at: datetime | None = None
    first_noticed_date: date | None = None
    first_noticed_year: OnsetYear | None = None
    first_noticed_text: Descriptor | None = None

    @field_validator("body_site", "first_noticed_text")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _one_first_noticed_precision(self) -> "SymptomEpisodeUpdate":
        given = [
            self.first_noticed_at,
            self.first_noticed_date,
            self.first_noticed_year,
        ]
        if len([value for value in given if value is not None]) > 1:
            raise ValueError("Send one onset precision: a time, a date or a year.")
        return self


class SymptomEpisodeRecur(SymptomEpisodeBase):
    """A resolved symptom has come back.

    The name comes from the episode being reopened, so it is not required here;
    everything else describes *this* bout. A new episode is created, linked to
    the old one, and the old one is left exactly as it was
    (PRD 6, section 38).
    """

    name: SymptomName | None = None  # type: ignore[assignment]
    first_entry: SymptomEntryCreate | None = None
    source: SymptomSourceInput = "manual_app"


class SymptomEpisodeRead(BaseModel):
    """An episode as a list row shows it.

    Carries the latest entry's severity and change state, because every screen
    that lists symptoms shows them and a request per row would be exactly what
    PRD 3 section 16 warns against.
    """

    id: uuid.UUID
    profile_id: uuid.UUID
    name: str
    body_site: str | None
    status: EpisodeStatus
    first_noticed_at: datetime | None
    first_noticed_date: date | None
    first_noticed_year: int | None
    first_noticed_text: str | None
    resolved_at: datetime | None
    #: The earlier bout this one follows, for a symptom that came back.
    previous_episode_id: uuid.UUID | None
    source: SymptomSource
    entry_count: int
    #: The newest observation, or null for an episode created without one.
    latest_entry: SymptomEntryRead | None
    #: Derived on every read from what the user recorded (PRD 6, section 41).
    safety: SymptomSafetyRead
    created_at: datetime
    updated_at: datetime


class SymptomEpisodeDetailRead(SymptomEpisodeRead):
    """One episode with its history (PRD 6, section 36)."""

    entries: list[SymptomEntryRead]


class SymptomEntrySaved(BaseModel):
    """A stored entry, plus whether this request is what created it.

    ``created`` is False for a replay of a ``client_entry_id`` already stored.
    The entry comes back either way, so a client draining a queue adopts the
    server's answer instead of retrying (PRD 6, section 61).
    """

    entry: SymptomEntryRead
    created: bool
    safety: SymptomSafetyRead


class SymptomEpisodeSaved(BaseModel):
    """A stored episode and its first entry, if one was sent."""

    episode: SymptomEpisodeDetailRead
    created: bool


# --- summary ----------------------------------------------------------------


class SymptomSummaryRead(BaseModel):
    """Counts only. No diagnosis, no risk score (PRD 6, section 51)."""

    profile_id: uuid.UUID
    #: Active and recurring episodes.
    active_count: int
    #: Active episodes whose latest entry the *user* marked worsening.
    worsening_count: int
    #: Distinct episodes written about in the last week -- episodes, not
    #: entries (PRD 6, section 48).
    recent_updates_count: int
    #: False when this profile has never logged a symptom.
    has_episodes: bool


# --- Today ------------------------------------------------------------------


class TodaySymptomRead(BaseModel):
    """The one symptom Today offers to update (PRD 6, section 52)."""

    episode_id: uuid.UUID
    name: str
    severity: int | None
    change_state: ChangeState | None
    updated_at: datetime


class TodaySymptomsRead(BaseModel):
    """The symptom block of ``/api/v1/today`` (PRD 6, section 52).

    Kept minimal: two counts and the symptom most recently written about. The
    Health tab is where the full picture lives.
    """

    active_count: int
    worsening_count: int
    #: Null when nothing is active -- including for somebody with no symptoms
    #: at all, which is a normal and welcome state.
    most_recent: TodaySymptomRead | None
    #: False when this profile has never logged a symptom, so Today can leave
    #: the card out rather than render an empty one.
    has_episodes: bool
