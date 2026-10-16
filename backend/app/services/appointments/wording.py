"""Formatting primitives for report text (PRD 7, sections 14, 16 and 26).

Dates, times, counts and lists. Nothing here decides *what* to say -- that is
``snapshot.py`` -- and nothing here reads the database.

**Why these are hand-rolled rather than ``strftime``.** Two reasons, both about
determinism. ``%B`` and ``%p`` are locale-dependent, so the same report would
render differently on a server with a different locale; and ``%-d`` (a day
without a leading zero) is not available on Windows at all, which is where this
project is developed. A fixed English month table produces the same string
everywhere, which is what PRD 7's determinism criterion needs.

The consequence, stated plainly: report text is English only. Translating it is
a later piece of work, and it will start here.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

MONTHS_SHORT = tuple(month[:3] for month in MONTHS)


def format_day(value: date) -> str:
    """ "2 October 2026"."""
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def format_day_short(value: date) -> str:
    """ "2 Oct 2026", for places where space is tight."""
    return f"{value.day} {MONTHS_SHORT[value.month - 1]} {value.year}"


def format_range(start: date, end: date) -> str:
    """ "1 September to 2 October 2026", dropping what is repeated.

    A range inside one month reads "1 to 14 September 2026"; one inside one year
    drops the first year; one that crosses a new year keeps both.
    """
    if start == end:
        return format_day(start)
    if start.year != end.year:
        return f"{format_day(start)} to {format_day(end)}"
    if start.month == end.month:
        return f"{start.day} to {end.day} {MONTHS[end.month - 1]} {end.year}"
    return f"{start.day} {MONTHS[start.month - 1]} to {format_day(end)}"


def format_clock(moment: datetime, zone: ZoneInfo) -> str:
    """ "3:30 PM", in the given zone."""
    local = moment.astimezone(zone)
    hour = local.hour % 12 or 12
    meridiem = "AM" if local.hour < 12 else "PM"
    return f"{hour}:{local.minute:02d} {meridiem}"


def format_moment(moment: datetime, zone: ZoneInfo) -> str:
    """ "2 October 2026, 3:30 PM", in the given zone."""
    local = moment.astimezone(zone)
    return f"{format_day(local.date())}, {format_clock(moment, zone)}"


def relative_day(target: date, today: date) -> str | None:
    """ "Today", "Tomorrow", "Yesterday", or None for anything further off.

    Only the three days a person thinks of by name. Anything else gets a date,
    because "in 4 days" makes somebody count and a date does not.
    """
    delta = (target - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    return None


def when_label(moment: datetime, zone: ZoneInfo, today: date) -> str:
    """ "Tomorrow at 3:30 PM", or "2 October 2026 at 3:30 PM".

    Computed on the server, which is unusual for a display string and
    deliberate: the moment has to be shown in the *appointment's* own zone
    (PRD 7, section 42), and the server is where the time zone database is.
    """
    local = moment.astimezone(zone)
    named = relative_day(local.date(), today)
    day = named or format_day(local.date())
    return f"{day} at {format_clock(moment, zone)}"


def plural(count: int, singular: str, many: str | None = None) -> str:
    """ "1 entry" / "6 entries". No "1 entries", ever."""
    word = singular if count == 1 else (many or f"{singular}s")
    return f"{count} {word}"


def join_items(items: list[str]) -> str:
    """ "rest", "rest and walking", "rest, walking and heat".

    Oxford comma deliberately absent: this is read aloud as often as it is read.
    """
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return f"{', '.join(cleaned[:-1])} and {cleaned[-1]}"


def capitalise(text: str) -> str:
    """Raises the first letter and leaves the rest of the user's words alone.

    ``str.capitalize`` lowercases everything after the first character, which
    would turn "MRI scan" into "Mri scan".
    """
    return text[:1].upper() + text[1:] if text else text
