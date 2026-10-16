"""Which stretch of time a report covers, and why (PRD 7, section 14).

PRD 7 prefers "since the previous appointment with the same clinician" and falls
back to the last 30 days. Both halves of that need care.

**"The same clinician" means the same linked clinician record.** Two
appointments whose titles both say "cardiology" are not evidence of the same
doctor, and setting a report period from a coincidence of wording would be
worse than the fallback. So the preference applies only when the appointment
points at a clinician the user chose from their own list.

**The fallback is recorded, not silent.** ``preset`` says what was actually
applied and ``fallback_reason`` says why, so the app can tell somebody their
report covers the last 30 days *because* Nura has no earlier visit with that
clinician -- rather than showing a range they did not ask for and cannot explain
(section 14's "Show the selected range clearly").

**A period never runs past today.** There are no records in the future, and a
report whose header claims to cover next week would be stating something it
cannot know.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import Appointment
from app.services.appointments import appointments as appointment_service
from app.services.appointments.wording import format_day, format_range
from app.services.errors import DomainError

#: Days behind the end date, per preset.
PRESET_DAYS = {"7_days": 7, "30_days": 30, "90_days": 90}

#: What "since my last visit" becomes when there is no last visit.
FALLBACK_PRESET = "30_days"

#: The longest period a report may cover. Two years is far more than any visit
#: needs and stops a custom range from turning a report into an export of
#: somebody's entire history.
MAX_PERIOD_DAYS = 730


class InvalidPeriodError(DomainError):
    status_code = 422
    code = "invalid_report_period"


@dataclass(frozen=True)
class ReportPeriod:
    """A resolved period, and the story of how it was resolved."""

    start: date
    end: date
    #: The preset actually applied -- which is not always the one requested.
    preset: str
    #: What the client asked for, kept so the app can show its own choice
    #: selected even when the answer came out differently.
    requested_preset: str
    #: "1 September to 2 October 2026". Shown wherever the period is
    #: (PRD 7, section 14).
    label: str
    #: ``no_linked_clinician`` or ``no_previous_visit`` when "since my last
    #: visit" could not be honoured, otherwise None.
    fallback_reason: str | None = None
    #: The previous visit this period runs from, when there was one.
    previous_visit_date: date | None = None

    @property
    def days(self) -> int:
        """Inclusive length, so a single day is 1."""
        return (self.end - self.start).days + 1


def _end_date(appointment: Appointment, today: date) -> date:
    """The last day a report covers.

    The appointment's own day, or today, whichever comes first: preparing for
    Thursday's appointment on Tuesday covers up to Tuesday, and writing a report
    a month after a visit covers up to the visit rather than up to now.
    """
    return min(today, appointment_service.local_date(appointment))


def resolve(
    db: Session,
    appointment: Appointment,
    *,
    preset: str,
    today: date,
    start: date | None = None,
    end: date | None = None,
) -> ReportPeriod:
    """Works out the period, applying PRD 7 section 14's preference and fallback."""
    if preset == "custom":
        return _custom(start, end, today)

    period_end = _end_date(appointment, today)

    if preset == "since_last_visit":
        previous = appointment_service.previous_visit(
            db, appointment.profile_id, appointment
        )
        if previous is None:
            reason = (
                "no_linked_clinician"
                if appointment.clinician_id is None
                else "no_previous_visit"
            )
            return _preset_period(
                FALLBACK_PRESET,
                period_end,
                requested_preset=preset,
                fallback_reason=reason,
            )

        previous_day = appointment_service.local_date(previous)
        period_start = min(previous_day, period_end)
        if (period_end - period_start).days + 1 > MAX_PERIOD_DAYS:
            period_start = period_end - timedelta(days=MAX_PERIOD_DAYS - 1)
        return ReportPeriod(
            start=period_start,
            end=period_end,
            preset=preset,
            requested_preset=preset,
            label=format_range(period_start, period_end),
            previous_visit_date=previous_day,
        )

    if preset not in PRESET_DAYS:
        raise InvalidPeriodError("That is not a report period Nura understands.")
    return _preset_period(preset, period_end, requested_preset=preset)


def _preset_period(
    preset: str,
    end: date,
    *,
    requested_preset: str,
    fallback_reason: str | None = None,
) -> ReportPeriod:
    days = PRESET_DAYS[preset]
    # Inclusive: "the last 7 days" is today and the six before it, matching how
    # the check-in window is counted (PRD 3, section 12).
    start = end - timedelta(days=days - 1)
    return ReportPeriod(
        start=start,
        end=end,
        preset=preset,
        requested_preset=requested_preset,
        label=format_range(start, end),
        fallback_reason=fallback_reason,
    )


def _custom(start: date | None, end: date | None, today: date) -> ReportPeriod:
    """A range the user typed. Both ends required, and neither in the future."""
    if start is None or end is None:
        raise InvalidPeriodError("A custom period needs a start and an end date.")
    if start > end:
        raise InvalidPeriodError("The period cannot end before it starts.")

    # Clamped rather than refused: somebody picking "to the end of the month"
    # means "up to whatever there is", and refusing would be a dead end.
    clamped_end = min(end, today)
    if start > clamped_end:
        raise InvalidPeriodError("That period has not happened yet.")
    if (clamped_end - start).days + 1 > MAX_PERIOD_DAYS:
        raise InvalidPeriodError("That period is too long for one report.")

    return ReportPeriod(
        start=start,
        end=clamped_end,
        preset="custom",
        requested_preset="custom",
        label=format_range(start, clamped_end),
    )


def describe_fallback(period: ReportPeriod) -> str | None:
    """One sentence explaining a period the user did not choose, or None.

    Shown next to the range on the preparation screen. It says what Nura does
    not know, which is the honest version of "we picked something else".
    """
    if period.fallback_reason == "no_linked_clinician":
        return (
            "This appointment isn’t linked to a clinician, so Nura can’t tell "
            f"when you last saw them. Showing the last {PRESET_DAYS[period.preset]} days."
        )
    if period.fallback_reason == "no_previous_visit":
        return (
            "Nura has no earlier appointment with this clinician, so it can’t "
            f"work out when you last met. Showing the last "
            f"{PRESET_DAYS[period.preset]} days."
        )
    return None


def describe_since_last_visit(period: ReportPeriod) -> str | None:
    """ "Since your appointment on 1 September 2026", when that is the period."""
    if period.previous_visit_date is None:
        return None
    return f"Since your appointment on {format_day(period.previous_visit_date)}"
