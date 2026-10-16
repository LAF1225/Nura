"""A dose that is due, on a screen other people can see.

PRD 11, sections 21, 22, 51, 56, 85, 86, 102 and 125.

**The privacy level is applied here, not later.** Section 22 exists because a
robot sits on a shelf in a room that other people walk through, and a tablet
name is sometimes the most private thing in somebody's day. The three levels
produce three different payloads, and the redaction happens while the payload
is built -- so the row stored in ``device_presentations`` is already the
redacted one, and the app's own history endpoint cannot accidentally show more
than the robot was sent.

**Privacy mode wins over the preference.** Section 33 asks the robot to
suppress sensitive previews in Privacy Mode. A person who chose "full details"
and then put Nura in Privacy Mode gets the private card, because the mode is a
thing they are doing now and the preference is a thing they set once.

**The card is additive and the phone is primary.** Sections 51 and 102. Nothing
here touches the dose. A dose that is reminded on the robot is reminded on the
phone too, by PRD 5, and a robot that is offline, unbuilt or has no screen
changes neither.

**Stale reminders cannot survive.** Section 56: ``is_due`` is recomputed from
PRD 5's own ``window`` on every reconciliation, so a dose that has been taken,
skipped or snoozed past its moment loses its card rather than being shown
"take this now" an hour late. The dedupe key carries the snooze count, so a
snoozed dose gets a new card at its new time instead of folding into the one
that was already withdrawn.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Device, DevicePresentation, MedicationDose
from app.services.medications import doses as dose_service
from app.services.robot import capabilities as capability_service
from app.services.robot import layouts, modes, preferences, queue, wording

logger = logging.getLogger(__name__)

SOURCE = "medication"
PRESENTATION_TYPE = "medication_reminder"

#: Section 21's future actions. Offered only when the device reports input
#: hardware; section 86 turns the card into "Use the Nura app to respond."
#: otherwise, which is what every deployment gets today.
ACTIONS = ("taken", "snooze", "skip")

#: PRD 5's own notion of "now-ish". A dose reads as ``due`` from half an hour
#: before its time until two hours after, and those are PRD 5's numbers rather
#: than a second set invented here.
DUE_WINDOWS = ("due",)


def privacy_level_for(
    resolved: preferences.EffectivePreferences, mode: modes.RobotMode
) -> str:
    """Which level applies right now (sections 22 and 33).

    Privacy Mode overrides the stored preference, **downwards only**: a person
    who chose "full details" and then put Nura in Privacy Mode gets the private
    card, because the mode is something they are doing now and the preference
    is something they set once. There is no direction in which this function
    can reveal more than the preference asked for.

    One function, used by the builder *and* by the reconciler's staleness
    check, so "which level is in force" has one answer.
    """
    if mode.mode == "privacy":
        return "private"
    return resolved.medication_privacy_level


def source_id(dose: MedicationDose, privacy_level: str) -> str:
    """The dose, which attempt at it this is, and at what level (section 57).

    Three parts, and each is a genuinely different occasion.

    The snooze count, because a snoozed dose is a second occasion: the first
    card was withdrawn when the person pressed Snooze, and the new one is due
    at a new time.

    The privacy level, because a card already on the screen must change when
    the level does. Without it the rebuild folds into the existing row and
    somebody who has just switched to a private preview -- or turned Privacy
    Mode on -- keeps looking at the name of their tablet. That is the wrong
    direction for sections 22 and 33 to fail in, and the manual walk-through
    is what found it.
    """
    return f"{dose.id}:{dose.snooze_count}:{privacy_level}"


def is_due(dose: MedicationDose, now: datetime) -> bool:
    """Whether this dose should be on the robot's screen right now."""
    return dose_service.window(dose, now) in DUE_WINDOWS


def build(
    dose: MedicationDose,
    *,
    privacy_level: str,
    zone: str,
    has_input: bool,
    speak: bool,
    chime: bool,
) -> queue.PresentationRequest:
    """One reminder, at one privacy level (sections 21 and 22).

    ``full`` shows the name, the dose and the time; ``name_only`` drops the
    dose, because the amount is often the part that says what the condition is;
    ``private`` says that something is due and nothing else, which is section
    22's own example.
    """
    when = wording.dose_window_line(due_at=dose_service.due_at(dose), zone=zone)
    title = wording.PRESENTATION_TITLES[PRESENTATION_TYPE]

    if privacy_level == "private":
        primary = "Reminder due"
        secondary = None
    elif privacy_level == "name_only":
        primary = dose.medication.name
        secondary = when
    else:
        amount = _amount(dose)
        primary = dose.medication.name
        secondary = f"{amount} · {when}" if amount else when

    payload = {
        "title": title,
        "primary": primary,
        "secondary": secondary,
        "prompt": "Taken?" if has_input else None,
        "actions": list(ACTIONS) if has_input else [],
        "respond_in_app": not has_input,
        # Section 67: whether this payload holds something worth keeping out of
        # a log. The private card does not.
        "sensitive": privacy_level != "private",
        "speak": speak,
        "chime": "reminder" if chime else None,
    }
    return queue.PresentationRequest(
        presentation_type=PRESENTATION_TYPE,
        layout="REMINDER",
        payload=layouts.build_payload("REMINDER", **payload),
        source=SOURCE,
        source_id=source_id(dose, privacy_level),
        meta={"privacy": privacy_level},
    )


def _amount(dose: MedicationDose) -> str | None:
    """ "500 mg", or nothing when the record does not say."""
    medication = dose.medication
    if medication.dose is None:
        return None
    if medication.dose_unit:
        return f"{medication.dose} {medication.dose_unit}"
    return medication.dose


def queue_for_dose(
    db: Session,
    device: Device,
    dose: MedicationDose,
    now: datetime,
    *,
    mode: modes.RobotMode | None = None,
) -> DevicePresentation | None:
    """Builds and queues a reminder for one dose, if it is still due."""
    if not is_due(dose, now):
        return None
    resolved_mode = mode or modes.resolve(db, device, now)
    _, resolved_preferences = preferences.resolved_for(db, device, now)
    states = capability_service.capability_map(db, device, now)

    privacy_level = privacy_level_for(resolved_preferences, resolved_mode)
    speak = (
        resolved_preferences.read_medications_aloud
        and capability_service.can_speak(states)
        and not modes.suppresses_audio(resolved_mode.mode)
        and privacy_level != "private"
    )
    request = build(
        dose,
        privacy_level=privacy_level,
        zone=_zone_for(dose),
        has_input=capability_service.has_input(states),
        speak=speak,
        chime=capability_service.can_play_chime(states),
    )
    return queue.queue(db, device, request, now, mode=resolved_mode)


def _zone_for(dose: MedicationDose) -> str:
    """The schedule's own zone, which is where its times were written."""
    if dose.schedule is not None and dose.schedule.timezone:
        return dose.schedule.timezone
    return "UTC"


def cancel_for_dose(
    db: Session,
    device: Device,
    dose: MedicationDose,
    now: datetime,
    *,
    reason: str = "source_resolved",
) -> int:
    """Withdraws every card for a dose, whatever level it was built at.

    Matched on the dose id alone rather than on a whole key: a dose has one
    card at a time, and which level that card happens to be at is not something
    the caller should have to know to withdraw it (sections 56, 125).
    """
    return queue.cancel_for_source(
        db,
        device.id,
        source=SOURCE,
        source_id_prefix=str(dose.id),
        reason=reason,
        now=now,
        presentation_type=PRESENTATION_TYPE,
    )
