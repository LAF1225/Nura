"""The counts Today and Care read (PRD 12, sections 18, 19, 20 and 58).

Assembled once, here, for the reason ``services.today`` exists at all: a screen
that made four requests to count four things would fill in piece by piece, and
two screens that counted the same things separately would eventually disagree.

**Daily life sits below everything medical, by construction.** Section 18 gives
Today's order and section 18's last line is the rule: *daily-life items must
never obscure safety-critical items.* So ``important_items`` returns daily-life
rows in section 18's own relative order -- an important task, then a routine,
then a reminder, then an ordinary task -- and ``services.today`` appends that
list *after* medications and appointments. The ordering is not re-decided in
the route, and nothing in this module can put a task above a dose.

**Reading brings the day up to date.** ``build_summary`` replenishes reminder
occurrences and routine runs before counting them, which is the same choice
PRD 5 made for doses: opening the app is the commonest moment for yesterday's
occurrences to need recording, and it is why section 63's maintenance script is
optional for correctness.

**Nothing here is a judgement.** "Three tasks due today, one overdue" is a
count. There is no streak, no score, no percentage and nothing that reads as
praise or reproach -- the same discipline PRD 3 set for the check-in and PRD 5
for adherence.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.models import GeneralReminderOccurrence, RoutineRun, Task
from app.models.enums import TASK_OPEN_STATUSES
from app.services.productivity import alarms as alarm_service
from app.services.productivity import reminders as reminder_service
from app.services.productivity import routines as routine_service
from app.services.productivity import tasks as task_service


@dataclass(frozen=True)
class TaskCounts:
    """What Today says about tasks (section 58)."""

    due_today: int
    overdue: int
    open_total: int


@dataclass(frozen=True)
class ReminderCounts:
    due_today: int
    #: Occurrences waiting for an answer right now. A subset of ``due_today``
    #: plus anything still unanswered from earlier.
    due_now: int


@dataclass(frozen=True)
class RoutineCounts:
    due_today: int
    in_progress: int
    completed_today: int


@dataclass(frozen=True)
class TaskSnapshot:
    task: Task
    overdue: bool


@dataclass(frozen=True)
class ReminderSnapshot:
    occurrence: GeneralReminderOccurrence
    #: ``due`` or ``overdue`` -- the only two that reach Today.
    window: str


@dataclass(frozen=True)
class RunSnapshot:
    run: RoutineRun
    progress: routine_service.RunProgress


@dataclass(frozen=True)
class DailyLifeSummary:
    """Everything Today and Care need about daily life, in one read."""

    local_date: date
    tasks: TaskCounts
    reminders: ReminderCounts
    routines: RoutineCounts
    #: The next alarm, so the Care card can say when it is. Null when there is
    #: no enabled alarm ahead.
    next_alarm_at: datetime | None = None
    alarm_count: int = 0
    #: Section 18's rows, already in section 18's order.
    important_tasks: list[TaskSnapshot] = field(default_factory=list)
    important_runs: list[RunSnapshot] = field(default_factory=list)
    important_reminders: list[ReminderSnapshot] = field(default_factory=list)

    @property
    def has_anything(self) -> bool:
        """Whether this person uses daily life at all.

        What lets the Today card stay invisible for somebody who has never
        made a task -- the same choice the symptoms card makes, and the reason
        Today opens calm (PRD 3, section 3).
        """
        return (
            self.tasks.open_total > 0
            or self.reminders.due_today > 0
            or self.routines.due_today > 0
            or self.alarm_count > 0
        )


def build_summary(
    db: Session, profile_id: uuid.UUID, local_date: date, now: datetime
) -> DailyLifeSummary:
    """Assembles the counts, bringing occurrences and runs up to date first."""
    reminder_service.replenish(db, profile_id, now)
    routine_service.replenish(db, profile_id, now)

    open_tasks = task_service.list_tasks(db, profile_id, scope="open")
    due_tasks = [task for task in open_tasks if task.due_local_date == local_date]
    overdue_tasks = [task for task in open_tasks if task_service.is_overdue(task, now)]

    occurrences = reminder_service.list_occurrences(
        db, profile_id, from_date=local_date, to_date=local_date
    )
    due_now = reminder_service.due_occurrences(db, profile_id, now)

    runs = routine_service.runs_for_today(db, profile_id, now)
    open_runs = [run for run in runs if run.status in ("scheduled", "in_progress")]

    fires = alarm_service.upcoming_fires(db, profile_id, now, days=7)
    enabled_alarms = alarm_service.list_alarms(db, profile_id, enabled_only=True)

    # Overdue first inside each group, then by time, which is how somebody
    # reads a list of things they have not got to.
    def _task_key(task: Task) -> tuple[int, datetime | date | str]:
        return (0 if task_service.is_overdue(task, now) else 1, task.due_at or local_date)

    important_tasks = sorted(
        {task.id: task for task in [*overdue_tasks, *due_tasks]}.values(), key=_task_key
    )

    return DailyLifeSummary(
        local_date=local_date,
        tasks=TaskCounts(
            due_today=len(due_tasks),
            overdue=len(overdue_tasks),
            open_total=len(open_tasks),
        ),
        reminders=ReminderCounts(
            due_today=len(occurrences),
            due_now=len(due_now),
        ),
        routines=RoutineCounts(
            due_today=len(runs),
            in_progress=sum(1 for run in runs if run.status == "in_progress"),
            completed_today=sum(1 for run in runs if run.status == "completed"),
        ),
        next_alarm_at=fires[0].fire_at if fires else None,
        alarm_count=len(enabled_alarms),
        important_tasks=[
            TaskSnapshot(task=task, overdue=task_service.is_overdue(task, now))
            for task in important_tasks
        ],
        important_runs=[
            RunSnapshot(run=run, progress=routine_service.progress(run))
            for run in open_runs
        ],
        important_reminders=[
            ReminderSnapshot(
                occurrence=occurrence, window=reminder_service.window(occurrence, now)
            )
            for occurrence in due_now
        ],
    )


def open_task_count(db: Session, profile_id: uuid.UUID) -> int:
    """Just the one number, for a screen that needs nothing else."""
    return len(
        [
            task
            for task in task_service.list_tasks(db, profile_id, scope="open")
            if task.status in TASK_OPEN_STATUSES
        ]
    )
