"""What Today and Health need to know about symptoms (PRD 6, ss39-41, 48, 51-52).

Today already assembles the whole day in one request, so symptoms join that
response rather than adding a second one (PRD 3, section 16). The payload is
small on purpose: three counts and the one symptom somebody is most likely to
want to update. Everything else is a tap away.

Two boundaries are kept here rather than left to whoever writes the screen.

**Symptom counts are never mixed with diagnosed conditions** (PRD 6,
section 48). They are separate figures from separate tables, and the Health
overview shows them in separate places. A symptom is what somebody is
experiencing; a condition is what they have been told they have, and blurring
the two in a count is how a summary starts implying a diagnosis.

**Nothing here is a risk score** (PRD 6, section 51). ``worsening_count`` counts
episodes whose most recent entry the *user* marked as worsening. There is no
severity threshold, no weighting and no total, because any of those would be a
number about how ill somebody is -- which Nura does not get to decide.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import SymptomEntry, SymptomEpisode
from app.models.enums import SYMPTOM_ACTIVE_STATUSES
from app.services.symptoms import safety as safety_service

#: How many symptom rows Important Today will carry. Two: the section is a
#: glance, and medications already put up to three rows in it (PRD 3, s21).
MAX_IMPORTANT_ITEMS = 2

#: The window behind "symptoms updated this week" (PRD 6, section 48).
RECENT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class EpisodeSnapshot:
    """One active episode as a summary talks about it."""

    episode: SymptomEpisode
    #: The newest entry, or None for an episode created without one.
    latest: SymptomEntry | None
    #: The entry before that, which is what a severity comparison needs.
    previous: SymptomEntry | None
    #: Codes from ``safety.WORSENING_REASONS``. Empty unless the user recorded
    #: a change -- never inferred (PRD 6, section 41).
    worsening_reasons: tuple[str, ...] = ()

    @property
    def worsening(self) -> bool:
        return bool(self.worsening_reasons)

    @property
    def severity(self) -> int | None:
        return None if self.latest is None else self.latest.severity

    @property
    def change_state(self) -> str | None:
        return None if self.latest is None else self.latest.change_state

    @property
    def updated_at(self) -> datetime:
        return self.episode.updated_at


@dataclass(frozen=True)
class SymptomSummary:
    """Today's symptoms, as the dashboard talks about them."""

    active_count: int
    worsening_count: int
    recent_updates_count: int
    #: The active episode written about most recently -- the one an "Update"
    #: button should act on. None when nothing is active.
    most_recent: EpisodeSnapshot | None = None
    #: Ordered for Important Today: anything the user recorded as worsening.
    important: list[EpisodeSnapshot] = field(default_factory=list)
    #: False when this profile has never logged a symptom, which is what lets
    #: Today leave the card out entirely rather than showing an empty one
    #: (PRD 3, section 18).
    has_episodes: bool = False


def _snapshot(episode: SymptomEpisode) -> EpisodeSnapshot:
    """Pairs an episode with its two newest entries and assesses the change.

    ``episode.entries`` is ordered newest-first by the relationship, so no
    extra query is needed per episode.
    """
    entries = list(episode.entries)
    latest = entries[0] if entries else None
    previous = entries[1] if len(entries) > 1 else None
    assessment = safety_service.assess(latest, previous)
    return EpisodeSnapshot(
        episode=episode,
        latest=latest,
        previous=previous,
        worsening_reasons=assessment.reasons,
    )


def active_snapshots(db: Session, profile_id: uuid.UUID) -> list[EpisodeSnapshot]:
    """Every active or recurring episode, most recently updated first."""
    episodes = (
        db.execute(
            select(SymptomEpisode)
            .where(
                SymptomEpisode.profile_id == profile_id,
                SymptomEpisode.status.in_(SYMPTOM_ACTIVE_STATUSES),
            )
            .order_by(SymptomEpisode.updated_at.desc())
            .options(
                selectinload(SymptomEpisode.entries).selectinload(SymptomEntry.photos)
            )
        )
        .scalars()
        .all()
    )
    return [_snapshot(episode) for episode in episodes]


def recent_update_count(
    db: Session, profile_id: uuid.UUID, now: datetime, days: int = RECENT_WINDOW_DAYS
) -> int:
    """How many distinct episodes were written about in the last ``days``.

    Episodes, not entries: somebody who checked in on one headache five times
    has updated one symptom, and saying "5 symptoms updated this week" would be
    wrong in a way that matters (PRD 6, section 48).
    """
    since = now - timedelta(days=days)
    return int(
        db.execute(
            select(func.count(func.distinct(SymptomEntry.symptom_episode_id))).where(
                SymptomEntry.profile_id == profile_id,
                SymptomEntry.recorded_at >= since,
            )
        ).scalar_one()
    )


def has_any_episode(db: Session, profile_id: uuid.UUID) -> bool:
    """Whether this profile has ever logged a symptom."""
    return (
        db.execute(
            select(SymptomEpisode.id)
            .where(SymptomEpisode.profile_id == profile_id)
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def active_count(db: Session, profile_id: uuid.UUID) -> int:
    """Active and recurring episodes. The figure the Health overview shows."""
    return int(
        db.execute(
            select(func.count(SymptomEpisode.id)).where(
                SymptomEpisode.profile_id == profile_id,
                SymptomEpisode.status.in_(SYMPTOM_ACTIVE_STATUSES),
            )
        ).scalar_one()
    )


def build_summary(db: Session, profile_id: uuid.UUID, now: datetime) -> SymptomSummary:
    """Assembles the symptom part of Today.

    Reads only. Nothing is created, resolved or reassessed as a side effect of
    drawing a screen -- unlike medications, symptoms have no clock-driven state
    to bring up to date, because no symptom changes on its own.
    """
    snapshots = active_snapshots(db, profile_id)

    important = [snapshot for snapshot in snapshots if snapshot.worsening]
    important.sort(key=lambda snapshot: snapshot.updated_at, reverse=True)

    return SymptomSummary(
        active_count=len(snapshots),
        worsening_count=len(important),
        recent_updates_count=recent_update_count(db, profile_id, now),
        most_recent=snapshots[0] if snapshots else None,
        important=important[:MAX_IMPORTANT_ITEMS],
        has_episodes=has_any_episode(db, profile_id),
    )
