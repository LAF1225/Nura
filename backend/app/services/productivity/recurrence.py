"""When a repeating daily-life thing happens next.

PRD 12, sections 7, 10, 12, 14, 35 and 36.

**This module decides nothing about daylight saving.** It calls
``services.medications.doses.occurrence_instant``, which is PRD 5's function
and carries PRD 5's two decisions: a wall-clock time that happens twice on an
autumn morning resolves to the first of them, and one that never happens on a
spring morning resolves through the pre-transition offset, so there is exactly
one instant either way -- never zero and never two. Section 35 asks for that
discipline to be reused rather than re-decided, and reuse here means the same
function rather than the same idea written twice.

**Everything in here is pure.** Nothing touches a database or a clock: a
recurrence and two dates go in, a list of moments comes out. That is what makes
the two daylight-saving days a year testable, which matters because they are
impossible to notice in use and easy to get wrong.

**Four recurrences, plus one-off, and no grammar** (section 7). The patterns
are named, the names are in ``REMINDER_RECURRENCES``, and there is no RRULE
parser anywhere: section 7 says to add arbitrary recurrence only if it is
thoroughly tested, and the thing to avoid most is a clever parser beside a
medication engine that already works.

**A monthly reminder on the 31st is the last day of a short month.** Decided
here, deterministically, rather than refused at the edge or silently skipped.
Section 35 asks for nonexistent local *times* to go through the existing
utility; a nonexistent local *date* is the same class of problem and gets the
same treatment -- one occurrence, at the nearest honest moment.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.models.enums import (
    REMINDER_RECURRENCES_WITH_WEEKDAYS,
    REMINDER_REPEATING_RECURRENCES,
)
from app.services.medications.doses import (
    Occurrence,
    local_today,
    occurrence_instant,
    zone_for,
)

#: How far ahead concrete occurrences are created. The same fortnight PRD 5
#: uses, for the same two reasons: a phone that has been offline for a week
#: still has notifications left to fire, and a reminder edit does not have to
#: rewrite months.
GENERATION_HORIZON_DAYS = 14

#: How long after its moment an unanswered reminder occurrence waits before it
#: counts as missed. PRD 5's grace period, reused: somebody who deals with a
#: reminder an hour late has not missed it, and a product that says they did is
#: both wrong and unkind. It is a bookkeeping threshold and nothing follows
#: from it -- no advice, no score, nothing anybody is told about.
MISS_AFTER = timedelta(hours=2)

#: How early an occurrence starts reading as due rather than upcoming. PRD 5's
#: lead, so a reminder and a dose at the same minute agree about the word.
DUE_LEAD = timedelta(minutes=30)

#: Re-exported so callers have one import for "resolve this zone" and
#: "what day is it there".
__all__ = [
    "DUE_LEAD",
    "GENERATION_HORIZON_DAYS",
    "MISS_AFTER",
    "MONTH_LENGTHS",
    "Occurrence",
    "Pattern",
    "day_in_month",
    "local_today",
    "matches",
    "occurrence_instant",
    "occurrences",
    "zone_for",
]

MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        return 29
    return MONTH_LENGTHS[month - 1]


def day_in_month(year: int, month: int, requested: int) -> int:
    """The requested day of the month, or that month's last day.

    "The 31st, every month" means the 30th in April and the 28th in February.
    One occurrence, at the end of the month, rather than eleven months with a
    reminder and one without -- which is what skipping would mean, and what
    somebody who set a month-end reminder would least expect.
    """
    return min(requested, _days_in_month(year, month))


@dataclass(frozen=True)
class Pattern:
    """A recurrence, flattened out of whichever row it came from.

    A reminder, an alarm and a routine have the same question to answer -- does
    this happen on that day, and at what instant -- out of three different sets
    of columns. Flattening them into this keeps one implementation of the
    answer rather than three that drift.

    ``day_of_month`` is only ever set by a reminder; an alarm and a routine have
    no monthly pattern (sections 10 and 12).
    """

    recurrence: str
    timezone: str
    start_date: date
    time_of_day: time
    end_date: date | None = None
    weekdays: Sequence[int] | None = None
    day_of_month: int | None = None

    @property
    def repeats(self) -> bool:
        return self.recurrence in REMINDER_REPEATING_RECURRENCES


def matches(pattern: Pattern, on_date: date) -> bool:
    """Whether this pattern produces something on that local date.

    The date range is checked by the caller, because a one-off reminder whose
    date has gone is a different thing from one that does not repeat on
    Tuesdays, and the caller is the one that cares which.
    """
    if pattern.recurrence == "one_time":
        return on_date == pattern.start_date
    if pattern.recurrence == "daily":
        return True
    if pattern.recurrence in REMINDER_RECURRENCES_WITH_WEEKDAYS:
        # A pattern with no weekdays produces nothing, which is correct: "on no
        # days" is no occurrences. The database CHECK makes this unreachable
        # for a stored row, and it stays here because a Pattern can also be
        # built in a test or by a caller that has not read the constraint.
        weekdays = pattern.weekdays
        return weekdays is not None and on_date.weekday() in set(weekdays)
    if pattern.recurrence == "monthly":
        requested = pattern.day_of_month
        if requested is None:
            return False
        return on_date.day == day_in_month(on_date.year, on_date.month, requested)
    return False


def occurrences(pattern: Pattern, from_date: date, to_date: date) -> Iterator[Occurrence]:
    """Every moment this pattern produces between two local dates, inclusive.

    Local dates in the pattern's own zone, which is the whole point: "from the
    4th to the 18th" is fourteen of the person's days, not a UTC window that
    cuts an evening reminder into tomorrow.
    """
    zone = zone_for(pattern.timezone)
    start = max(from_date, pattern.start_date)
    end = to_date if pattern.end_date is None else min(to_date, pattern.end_date)

    current = start
    while current <= end:
        if matches(pattern, current):
            yield Occurrence(
                local_date=current,
                scheduled_for=occurrence_instant(current, pattern.time_of_day, zone),
            )
        current += timedelta(days=1)


def next_occurrence(
    pattern: Pattern, now: datetime, horizon_days: int = 366
) -> datetime | None:
    """The first moment at or after ``now``, or None within the horizon.

    Used for an alarm, which has no occurrence rows at all: there is nothing
    worth keeping about last Tuesday's 7am, so "when does this next go off" is
    derived from the stored time and the clock the same way a robot's
    connection status is derived rather than stored.
    """
    zone = zone_for(pattern.timezone)
    today = local_today(zone, now)
    for occurrence in occurrences(pattern, today, today + timedelta(days=horizon_days)):
        if occurrence.scheduled_for >= now:
            return occurrence.scheduled_for
    return None
