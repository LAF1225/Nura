"""Every sentence the daily-life features say.

PRD 12, sections 6, 9, 11, 17, 19, 22, 23, 24, 26, 27, 28, 33 and 45.

One module, for the reason PRD 7 gave and PRD 10 and PRD 11 repeated: a
sentence written in a route, in a service and in a robot builder is three
sentences that will eventually disagree. Everything below is a label a screen
shows, a sentence an assistant tool hands the model, or a line the robot draws,
and there is exactly one of each.

Four of these sentences are the honest ones, and they are the reason this file
matters more than its size suggests.

**The alarm sentence** (section 11). Nura has never fired an alarm on a phone.
``ALARM_LIMITATION`` says so, in the product, beside the switch -- not in a
changelog and not only in a completion report. Section 11 says that if only
notification-style alarms are supported they must be labelled honestly, and the
app has not even been run on a handset, so the label is stronger than that.

**The three external sentences** (sections 26, 27 and 28). Weather, news and an
external calendar are ``not_configured``, which is a state and not a mood: no
provider exists, nothing is fetched, and the sentence says the build does not
have it rather than apologising vaguely. Section 12's rule, which PRD 10 and
PRD 11 already live by.

**The medication sentence** (section 23). "Remind me to double my dose
tomorrow" is a request Nura answers by writing down a note and saying where
dose changes come from. The sentence is here, once, so neither the assistant
nor a screen can improvise a softer version of it.

**The clinical sentence** (section 24). Nura may remind somebody of a routine
they or their clinician decided on. It does not decide on one.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.models.enums import (
    ALARM_RECURRENCES,
    ALARM_SOUND_KEYS,
    DAILY_LIFE_CAPABILITY_KEYS,
    DAILY_LIFE_CAPABILITY_STATES,
    DAILY_LIFE_SOURCES,
    REMINDER_OCCURRENCE_STATUSES,
    REMINDER_RECURRENCES,
    REMINDER_STATUSES,
    ROUTINE_RUN_STATUSES,
    ROUTINE_SCHEDULE_TYPES,
    ROUTINE_STATUSES,
    ROUTINE_STEP_STATES,
    TASK_PRIORITIES,
    TASK_STATUSES,
)
from app.services.appointments.wording import (
    format_day,
    join_items,
    plural,
    relative_day,
)

# --- labels -----------------------------------------------------------------

TASK_STATUS_LABELS: dict[str, str] = {
    "open": "To do",
    "completed": "Done",
    "archived": "Archived",
    "cancelled": "Cancelled",
}
assert set(TASK_STATUS_LABELS) == set(TASK_STATUSES)

#: "Important" raises a row's prominence in a list. It is not an alert, it
#: notifies nobody, and section 18 is explicit that a daily-life item must
#: never obscure something safety-critical.
TASK_PRIORITY_LABELS: dict[str, str] = {
    "normal": "Normal",
    "important": "Important",
}
assert set(TASK_PRIORITY_LABELS) == set(TASK_PRIORITIES)

REMINDER_RECURRENCE_LABELS: dict[str, str] = {
    "one_time": "Once",
    "daily": "Every day",
    "selected_days": "On chosen days",
    "weekly": "Every week",
    "monthly": "Every month",
}
assert set(REMINDER_RECURRENCE_LABELS) == set(REMINDER_RECURRENCES)

REMINDER_STATUS_LABELS: dict[str, str] = {
    "active": "On",
    "paused": "Paused",
    "completed": "Finished",
    "cancelled": "Cancelled",
}
assert set(REMINDER_STATUS_LABELS) == set(REMINDER_STATUSES)

#: Section 8: *do not reuse medication Taken semantics*. These are the words a
#: reminder uses, and "Done" is as far as any of them goes -- nothing here
#: records that a person took anything.
OCCURRENCE_STATUS_LABELS: dict[str, str] = {
    "scheduled": "Coming up",
    "completed": "Done",
    "dismissed": "Dismissed",
    "snoozed": "Snoozed",
    "missed": "Not answered",
    "cancelled": "Cancelled",
}
assert set(OCCURRENCE_STATUS_LABELS) == set(REMINDER_OCCURRENCE_STATUSES)

ALARM_RECURRENCE_LABELS: dict[str, str] = {
    "one_time": "Once",
    "daily": "Every day",
    "selected_days": "On chosen days",
}
assert set(ALARM_RECURRENCE_LABELS) == set(ALARM_RECURRENCES)

#: Names, not sounds. **Nothing in this project has ever played one of these.**
ALARM_SOUND_LABELS: dict[str, str] = {
    "default": "Default",
    "gentle": "Gentle",
    "chime": "Chime",
    "bell": "Bell",
}
assert set(ALARM_SOUND_LABELS) == set(ALARM_SOUND_KEYS)

ROUTINE_SCHEDULE_LABELS: dict[str, str] = {
    "daily": "Every day",
    "selected_days": "On chosen days",
}
assert set(ROUTINE_SCHEDULE_LABELS) == set(ROUTINE_SCHEDULE_TYPES)

ROUTINE_STATUS_LABELS: dict[str, str] = {
    "active": "On",
    "paused": "Paused",
    "archived": "Archived",
}
assert set(ROUTINE_STATUS_LABELS) == set(ROUTINE_STATUSES)

ROUTINE_RUN_STATUS_LABELS: dict[str, str] = {
    "scheduled": "Coming up",
    "in_progress": "Started",
    "completed": "Done",
    "skipped": "Skipped",
    "missed": "Not done",
    "cancelled": "Cancelled",
}
assert set(ROUTINE_RUN_STATUS_LABELS) == set(ROUTINE_RUN_STATUSES)

ROUTINE_STEP_STATE_LABELS: dict[str, str] = {
    "completed": "Done",
    "skipped": "Skipped",
}
assert set(ROUTINE_STEP_STATE_LABELS) == set(ROUTINE_STEP_STATES)

#: Section 43. ``caregiver_suggestion`` is the one that has to stay visible:
#: somebody should be able to see that a routine came from the person helping
#: them, months later.
SOURCE_LABELS: dict[str, str] = {
    "user": "Added by you",
    "assistant": "Added by Nura",
    "caregiver_suggestion": "From a care request you approved",
    "import_future": "Imported",
}
assert set(SOURCE_LABELS) == set(DAILY_LIFE_SOURCES)

CAPABILITY_LABELS: dict[str, str] = {
    "tasks": "Tasks",
    "reminders": "Reminders",
    "alarms": "Alarms",
    "routines": "Routines",
    "weather": "Weather",
    "news": "News",
    "external_calendar": "External calendar",
}
assert set(CAPABILITY_LABELS) == set(DAILY_LIFE_CAPABILITY_KEYS)

CAPABILITY_STATE_LABELS: dict[str, str] = {
    "available": "Available",
    "not_configured": "Not set up in this build",
    "unavailable": "Not working right now",
}
assert set(CAPABILITY_STATE_LABELS) == set(DAILY_LIFE_CAPABILITY_STATES)


# --- the honest sentences ---------------------------------------------------

#: Section 11, and section 71's reality. Shown beside the alarm list and
#: returned by the alarm endpoints, so nobody has to read a completion report
#: to find out what an alarm in this build is.
ALARM_LIMITATION = (
    "Alarms are scheduled as phone notifications. Nura has never been run on a "
    "physical phone, so whether one actually wakes you has not been tested."
)

#: What the robot's alarm card says (PRD 12, section 65).
#:
#: The robot's speaker reports ``not_connected``, so a card that looked like an
#: alarm going off would be the robot claiming something it cannot do. Derived
#: from the capability map by the builder, which is why this line disappears on
#: its own if a chime capability ever appears.
ALARM_ROBOT_NOTE = "Nura cannot sound this"

#: Section 9. A reminder with notifications refused is still a reminder: it is
#: stored, it is on Today, and the screen says why it will be quiet.
NOTIFICATIONS_DISABLED = (
    "Notifications are turned off for Nura, so this will not make a sound. It "
    "will still be here and on your Today screen."
)

#: Sections 26, 27 and 28, close to the PRD's own words. Each one says what is
#: true of *this build* rather than of the world.
WEATHER_NOT_CONFIGURED = "Live weather is not configured in this build."
NEWS_NOT_CONFIGURED = "Live news access is not configured in this build."
EXTERNAL_CALENDAR_NOT_CONFIGURED = (
    "I can add that to Nura, but an external calendar is not connected."
)

#: Section 23. The daily-life tools must not become a way round the medical
#: safeguards, and this is what Nura says instead of doing that.
MEDICATION_CHANGE_BOUNDARY = (
    "I can create a general note, but medication dose changes should follow "
    "your clinician or pharmacist's instructions."
)

#: Section 24, and section 15. Nura reminds; it does not prescribe.
CLINICAL_ROUTINE_BOUNDARY = (
    "I can set up a routine you have decided on, or one a clinician has given "
    "you. I cannot work out an exercise or treatment routine from your "
    "symptoms."
)

#: Section 22. What Nura says when a write is not complete enough to do.
REMINDER_NEEDS_A_TIME = "A reminder needs a time. When should Nura remind you?"
TASK_NEEDS_A_TITLE = "A task needs a few words saying what it is."

#: Section 42. Said on the caregiver's own screen, so somebody helping knows
#: where the edge is rather than wondering why a list looks short.
CAREGIVER_ROUTINES_ONLY = (
    "Routines only. Tasks, alarms and personal reminders stay private."
)

#: There is deliberately **no** copy of PRD 11's "Use the Nura app to respond."
#: here. A daily-life card needs that sentence, and the robot builder takes it
#: from ``services.robot.wording`` where PRD 11 wrote it -- so the two say the
#: same thing without this module importing the robot package. Nothing outside
#: ``services/robot`` knows the robot exists, and a test walks every file under
#: ``app/services`` to keep it that way.

#: Empty states.
NO_TASKS = "Nothing on your list."
NO_REMINDERS = "No reminders set up."
NO_ALARMS = "No alarms set."
NO_ROUTINES = "No routines yet."
NO_RUN_TODAY = "Nothing scheduled today."


# --- sentences built from rows ----------------------------------------------

WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
WEEKDAY_SHORT = tuple(name[:3] for name in WEEKDAY_NAMES)

#: The two groupings worth naming rather than listing. Anything else is listed,
#: because "Mondays, Wednesdays and Fridays" is clearer than a clever name for
#: it.
_WEEKDAY_GROUPS = {
    (0, 1, 2, 3, 4): "Weekdays",
    (5, 6): "Weekends",
    (0, 1, 2, 3, 4, 5, 6): "Every day",
}


def format_clock(moment: time) -> str:
    """ "7:30 AM". A wall-clock time, with no zone attached to confuse it."""
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{hour}:{moment.minute:02d} {suffix}"


def weekday_label(weekdays: list[int] | None) -> str:
    """ "Weekdays", "Mondays and Fridays", or "Every day" for nothing at all."""
    if not weekdays:
        return "Every day"
    ordered = tuple(sorted(set(weekdays)))
    named = _WEEKDAY_GROUPS.get(ordered)
    if named is not None:
        return named
    return join_items([f"{WEEKDAY_NAMES[day]}s" for day in ordered])


def ordinal(value: int) -> str:
    """ "1st", "2nd", "31st" -- for a monthly reminder's day."""
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"


def recurrence_sentence(
    *,
    recurrence: str,
    time_of_day: time,
    weekdays: list[int] | None = None,
    day_of_month: int | None = None,
    start_date: date | None = None,
) -> str:
    """ "Every day at 7:30 AM", "The 1st of each month at 9:00 AM".

    One function for reminders, alarms and routines, because a person reading
    three screens should not have to learn three ways of writing the same
    thing.
    """
    at = f"at {format_clock(time_of_day)}"
    if recurrence == "one_time":
        when = format_day(start_date) if start_date is not None else "Once"
        return f"{when} {at}"
    if recurrence == "daily":
        return f"Every day {at}"
    if recurrence == "monthly" and day_of_month is not None:
        return f"The {ordinal(day_of_month)} of each month {at}"
    if recurrence == "weekly" and weekdays:
        return f"Every {WEEKDAY_NAMES[sorted(weekdays)[0]]} {at}"
    return f"{weekday_label(weekdays)} {at}"


def due_label(due_at: datetime | None, zone: str, today: date) -> str | None:
    """ "Today, 4:00 PM", "Tomorrow, 9:00 AM", "14 March, 9:00 AM".

    Null for a task with no due date, which is a normal task and not an
    incomplete one (section 5).
    """
    if due_at is None:
        return None
    local = due_at.astimezone(ZoneInfo(zone))
    day = relative_day(local.date(), today) or format_day(local.date())
    return f"{day}, {format_clock(local.time())}"


def overdue_sentence(count: int) -> str:
    """Stated, never scolded about. Section 18 keeps daily life below safety,
    and a task nobody got to is not an event."""
    if count == 0:
        return "Nothing overdue."
    return f"{plural(count, 'task')} past its due time."


def task_counts_sentence(due_today: int, overdue: int) -> str:
    """The Today card's line (section 19)."""
    if due_today == 0 and overdue == 0:
        return NO_TASKS
    parts = []
    if due_today:
        parts.append(f"{plural(due_today, 'task')} due today")
    if overdue:
        parts.append(f"{overdue} overdue")
    return ", ".join(parts) + "."


def today_summary_sentence(tasks: int, routines: int, reminders: int) -> str:
    """Section 19's example, as one sentence: "3 tasks, 1 routine, 2 reminders"."""
    parts = []
    if tasks:
        parts.append(plural(tasks, "task"))
    if routines:
        parts.append(plural(routines, "routine"))
    if reminders:
        parts.append(plural(reminders, "reminder"))
    if not parts:
        return "Nothing due today."
    return join_items(parts) + " today."


def progress_sentence(done: int, total: int) -> str:
    """ "2 of 3 complete" -- section 33's routine card, and the run screen."""
    return f"{done} of {total} complete"


def next_step_sentence(title: str) -> str:
    """ "Next: Stretch" (section 33)."""
    return f"Next: {title}"


def routine_run_sentence(*, done: int, total: int, next_title: str | None) -> str:
    """The whole progress line, for a list row and a robot card alike."""
    progress = progress_sentence(done, total)
    if next_title is None:
        return progress
    return f"{progress}. {next_step_sentence(next_title)}"


def capability_sentence(*, key: str, state: str) -> str:
    """ "Weather: not set up in this build" (sections 25 and 57).

    The three external keys get their own fuller sentence, because a person or
    a model asking about the weather deserves the reason rather than a label.
    """
    if state == "not_configured":
        specific = {
            "weather": WEATHER_NOT_CONFIGURED,
            "news": NEWS_NOT_CONFIGURED,
            "external_calendar": EXTERNAL_CALENDAR_NOT_CONFIGURED,
        }.get(key)
        if specific is not None:
            return specific
    return f"{CAPABILITY_LABELS[key]}: {CAPABILITY_STATE_LABELS[state].lower()}"
