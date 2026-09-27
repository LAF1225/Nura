"""Medication scheduling, doses, supply and adherence (PRD 5).

A package rather than a module because this is four distinct jobs that happen
to share a subject, and one file holding all of them would be the longest in
the codebase by some way:

    schedules   what a schedule may be, and what changing one does to the future
    doses       recurrence, the grace period, and the three actions
    supply      how many are left, and when to mention a refill
    adherence   one number, with its denominator written down
    summary     the slice of all that which Today shows

Import the submodules rather than names from here -- ``from
app.services.medications import doses as dose_service`` -- so a call site says
which of the four it is reaching for.
"""

from app.services.medications import adherence, doses, schedules, summary, supply

__all__ = ["adherence", "doses", "schedules", "summary", "supply"]
