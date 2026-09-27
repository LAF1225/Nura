"""Symptom episodes: the ongoing problem (PRD 6, sections 8, 10, 37 and 38).

An episode is one *bout* of one symptom. That is the decision the rest of the
feature hangs off, and the two places it shows are here.

**Resolving keeps everything.** ``resolve`` sets a status and a timestamp and
touches nothing else. No entry is deleted, no photo is removed, and the episode
stays fetchable forever -- it simply stops appearing in the active list
(PRD 6, section 37). Resolving something already resolved is a no-op rather
than an error, so a retried request from a phone that lost its answer is safe.

**A symptom coming back is a new episode, linked to the old one.** PRD 6
section 38 asks for one documented model and forbids silently merging unrelated
events; ``reopen_as_recurrence`` takes the second option. The new episode
carries the status ``recurring`` and ``previous_episode_id`` pointing at the
bout it follows. Each bout therefore keeps its own onset, its own resolution
and its own entries, while the chain still answers "has this happened before?".
Reopening the original instead would have produced one episode with a
first-noticed date from months ago and a gap in the middle that no summary
could describe honestly.

**Nothing is ever inferred.** A status changes because somebody changed it. An
episode nobody has updated for six weeks is still active, because the
alternative is Nura deciding a person got better (PRD 6, section 10).
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Profile, SymptomEntry, SymptomEpisode
from app.models.enums import SYMPTOM_ACTIVE_STATUSES
from app.services.errors import DomainError, NotFoundError

logger = logging.getLogger(__name__)

#: The most episodes one list request will return (PRD 6, section 49). Plenty:
#: somebody with more than this has years of history, and the history screen
#: pages by status rather than scrolling forever.
MAX_EPISODES = 200

#: How far back "recently updated" reaches, for the Health overview's
#: "symptoms updated this week" figure (PRD 6, section 48).
RECENT_WINDOW_DAYS = 7


class EpisodeNotFoundError(NotFoundError):
    """No such episode for this profile.

    The same answer as one belonging to somebody else, so an id is never
    confirmed to exist (PRD 6, section 53).
    """

    code = "symptom_episode_not_found"


class EpisodeNotResolvedError(DomainError):
    """Asked to record a recurrence of something that has not ended.

    Recording a recurrence of an active episode would create two live episodes
    of the same symptom, which is the merge PRD 6 section 38 warns about,
    arrived at from the other direction. The follow-up flow is what an ongoing
    symptom wants.
    """

    status_code = 409
    code = "symptom_episode_not_resolved"


def _log(action: str) -> None:
    """``symptom.episode.create success`` -- and never a symptom name.

    PRD 6 sections 62 and 65: no symptom name, free text, associated symptom or
    photo path appears in a log line, ever.
    """
    logger.info("symptom.%s success", action)


def _with_entries(query: Select[Any]) -> Select[Any]:
    """Loads each episode's entries in one extra query rather than N."""
    return query.options(selectinload(SymptomEpisode.entries))


# --- reading ----------------------------------------------------------------


def list_episodes(
    db: Session,
    profile_id: uuid.UUID,
    *,
    status: str | None = None,
    active_only: bool = False,
    name: str | None = None,
    limit: int = MAX_EPISODES,
) -> list[SymptomEpisode]:
    """This profile's episodes, most recently updated first.

    The filters are the four PRD 6 section 49 asks for and no more: active,
    resolved, recent (which is what the default ordering gives) and name. There
    is no full-text search over notes -- a search box that reaches into
    somebody's symptom descriptions is a feature that needs its own thought.
    """
    query = select(SymptomEpisode).where(SymptomEpisode.profile_id == profile_id)

    if active_only:
        query = query.where(SymptomEpisode.status.in_(SYMPTOM_ACTIVE_STATUSES))
    elif status is not None:
        query = query.where(SymptomEpisode.status == status)

    if name:
        # Case-insensitive contains, on the name only.
        query = query.where(SymptomEpisode.name.ilike(f"%{name}%"))

    query = query.order_by(SymptomEpisode.updated_at.desc()).limit(limit)
    return list(db.execute(_with_entries(query)).scalars().all())


def get_episode(
    db: Session, profile_id: uuid.UUID, episode_id: uuid.UUID
) -> SymptomEpisode:
    """One episode of this profile's, or a 404 that reveals nothing.

    The profile is part of the lookup rather than checked afterwards, so there
    is no path where an episode is fetched first and authorized second
    (PRD 6, section 53).
    """
    episode = db.execute(
        _with_entries(
            select(SymptomEpisode).where(
                SymptomEpisode.id == episode_id,
                SymptomEpisode.profile_id == profile_id,
            )
        )
    ).scalar_one_or_none()
    if episode is None:
        raise EpisodeNotFoundError("Not found.")
    return episode


def recent_entries(
    db: Session, episode_id: uuid.UUID, limit: int = 2
) -> list[SymptomEntry]:
    """The newest entries for an episode, newest first.

    Two is the useful number: the safety assessment compares the latest against
    the one before it, and nothing in PRD 6 looks further back than that
    (section 41).
    """
    return list(
        db.execute(
            select(SymptomEntry)
            .where(SymptomEntry.symptom_episode_id == episode_id)
            .order_by(SymptomEntry.recorded_at.desc(), SymptomEntry.created_at.desc())
            .limit(limit)
            .options(selectinload(SymptomEntry.photos))
        )
        .scalars()
        .all()
    )


def first_recorded_at(db: Session, episode_id: uuid.UUID) -> datetime | None:
    """When this episode was first written about."""
    return db.execute(
        select(func.min(SymptomEntry.recorded_at)).where(
            SymptomEntry.symptom_episode_id == episode_id
        )
    ).scalar_one_or_none()


def has_entries(db: Session, episode_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(SymptomEntry.id)
            .where(SymptomEntry.symptom_episode_id == episode_id)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


# --- writing ----------------------------------------------------------------


def create_episode(
    db: Session,
    profile: Profile,
    *,
    name: str,
    body_site: str | None = None,
    first_noticed_at: datetime | None = None,
    first_noticed_date: Any = None,
    first_noticed_year: int | None = None,
    first_noticed_text: str | None = None,
    source: str = "manual_app",
    previous_episode_id: uuid.UUID | None = None,
    status: str = "active",
    commit: bool = True,
) -> SymptomEpisode:
    """Starts an episode.

    Deliberately does *not* touch ``health_profile_status``. The health
    profile's completeness is about a record somebody fills in -- conditions,
    medications, allergies -- and having no symptoms logged is a good state,
    not an incomplete one. Counting symptoms towards it would make a percentage
    go up because somebody felt unwell (PRD 4, section 7; PRD 6, section 48).
    """
    episode = SymptomEpisode(
        profile_id=profile.id,
        name=name,
        body_site=body_site,
        status=status,
        first_noticed_at=first_noticed_at,
        first_noticed_date=first_noticed_date,
        first_noticed_year=first_noticed_year,
        first_noticed_text=first_noticed_text,
        source=source,
        previous_episode_id=previous_episode_id,
    )
    db.add(episode)
    if commit:
        db.commit()
        db.refresh(episode)
        _log("episode.create")
    else:
        # The session does not autoflush, and the caller needs ``episode.id``
        # to hang a first entry off. Flushing assigns it without committing, so
        # the episode and its entry still land in one transaction.
        db.flush()
    return episode


def update_episode(
    db: Session, episode: SymptomEpisode, fields: dict[str, Any]
) -> SymptomEpisode:
    """Applies the fields present in a PATCH and leaves the rest alone.

    ``status`` is accepted here for the two cases a user drives directly --
    marking something historical, or putting a resolved episode back to active
    because they were too quick -- and the resolve route exists separately
    because resolving also has to record *when*.
    """
    for field, value in fields.items():
        setattr(episode, field, value)
    db.commit()
    db.refresh(episode)
    _log("episode.update")
    return episode


def resolve_episode(
    db: Session, episode: SymptomEpisode, now: datetime
) -> SymptomEpisode:
    """Marks an episode resolved, keeping everything it holds.

    Idempotent: an episode that is already resolved keeps its original
    ``resolved_at`` rather than having the timestamp pushed forward by a
    retried request (PRD 6, section 37).
    """
    if episode.status == "resolved":
        return episode

    episode.status = "resolved"
    episode.resolved_at = now
    db.commit()
    db.refresh(episode)
    _log("episode.resolve")
    return episode


def reopen_as_recurrence(
    db: Session,
    profile: Profile,
    episode: SymptomEpisode,
    *,
    first_noticed_at: datetime | None = None,
    first_noticed_date: Any = None,
    first_noticed_text: str | None = None,
    body_site: str | None = None,
    source: str = "manual_app",
) -> SymptomEpisode:
    """Records that a resolved symptom has come back, as a new linked episode.

    The name carries over, the site carries over unless a new one is given, and
    the onset is this bout's -- not the old one's. The previous episode is left
    exactly as it was: resolved, with its own history intact
    (PRD 6, section 38).
    """
    if episode.status != "resolved":
        raise EpisodeNotResolvedError(
            "This symptom is still recorded as ongoing. Add an update instead."
        )

    recurrence = create_episode(
        db,
        profile,
        name=episode.name,
        body_site=body_site if body_site is not None else episode.body_site,
        first_noticed_at=first_noticed_at,
        first_noticed_date=first_noticed_date,
        first_noticed_text=first_noticed_text,
        source=source,
        previous_episode_id=episode.id,
        status="recurring",
        commit=False,
    )
    db.commit()
    db.refresh(recurrence)
    _log("episode.recur")
    return recurrence


def delete_episode(db: Session, episode: SymptomEpisode) -> None:
    """Removes an episode and everything under it.

    Offered because somebody who logged a symptom by mistake should be able to
    take it back, and resolving a thing that never happened would leave a false
    record. The app confirms first, and says plainly that the entries and
    photos go with it. Photo *objects* are removed by the caller before this
    runs -- the database cascade cannot reach into storage.
    """
    db.delete(episode)
    db.commit()
    _log("episode.delete")
