"""Tasks (PRD 12, sections 5, 6, 18, 37, 40, 44 and 45).

**A task may have no time at all.** That is the common case -- "pick up the
prescription" -- and it is why a task is not a reminder with a different name:
there is nothing to fire, nothing to snooze, and no occurrence row. Section 4
keeps the two apart and this module is one half of that.

**Completion preserves history** (section 6). Done sets a status and a
timestamp; Undo clears both; Archive and Cancel keep the row. Deleting is a
separate, explicit act for a task somebody entered by mistake, and the API
makes the user choose which they meant.

**Two timestamps, because two devices** (section 40). A task edit is compared
against ``content_updated_at`` and a status change against
``status_changed_at``, so a title edit that was typed on a tablet an hour ago
cannot arrive and undo a completion made on a phone since. The alternative --
one ``updated_at`` and last-write-wins -- is the thing section 40 says not to
rely on without documenting the consequences, and the consequence it would have
is exactly the one the section names.

**A retry is free** (section 37). ``client_task_id`` is unique per profile, so
an offline draft sent twice is one task: the second send finds the first and
says it did.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task
from app.models.enums import TASK_OPEN_STATUSES, TASK_PRIORITIES
from app.services.errors import DomainError, NotFoundError
from app.services.medications.doses import local_today, zone_for

logger = logging.getLogger(__name__)

#: How many open tasks one profile may hold. Archived and completed ones do not
#: count, so somebody who uses Nura for years never meets this; it is here so a
#: broken client cannot fill the table.
MAX_OPEN_TASKS = 500

#: Fields a client may set. Everything else -- the status, its timestamps, the
#: provenance -- is the server's own (section 74).
EDITABLE_FIELDS = frozenset({"title", "notes", "priority", "due_at", "timezone"})


class TaskNotFoundError(NotFoundError):
    """No such task for this profile. The same answer as somebody else's."""

    code = "task_not_found"


class TooManyTasksError(DomainError):
    status_code = 409
    code = "too_many_tasks"


class InvalidTaskError(DomainError):
    status_code = 422
    code = "invalid_task"


def _log(action: str) -> None:
    """``task.create success`` -- section 45's own example, and nothing more.

    No title and no notes, ever. A task title is the user's own words, and
    section 45 rules out putting user-entered task text in a general
    application log. Section 46 wants the analytics event to be just as
    generic.
    """
    logger.info("task.%s success", action)


# --- reading ----------------------------------------------------------------


def get_task(db: Session, profile_id: uuid.UUID, task_id: uuid.UUID) -> Task:
    """One task of this profile's, or a 404 that confirms nothing.

    The profile is part of the lookup rather than checked afterwards, so there
    is no path that loads a task first and authorizes it second (section 74).
    """
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.profile_id == profile_id)
    ).scalar_one_or_none()
    if task is None:
        raise TaskNotFoundError("Not found.")
    return task


def find_by_client_id(
    db: Session, profile_id: uuid.UUID, client_task_id: str | None
) -> Task | None:
    """A task this client already created, if any (section 37)."""
    if not client_task_id:
        return None
    return db.execute(
        select(Task).where(
            Task.profile_id == profile_id, Task.client_task_id == client_task_id
        )
    ).scalar_one_or_none()


def list_tasks(
    db: Session,
    profile_id: uuid.UUID,
    *,
    scope: str | None = None,
    limit: int | None = None,
) -> list[Task]:
    """This profile's tasks, in the order the scope wants them.

    ``open`` is due soonest first with undated tasks last, because a list of
    things to do is read from the top. ``completed`` and ``archived`` read
    backwards, because history does.

    A task with no due date sorts after every dated one rather than before:
    ``due_at`` is nullable and ``nulls_last`` says so explicitly instead of
    leaving it to the database's default, which differs by direction.
    """
    query = select(Task).where(Task.profile_id == profile_id)

    if scope == "open":
        query = query.where(Task.status.in_(TASK_OPEN_STATUSES)).order_by(
            Task.due_at.asc().nulls_last(), Task.created_at.asc()
        )
    elif scope == "completed":
        query = query.where(Task.status == "completed").order_by(
            Task.completed_at.desc().nulls_last()
        )
    elif scope == "archived":
        query = query.where(Task.status.in_(("archived", "cancelled"))).order_by(
            Task.updated_at.desc()
        )
    else:
        query = query.order_by(Task.due_at.asc().nulls_last(), Task.created_at.asc())

    if limit is not None:
        query = query.limit(limit)
    return list(db.execute(query).scalars().all())


def due_today(db: Session, profile_id: uuid.UUID, on_date: date) -> list[Task]:
    """Open tasks whose due day is this one, in the person's own calendar.

    Filtered on ``due_local_date`` rather than on the instant, so "due today"
    means the day they chose and a task due at eleven at night does not fall
    into tomorrow (section 36).
    """
    return list(
        db.execute(
            select(Task)
            .where(
                Task.profile_id == profile_id,
                Task.status.in_(TASK_OPEN_STATUSES),
                Task.due_local_date == on_date,
            )
            .order_by(Task.due_at.asc().nulls_last())
        )
        .scalars()
        .all()
    )


def overdue(db: Session, profile_id: uuid.UUID, now: datetime) -> list[Task]:
    """Open tasks whose due instant has passed.

    Nothing is inferred from this. A task does not become ``missed``; there is
    no such status, because nobody needs an app to tell them a job is late and
    section 18 keeps daily life well below anything safety-critical.
    """
    return list(
        db.execute(
            select(Task)
            .where(
                Task.profile_id == profile_id,
                Task.status.in_(TASK_OPEN_STATUSES),
                Task.due_at.is_not(None),
                Task.due_at < now,
            )
            .order_by(Task.due_at.asc())
        )
        .scalars()
        .all()
    )


def is_overdue(task: Task, now: datetime) -> bool:
    """Derived on every read, never stored -- a value meaning "right now"."""
    return (
        task.status in TASK_OPEN_STATUSES
        and task.due_at is not None
        and task.due_at < now
    )


# --- writing ----------------------------------------------------------------


@dataclass(frozen=True)
class TaskInput:
    """What a client may say when creating a task."""

    title: str
    notes: str | None = None
    priority: str = "normal"
    due_at: datetime | None = None
    #: The zone the due date was chosen in. Defaults to UTC, which is only
    #: right by accident, so every client sends its own.
    timezone: str = "UTC"
    client_task_id: str | None = None
    #: Set by the server from how the write arrived, never from a request body
    #: (section 74).
    source: str = "user"


def _local_date_for(due_at: datetime | None, timezone: str) -> date | None:
    """The calendar day a due instant belongs to, where it was set.

    Stored beside the instant so "due today" is one indexed comparison, and so
    a task keeps the day it was meant for even if the person travels -- which
    is section 36's policy stated as a column rather than as a convention.
    """
    if due_at is None:
        return None
    return due_at.astimezone(zone_for(timezone)).date()


def _check(data: TaskInput) -> None:
    if not data.title.strip():
        raise InvalidTaskError("A task needs a title.")
    if data.priority not in TASK_PRIORITIES:
        raise InvalidTaskError("That is not a priority Nura has.")
    # Resolves the zone, so a bad name is refused here rather than at the first
    # render. ``zone_for`` raises the shared ``unknown_timezone``.
    zone_for(data.timezone)


def _open_count(db: Session, profile_id: uuid.UUID) -> int:
    rows = db.execute(
        select(Task.id).where(
            Task.profile_id == profile_id, Task.status.in_(TASK_OPEN_STATUSES)
        )
    ).all()
    return len(rows)


def create_task(
    db: Session, profile_id: uuid.UUID, data: TaskInput, now: datetime
) -> Task:
    """Adds a task (sections 5 and 6).

    Not idempotent by itself: the route checks ``client_task_id`` first and
    returns the stored task if it finds one, the same shape PRD 7's appointment
    route uses. Keeping the check there rather than here means a caller that
    genuinely wants two identical tasks -- two "call the pharmacy" on different
    days -- can have them.
    """
    _check(data)
    if _open_count(db, profile_id) >= MAX_OPEN_TASKS:
        raise TooManyTasksError("There are too many tasks on this list already.")

    task = Task(
        profile_id=profile_id,
        title=data.title.strip(),
        notes=(data.notes or None),
        status="open",
        priority=data.priority,
        due_at=data.due_at,
        due_local_date=_local_date_for(data.due_at, data.timezone),
        timezone=data.timezone,
        source=data.source,
        client_task_id=data.client_task_id,
        content_updated_at=now,
        status_changed_at=now,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    _log("create")
    return task


def update_task(
    db: Session,
    task: Task,
    fields: dict[str, Any],
    now: datetime,
    *,
    client_updated_at: datetime | None = None,
) -> tuple[Task, bool]:
    """Edits the content of a task, and says whether the edit was applied.

    ``applied`` is False when the stored content is newer than this edit. That
    is section 40's deterministic rule, applied to *content only*: the
    comparison is against ``content_updated_at``, so an edit arriving from a
    phone that was offline cannot reach the status at all -- not to change it,
    and not to resurrect a completed task by touching its title.

    A client that loses the comparison gets the stored task back and adopts it,
    which is the same convergence PRD 3's check-in and PRD 5's dose actions
    use.
    """
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise InvalidTaskError(f"A task has no {sorted(unknown)[0]}.")

    if (
        client_updated_at is not None
        and task.content_updated_at is not None
        and client_updated_at < task.content_updated_at
    ):
        return task, False

    if "title" in fields:
        title = str(fields["title"] or "").strip()
        if not title:
            raise InvalidTaskError("A task needs a title.")
        task.title = title
    if "notes" in fields:
        task.notes = fields["notes"] or None
    if "priority" in fields:
        if fields["priority"] not in TASK_PRIORITIES:
            raise InvalidTaskError("That is not a priority Nura has.")
        task.priority = fields["priority"]
    if "timezone" in fields and fields["timezone"]:
        zone_for(fields["timezone"])
        task.timezone = fields["timezone"]
    if "due_at" in fields:
        task.due_at = fields["due_at"]
        task.due_local_date = _local_date_for(task.due_at, task.timezone)
    elif "timezone" in fields:
        # The instant did not move, but the day it belongs to may have.
        task.due_local_date = _local_date_for(task.due_at, task.timezone)

    task.content_updated_at = client_updated_at or now
    db.commit()
    db.refresh(task)
    _log("update")
    return task, True


def _set_status(
    db: Session,
    task: Task,
    status: str,
    now: datetime,
    *,
    client_updated_at: datetime | None,
) -> tuple[Task, bool]:
    """The one place a task's status changes.

    Idempotent: asking for the status it already has returns it untouched, so a
    retried Done leaves one completed task with its original timestamp rather
    than pushing the moment forward.
    """
    if (
        client_updated_at is not None
        and task.status_changed_at is not None
        and client_updated_at < task.status_changed_at
    ):
        return task, False
    if task.status == status:
        return task, False

    moment = client_updated_at or now
    task.status = status
    task.status_changed_at = moment
    # Each timestamp belongs to the status that sets it, and reopening clears
    # all three: a task that is open again has not been completed, archived or
    # cancelled, and leaving a stale timestamp behind would make the history
    # read as though it had.
    task.completed_at = moment if status == "completed" else None
    task.archived_at = moment if status == "archived" else None
    task.cancelled_at = moment if status == "cancelled" else None
    db.commit()
    db.refresh(task)
    _log(status)
    return task, True


def complete_task(
    db: Session, task: Task, now: datetime, *, client_updated_at: datetime | None = None
) -> tuple[Task, bool]:
    """Marks a task done, once (section 6)."""
    return _set_status(db, task, "completed", now, client_updated_at=client_updated_at)


def reopen_task(
    db: Session, task: Task, now: datetime, *, client_updated_at: datetime | None = None
) -> tuple[Task, bool]:
    """Undo (section 6). Clears the completion rather than adding a second row."""
    return _set_status(db, task, "open", now, client_updated_at=client_updated_at)


def archive_task(
    db: Session, task: Task, now: datetime, *, client_updated_at: datetime | None = None
) -> tuple[Task, bool]:
    """Puts a task out of the way and keeps it (section 6)."""
    return _set_status(db, task, "archived", now, client_updated_at=client_updated_at)


def cancel_task(
    db: Session, task: Task, now: datetime, *, client_updated_at: datetime | None = None
) -> tuple[Task, bool]:
    """Records that a task is not happening, and keeps it."""
    return _set_status(db, task, "cancelled", now, client_updated_at=client_updated_at)


def delete_task(db: Session, task: Task) -> None:
    """Removes a task entirely. For one entered by mistake.

    The app asks which the person meant before calling this, because archiving
    is what somebody usually wants and a deleted task cannot be got back.
    """
    db.delete(task)
    db.commit()
    _log("delete")


def today_date(timezone: str, now: datetime) -> date:
    """The calendar date it is in that zone -- a convenience for the routes."""
    return local_today(zone_for(timezone), now)
