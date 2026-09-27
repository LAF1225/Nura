"""Symptom episodes, entries and photos (PRD 6, sections 50-53 and 63).

Every route is nested under the profile the records belong to and resolves it
through ``OwnedProfile``, so the authorization chain is the one the health
record and the medication routes already use: *an episode, an entry or a photo
is reachable only through a profile the signed-in account owns*, and anything
else is a 404 rather than a 403 (PRD 6, section 53).

Nothing here is authorized by object id alone, and the chain is complete at
every depth. An entry is fetched by profile *and* episode *and* id together; a
photo by profile *and* entry *and* id. There is no route that takes an id and
works out who it belongs to afterwards, which is what PRD 6 section 53's
"never authorize by object ID alone" rules out.

The routes are written out rather than generated. They are repetitive, and that
is the point: this is the surface that decides whether somebody's symptom
descriptions and photographs can be read, and being able to read each one in
full is worth more here than brevity.
"""

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import DbSession, Now, OwnedProfile, http_error
from app.models import Profile, SymptomEntry, SymptomEpisode, SymptomPhoto
from app.schemas.symptom import (
    EpisodeStatus,
    SymptomEntryCreate,
    SymptomEntryRead,
    SymptomEntrySaved,
    SymptomEntryUpdate,
    SymptomEpisodeCreate,
    SymptomEpisodeDetailRead,
    SymptomEpisodeRead,
    SymptomEpisodeRecur,
    SymptomEpisodeSaved,
    SymptomEpisodeUpdate,
    SymptomPhotoRead,
    SymptomSafetyRead,
    SymptomSummaryRead,
)
from app.services.errors import DomainError
from app.services.storage import get_object_store
from app.services.symptoms import entries as entry_service
from app.services.symptoms import episodes as episode_service
from app.services.symptoms import photos as photo_service
from app.services.symptoms import safety as safety_service
from app.services.symptoms import summary as summary_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles/{profile_id}/symptoms", tags=["symptoms"])

NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED


# --- shared plumbing --------------------------------------------------------


def _safety_read(assessment: safety_service.SafetyAssessment) -> SymptomSafetyRead:
    return SymptomSafetyRead(
        worsening=assessment.worsening,
        reasons=list(assessment.reasons),  # type: ignore[arg-type]
        notice=assessment.notice,
        urgent=assessment.urgent,
    )


def _assess(
    db: DbSession, episode: SymptomEpisode, now: datetime
) -> safety_service.SafetyAssessment:
    """The guidance for an episode, from the two newest entries.

    Derived on every read rather than stored, for the same reason a robot's
    connection status is: a value that means "how this is going right now" is
    wrong the moment it is written.
    """
    recent = episode_service.recent_entries(db, episode.id, limit=2)
    return safety_service.assess(
        recent[0] if recent else None,
        recent[1] if len(recent) > 1 else None,
        first_recorded_at=episode_service.first_recorded_at(db, episode.id),
        now=now,
    )


def _entry_read(entry: SymptomEntry) -> SymptomEntryRead:
    return SymptomEntryRead.model_validate(entry)


def _episode_read(
    db: DbSession, episode: SymptomEpisode, now: datetime
) -> SymptomEpisodeRead:
    entries = list(episode.entries)
    return SymptomEpisodeRead(
        id=episode.id,
        profile_id=episode.profile_id,
        name=episode.name,
        body_site=episode.body_site,
        status=episode.status,  # type: ignore[arg-type]
        first_noticed_at=episode.first_noticed_at,
        first_noticed_date=episode.first_noticed_date,
        first_noticed_year=episode.first_noticed_year,
        first_noticed_text=episode.first_noticed_text,
        resolved_at=episode.resolved_at,
        previous_episode_id=episode.previous_episode_id,
        source=episode.source,  # type: ignore[arg-type]
        entry_count=len(entries),
        latest_entry=_entry_read(entries[0]) if entries else None,
        safety=_safety_read(_assess(db, episode, now)),
        created_at=episode.created_at,
        updated_at=episode.updated_at,
    )


def _episode_detail(
    db: DbSession, episode: SymptomEpisode, now: datetime
) -> SymptomEpisodeDetailRead:
    base = _episode_read(db, episode, now)
    return SymptomEpisodeDetailRead(
        **base.model_dump(),
        entries=[_entry_read(entry) for entry in episode.entries],
    )


def _fetch_episode(
    db: DbSession, profile: Profile, episode_id: uuid.UUID
) -> SymptomEpisode:
    try:
        return episode_service.get_episode(db, profile.id, episode_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_entry(
    db: DbSession, profile: Profile, episode_id: uuid.UUID, entry_id: uuid.UUID
) -> SymptomEntry:
    try:
        return entry_service.get_entry(db, profile.id, episode_id, entry_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_photo(
    db: DbSession, profile: Profile, entry_id: uuid.UUID, photo_id: uuid.UUID
) -> SymptomPhoto:
    try:
        return photo_service.get_photo(db, profile.id, entry_id, photo_id)
    except DomainError as error:
        raise http_error(error) from error


def _entry_input(
    payload: SymptomEntryCreate | SymptomEntryUpdate,
) -> entry_service.EntryInput:
    """One conversion for both flows, because there is one entry shape."""
    return entry_service.EntryInput(
        recorded_at=payload.recorded_at,
        main_symptom=payload.main_symptom,
        site=payload.site,
        onset_text=payload.onset_text,
        onset_at=payload.onset_at,
        onset_date=payload.onset_date,
        character=payload.character,
        radiation=payload.radiation,
        timing=payload.timing,
        severity=payload.severity,
        change_state=payload.change_state,
        free_text_note=payload.free_text_note,
        associated_symptoms=list(payload.associated_symptoms),
        exacerbating_factors=list(payload.exacerbating_factors),
        relieving_factors=list(payload.relieving_factors),
        negated_items=list(payload.negated_items),
        uncertain_items=list(payload.uncertain_items),
        context_dependent_items=list(payload.context_dependent_items),
        client_entry_id=getattr(payload, "client_entry_id", None),
    )


# --- summary ----------------------------------------------------------------
#
# Declared before `/{episode_id}` so "summary" is matched as a literal rather
# than failing to parse as a UUID. FastAPI matches in declaration order.


@router.get("/summary", response_model=SymptomSummaryRead)
def read_symptom_summary(
    profile: OwnedProfile, db: DbSession, now: Now
) -> SymptomSummaryRead:
    """Counts for the Health overview and the Today card (PRD 6, s48 and 51).

    Counts only: no diagnosis, no risk score, and nothing that mixes symptoms
    with diagnosed conditions.
    """
    summary = summary_service.build_summary(db, profile.id, now)
    return SymptomSummaryRead(
        profile_id=profile.id,
        active_count=summary.active_count,
        worsening_count=summary.worsening_count,
        recent_updates_count=summary.recent_updates_count,
        has_episodes=summary.has_episodes,
    )


# --- episodes ---------------------------------------------------------------

StatusFilter = Annotated[
    EpisodeStatus | None,
    Query(alias="status", description="Only episodes with this status."),
]
ActiveFilter = Annotated[
    bool | None, Query(description="True for episodes that are ongoing.")
]
NameFilter = Annotated[
    str | None, Query(max_length=120, description="Episodes whose name contains this.")
]


@router.get("", response_model=list[SymptomEpisodeRead])
def list_episodes(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    status_filter: StatusFilter = None,
    active: ActiveFilter = None,
    name: NameFilter = None,
) -> list[SymptomEpisodeRead]:
    """This profile's symptom episodes, most recently updated first."""
    rows = episode_service.list_episodes(
        db,
        profile.id,
        status=status_filter,
        active_only=bool(active),
        name=name,
    )
    return [_episode_read(db, episode, now) for episode in rows]


@router.post("", response_model=SymptomEpisodeSaved, status_code=CREATED)
def create_episode(
    payload: SymptomEpisodeCreate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
) -> SymptomEpisodeSaved:
    """Starts an episode, with its first observation if one was sent.

    Both flows end here: the manual form and the guided conversation build the
    same draft and save it the same way, with only ``source`` differing
    (PRD 6, section 4).

    **Idempotent through the first entry's client id.** A retry after a failed
    request finds the entry already stored and returns its episode with
    ``created: false`` and a 200, rather than creating a second episode for the
    same symptom (PRD 6, section 61).
    """
    first = payload.first_entry
    if first is not None and first.client_entry_id:
        existing = entry_service.find_by_client_id(db, profile.id, first.client_entry_id)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            episode = _fetch_episode(db, profile, existing.symptom_episode_id)
            return SymptomEpisodeSaved(
                episode=_episode_detail(db, episode, now), created=False
            )

    episode = episode_service.create_episode(
        db,
        profile,
        name=payload.name,
        body_site=payload.body_site,
        first_noticed_at=payload.first_noticed_at,
        first_noticed_date=payload.first_noticed_date,
        first_noticed_year=payload.first_noticed_year,
        first_noticed_text=payload.first_noticed_text,
        source=payload.source,
        commit=False,
    )
    if first is not None:
        entry_service.create_entry(
            db,
            profile,
            episode,
            _entry_input(first),
            source=first.source,
            now=now,
            commit=False,
        )
    db.commit()
    db.refresh(episode)
    logger.info("symptom.episode.create success")
    return SymptomEpisodeSaved(episode=_episode_detail(db, episode, now), created=True)


@router.get("/{episode_id}", response_model=SymptomEpisodeDetailRead)
def read_episode(
    episode_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> SymptomEpisodeDetailRead:
    """One episode and its history (PRD 6, section 36)."""
    return _episode_detail(db, _fetch_episode(db, profile, episode_id), now)


@router.patch("/{episode_id}", response_model=SymptomEpisodeDetailRead)
def update_episode(
    episode_id: uuid.UUID,
    payload: SymptomEpisodeUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> SymptomEpisodeDetailRead:
    """Changes the episode itself -- its name, where it is, or its status."""
    episode = _fetch_episode(db, profile, episode_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("status") == "resolved" and episode.resolved_at is None:
        # Resolving through a PATCH still has to record when, so the status and
        # the timestamp can never disagree (and the CHECK constraint says so).
        fields["resolved_at"] = now
    updated = episode_service.update_episode(db, episode, fields)
    return _episode_detail(db, updated, now)


@router.delete("/{episode_id}", status_code=NO_CONTENT)
def delete_episode(episode_id: uuid.UUID, profile: OwnedProfile, db: DbSession) -> None:
    """Removes an episode, its entries and its photos.

    For a symptom logged by mistake. Resolving is what somebody wants for a
    symptom that has ended, and the app says which is which before asking.
    The stored photo objects go first: a database cascade cannot reach into
    storage (PRD 6, section 35).
    """
    episode = _fetch_episode(db, profile, episode_id)
    photo_service.purge_objects(
        get_object_store(), photo_service.photos_for_episode(db, episode.id)
    )
    episode_service.delete_episode(db, episode)


@router.post("/{episode_id}/resolve", response_model=SymptomEpisodeDetailRead)
def resolve_episode(
    episode_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> SymptomEpisodeDetailRead:
    """Marks a symptom as over, keeping every entry and photo.

    Idempotent, and it keeps the original ``resolved_at`` rather than pushing
    the timestamp forward on a retry (PRD 6, section 37).
    """
    episode = episode_service.resolve_episode(
        db, _fetch_episode(db, profile, episode_id), now
    )
    return _episode_detail(db, episode, now)


@router.post(
    "/{episode_id}/recur", response_model=SymptomEpisodeSaved, status_code=CREATED
)
def record_recurrence(
    episode_id: uuid.UUID,
    payload: SymptomEpisodeRecur,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
) -> SymptomEpisodeSaved:
    """Records that a resolved symptom has come back (PRD 6, section 38).

    A *new* episode, linked to the one it follows and carrying the status
    ``recurring``. The earlier bout keeps its own onset, its own resolution and
    its own entries -- nothing is merged, and nothing is rewritten.

    Refused with 409 when the episode is still ongoing: that is a follow-up,
    not a recurrence, and creating a second live episode of the same symptom is
    exactly the merge this model exists to avoid.
    """
    previous = _fetch_episode(db, profile, episode_id)
    first = payload.first_entry

    if first is not None and first.client_entry_id:
        existing = entry_service.find_by_client_id(db, profile.id, first.client_entry_id)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            episode = _fetch_episode(db, profile, existing.symptom_episode_id)
            return SymptomEpisodeSaved(
                episode=_episode_detail(db, episode, now), created=False
            )

    try:
        recurrence = episode_service.reopen_as_recurrence(
            db,
            profile,
            previous,
            first_noticed_at=payload.first_noticed_at,
            first_noticed_date=payload.first_noticed_date,
            first_noticed_text=payload.first_noticed_text,
            body_site=payload.body_site,
            source=payload.source,
        )
    except DomainError as error:
        raise http_error(error) from error

    if first is not None:
        entry_service.create_entry(
            db, profile, recurrence, _entry_input(first), source=first.source, now=now
        )
        db.refresh(recurrence)

    return SymptomEpisodeSaved(episode=_episode_detail(db, recurrence, now), created=True)


# --- entries ----------------------------------------------------------------


@router.get("/{episode_id}/entries", response_model=list[SymptomEntryRead])
def list_entries(
    episode_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> list[SymptomEntryRead]:
    """One episode's observations, newest first (PRD 6, section 36)."""
    episode = _fetch_episode(db, profile, episode_id)
    return [_entry_read(entry) for entry in entry_service.list_entries(db, episode.id)]


@router.post(
    "/{episode_id}/entries", response_model=SymptomEntrySaved, status_code=CREATED
)
def create_entry(
    episode_id: uuid.UUID,
    payload: SymptomEntryCreate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
) -> SymptomEntrySaved:
    """Adds a follow-up observation (PRD 6, section 47).

    Carries only what has changed -- severity, how it is going, anything new
    with it, a note, a photo. Nothing re-states the original description.

    **Idempotent through ``client_entry_id``.** A replay returns the stored
    entry with ``created: false`` and a 200, so an offline queue can retry
    freely without ever producing two records of one observation
    (PRD 6, section 61).
    """
    episode = _fetch_episode(db, profile, episode_id)
    entry, created = entry_service.create_entry(
        db, profile, episode, _entry_input(payload), source=payload.source, now=now
    )
    if not created:
        response.status_code = status.HTTP_200_OK

    db.refresh(episode)
    return SymptomEntrySaved(
        entry=_entry_read(entry),
        created=created,
        safety=_safety_read(_assess(db, episode, now)),
    )


@router.patch("/{episode_id}/entries/{entry_id}", response_model=SymptomEntrySaved)
def update_entry(
    episode_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: SymptomEntryUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> SymptomEntrySaved:
    """Corrects an observation (PRD 6, sections 30 and 67)."""
    episode = _fetch_episode(db, profile, episode_id)
    entry = _fetch_entry(db, profile, episode_id, entry_id)
    updated = entry_service.update_entry(
        db, entry, payload.model_dump(exclude_unset=True)
    )
    return SymptomEntrySaved(
        entry=_entry_read(updated),
        created=False,
        safety=_safety_read(_assess(db, episode, now)),
    )


@router.delete("/{episode_id}/entries/{entry_id}", status_code=NO_CONTENT)
def delete_entry(
    episode_id: uuid.UUID,
    entry_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> None:
    """Removes one observation, and the photos attached to it."""
    entry = _fetch_entry(db, profile, episode_id, entry_id)
    photo_service.purge_objects(
        get_object_store(), photo_service.list_photos(db, entry.id)
    )
    entry_service.delete_entry(db, entry)


# --- photos -----------------------------------------------------------------


@router.post(
    "/{episode_id}/entries/{entry_id}/photos",
    response_model=SymptomPhotoRead,
    status_code=CREATED,
)
def upload_photo(
    episode_id: uuid.UUID,
    entry_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    response: Response,
    file: Annotated[UploadFile, File(description="A JPEG, PNG or HEIC image.")],
    client_photo_id: Annotated[str | None, Form()] = None,
) -> SymptomPhotoRead:
    """Attaches a photo to an observation (PRD 6, sections 31-34).

    The bytes go to private storage and the response says nothing about where.
    The declared content type is checked against the file's own header, so a
    mislabelled upload is refused rather than stored under a type it is not.

    **Nothing looks at the image** (PRD 6, section 32).
    """
    entry = _fetch_entry(db, profile, episode_id, entry_id)
    data = file.file.read()

    try:
        photo, created = photo_service.attach_photo(
            db,
            get_object_store(),
            profile,
            entry,
            data,
            declared_type=file.content_type,
            client_photo_id=client_photo_id,
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error

    if not created:
        response.status_code = status.HTTP_200_OK
    return SymptomPhotoRead.model_validate(photo)


@router.get(
    "/{episode_id}/entries/{entry_id}/photos/{photo_id}/content",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}, "description": "The image bytes."}},
)
def read_photo_content(
    episode_id: uuid.UUID,
    entry_id: uuid.UUID,
    photo_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> Response:
    """The image itself, for the person it belongs to (PRD 6, section 63).

    The whole chain is re-checked on every request for every byte: the account
    owns the profile, the episode belongs to the profile, the entry belongs to
    the episode, and the photo belongs to the entry. There is no signed URL and
    no public path -- an unrelated account gets the same 404 as a photo that was
    never there.

    ``no-store`` because a cached copy of somebody's symptom photograph in a
    shared proxy is exactly the thing this route exists to prevent.
    """
    # The episode is resolved first so an entry id from another of this
    # profile's episodes fails the same way as one from another account.
    _fetch_episode(db, profile, episode_id)
    _fetch_entry(db, profile, episode_id, entry_id)
    photo = _fetch_photo(db, profile, entry_id, photo_id)

    try:
        data = photo_service.read_photo(get_object_store(), photo)
    except DomainError as error:
        raise http_error(error) from error

    return Response(
        content=data,
        media_type=photo.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "Content-Length": str(len(data)),
        },
    )


@router.delete(
    "/{episode_id}/entries/{entry_id}/photos/{photo_id}", status_code=NO_CONTENT
)
def delete_photo(
    episode_id: uuid.UUID,
    entry_id: uuid.UUID,
    photo_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
) -> None:
    """Removes a photo -- the stored object and the row (PRD 6, section 35).

    The app confirms first. Deleting something already deleted is a 404, which
    is the same answer as one that was never there.
    """
    _fetch_episode(db, profile, episode_id)
    _fetch_entry(db, profile, episode_id, entry_id)
    photo = _fetch_photo(db, profile, entry_id, photo_id)
    photo_service.delete_photo(db, get_object_store(), photo)
