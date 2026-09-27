"""Symptom entries: one observation at one moment (PRD 6, sections 11, 47, 61).

The rule this file exists to keep is PRD 6 section 4's: **the manual form and
the guided conversation produce the same record.** There is one input shape,
one validator and one writer, and the only difference between the two flows is
the ``source`` the route sets -- which is an observation about how the data
arrived, not a different kind of data. There is deliberately no second table,
no "chat transcript" column and no place for a flow to stash something the
other flow cannot read.

Two other things are worth reading rather than skimming.

**A retry cannot create a second entry.** The client generates
``client_entry_id`` before it tries to send, so the id survives a failed
request, an app restart and a week offline. Sending it again returns the
existing row untouched. That is what makes the offline queue safe without a
server-side dedupe heuristic guessing whether two similar entries are the same
observation (PRD 6, section 61).

**A follow-up carries only what changed.** Nothing here copies the previous
entry's description forward, and nothing requires a field to be present. An
update that says "7/10, worse, and now nauseous" is a complete entry
(PRD 6, section 47).
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Profile, SymptomEntry, SymptomEpisode
from app.services.errors import NotFoundError

logger = logging.getLogger(__name__)

#: How many items one of the list fields may hold. Enough for a real answer --
#: nobody lists a dozen associated symptoms -- and small enough that the field
#: cannot become a place to keep a history.
MAX_LIST_ITEMS = 12

#: The most entries one request returns for an episode. A symptom checked twice
#: a day for a year is 700 entries; the detail screen shows the recent ones and
#: the history screen asks for more.
MAX_ENTRIES = 500


class EntryNotFoundError(NotFoundError):
    """No such entry for this profile, or not on this episode."""

    code = "symptom_entry_not_found"


def _log(action: str) -> None:
    """``symptom.entry.create success`` -- never a value (PRD 6, s62 and 65)."""
    logger.info("symptom.%s success", action)


def normalise_items(items: list[str] | None) -> list[str]:
    """Trims, drops blanks, and removes case-insensitive duplicates.

    Order is kept, and the first spelling wins: somebody who typed "Nausea" and
    then "nausea" meant one thing, and showing them back the capital they used
    is friendlier than normalising their words to lower case.

    A fresh list is always returned. SQLAlchemy does not track mutation inside
    a JSONB value, so every write here assigns rather than appends.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in items or []:
        value = raw.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= MAX_LIST_ITEMS:
            break
    return result


@dataclass
class EntryInput:
    """One observation, as either flow describes it.

    Every field is optional except the moment it is about, because a symptom
    description that has to be complete is one somebody abandons halfway
    (PRD 6, section 11).
    """

    recorded_at: datetime | None = None
    main_symptom: str | None = None
    site: str | None = None
    onset_text: str | None = None
    onset_at: datetime | None = None
    onset_date: date | None = None
    character: str | None = None
    radiation: str | None = None
    timing: str | None = None
    severity: int | None = None
    change_state: str | None = None
    free_text_note: str | None = None
    associated_symptoms: list[str] = field(default_factory=list)
    exacerbating_factors: list[str] = field(default_factory=list)
    relieving_factors: list[str] = field(default_factory=list)
    negated_items: list[str] = field(default_factory=list)
    uncertain_items: list[str] = field(default_factory=list)
    context_dependent_items: list[str] = field(default_factory=list)
    client_entry_id: str | None = None


# --- reading ----------------------------------------------------------------


def list_entries(
    db: Session, episode_id: uuid.UUID, limit: int = MAX_ENTRIES
) -> list[SymptomEntry]:
    """An episode's entries, newest first -- the order the history reads in."""
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


def get_entry(
    db: Session, profile_id: uuid.UUID, episode_id: uuid.UUID, entry_id: uuid.UUID
) -> SymptomEntry:
    """One entry, on this episode, of this profile's -- or a 404.

    All three conditions are part of the lookup. An entry id from somebody
    else's episode, or from another of this profile's episodes, answers the same
    way as one that does not exist (PRD 6, section 53).
    """
    entry = db.execute(
        select(SymptomEntry)
        .where(
            SymptomEntry.id == entry_id,
            SymptomEntry.symptom_episode_id == episode_id,
            SymptomEntry.profile_id == profile_id,
        )
        .options(selectinload(SymptomEntry.photos))
    ).scalar_one_or_none()
    if entry is None:
        raise EntryNotFoundError("Not found.")
    return entry


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_entry_id: str
) -> SymptomEntry | None:
    """The entry this client already created with this id, if any.

    Scoped to the profile, so one person's client id can never return
    another's entry however it was generated.
    """
    return db.execute(
        select(SymptomEntry)
        .where(
            SymptomEntry.profile_id == profile_id,
            SymptomEntry.client_entry_id == client_entry_id,
        )
        .options(selectinload(SymptomEntry.photos))
    ).scalar_one_or_none()


def latest_entry(db: Session, episode_id: uuid.UUID) -> SymptomEntry | None:
    entries = list_entries(db, episode_id, limit=1)
    return entries[0] if entries else None


# --- writing ----------------------------------------------------------------


def _apply(entry: SymptomEntry, data: EntryInput) -> None:
    entry.main_symptom = data.main_symptom
    entry.site = data.site
    entry.onset_text = data.onset_text
    entry.onset_at = data.onset_at
    entry.onset_date = data.onset_date
    entry.character = data.character
    entry.radiation = data.radiation
    entry.timing = data.timing
    entry.severity = data.severity
    entry.change_state = data.change_state
    entry.free_text_note = data.free_text_note
    entry.associated_symptoms = normalise_items(data.associated_symptoms)
    entry.exacerbating_factors = normalise_items(data.exacerbating_factors)
    entry.relieving_factors = normalise_items(data.relieving_factors)
    entry.negated_items = normalise_items(data.negated_items)
    entry.uncertain_items = normalise_items(data.uncertain_items)
    entry.context_dependent_items = normalise_items(data.context_dependent_items)


def create_entry(
    db: Session,
    profile: Profile,
    episode: SymptomEpisode,
    data: EntryInput,
    *,
    source: str,
    now: datetime,
    commit: bool = True,
) -> tuple[SymptomEntry, bool]:
    """Adds an observation. Returns the entry and whether it is a new one.

    The second value is False for a replay of a ``client_entry_id`` already
    stored. The existing row is returned exactly as it is -- a replay is not an
    edit, and letting one overwrite the stored entry would turn a retry into a
    way of silently rewriting history (PRD 6, section 61).

    Adding an update to a *resolved* episode does not reopen it. A symptom that
    has come back is a recurrence, which is its own deliberate action; quietly
    flipping a status because somebody added a note would be exactly the
    inference PRD 6 section 10 rules out.
    """
    if data.client_entry_id:
        existing = find_by_client_id(db, profile.id, data.client_entry_id)
        if existing is not None:
            return existing, False

    entry = SymptomEntry(
        profile_id=profile.id,
        symptom_episode_id=episode.id,
        recorded_at=data.recorded_at or now,
        source=source,
        client_entry_id=data.client_entry_id,
    )
    _apply(entry, data)
    db.add(entry)

    # Bump the episode so "most recently updated first" reflects the new entry
    # even when nothing about the episode itself changed.
    episode.updated_at = now

    if commit:
        db.commit()
        db.refresh(entry)
        _log("entry.create")
    else:
        db.flush()
    return entry, True


def update_entry(
    db: Session, entry: SymptomEntry, fields: dict[str, Any]
) -> SymptomEntry:
    """Applies the fields present in a PATCH and leaves the rest alone.

    Correcting an entry is a first-class action: PRD 6 section 30 requires the
    user to be able to fix what was captured, and section 67 says no answer
    becomes permanently locked. The list fields are normalised on the way in,
    exactly as on create.
    """
    lists = {
        "associated_symptoms",
        "exacerbating_factors",
        "relieving_factors",
        "negated_items",
        "uncertain_items",
        "context_dependent_items",
    }
    for name, value in fields.items():
        setattr(entry, name, normalise_items(value) if name in lists else value)
    db.commit()
    db.refresh(entry)
    _log("entry.update")
    return entry


def delete_entry(db: Session, entry: SymptomEntry) -> None:
    """Removes one observation, and the photos attached to it.

    Photo *objects* are removed by the caller first: the database cascade
    cannot reach into storage.
    """
    db.delete(entry)
    db.commit()
    _log("entry.delete")
