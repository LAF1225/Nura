"""Medication schedules, doses, adherence and supply (PRD 5, sections 51, 52).

Every route is nested under the profile the records belong to and resolves it
through ``OwnedProfile``, so the authorization chain is the same one the
health record uses: *a schedule, a dose or a supply row is reachable only
through a profile the signed-in account owns*, and anything else is a 404
rather than a 403 (PRD 5, section 52).

Nothing here is authorized by object id alone. A dose is fetched by profile
*and* id together, a medication is resolved through the profile before a
schedule can point at it, and there is no route that takes an id and works out
who it belongs to afterwards.

The routes are written out per resource rather than generated. They are
repetitive, and that is the point: this is the surface that decides whether
somebody's medication reminders can be read or changed, and being able to read
each route in full is worth more here than brevity.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Now, OwnedProfile, http_error
from app.models import MedicationDose, MedicationSchedule, MedicationSupply, Profile
from app.schemas.medication import (
    AdherenceRead,
    DoseActionRead,
    DoseSkipAction,
    DoseSnoozeAction,
    DoseTakenAction,
    MedicationDoseRead,
    MedicationRefillCreate,
    MedicationScheduleCreate,
    MedicationSchedulePause,
    MedicationScheduleRead,
    MedicationScheduleUpdate,
    MedicationSupplyRead,
    MedicationSupplyUpdate,
    ScheduleTimeRead,
)
from app.services.errors import DomainError
from app.services.medications import adherence as adherence_service
from app.services.medications import doses as dose_service
from app.services.medications import schedules as schedule_service
from app.services.medications import supply as supply_service

router = APIRouter(prefix="/profiles/{profile_id}", tags=["medications"])

NO_CONTENT = status.HTTP_204_NO_CONTENT
CREATED = status.HTTP_201_CREATED

#: The window the history screen opens on (PRD 5, section 26).
DEFAULT_HISTORY_DAYS = 7


# --- shared plumbing --------------------------------------------------------


def _schedule_read(schedule: MedicationSchedule) -> MedicationScheduleRead:
    return MedicationScheduleRead(
        id=schedule.id,
        profile_id=schedule.profile_id,
        medication_id=schedule.medication_id,
        medication_name=schedule.medication.name,
        medication_dose=schedule.medication.dose,
        schedule_type=schedule.schedule_type,  # type: ignore[arg-type]
        timezone=schedule.timezone,
        start_date=schedule.start_date,
        end_date=schedule.end_date,
        is_active=schedule.is_active,
        paused_at=schedule.paused_at,
        times=[ScheduleTimeRead.model_validate(entry) for entry in schedule.times],
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
    )


def _dose_read(dose: MedicationDose, now: datetime) -> MedicationDoseRead:
    """A dose, with the three values that are derived rather than stored."""
    return MedicationDoseRead(
        id=dose.id,
        profile_id=dose.profile_id,
        medication_id=dose.medication_id,
        medication_name=dose.medication.name,
        medication_dose=dose.medication.dose,
        schedule_id=dose.schedule_id,
        scheduled_for=dose.scheduled_for,
        local_date=dose.local_date,
        status=dose.status,  # type: ignore[arg-type]
        window=dose_service.window(dose, now),  # type: ignore[arg-type]
        action_at=dose.action_at,
        source=dose.source,  # type: ignore[arg-type]
        skip_reason_code=dose.skip_reason_code,  # type: ignore[arg-type]
        skip_reason_text=dose.skip_reason_text,
        snoozed_until=dose.snoozed_until,
        snooze_count=dose.snooze_count,
        late=dose_service.was_late(dose),
        can_snooze=(
            dose.snooze_count < dose_service.MAX_SNOOZES
            and dose.status in ("scheduled", "snoozed", "missed")
        ),
    )


def _action_read(result: dose_service.DoseActionResult, now: datetime) -> DoseActionRead:
    return DoseActionRead(
        dose=_dose_read(result.dose, now),
        applied=result.applied,
        supply_remaining=result.supply_remaining,
        low_supply=result.low_supply,
    )


def _supply_read(supply: MedicationSupply, name: str) -> MedicationSupplyRead:
    return MedicationSupplyRead(
        profile_id=supply.profile_id,
        medication_id=supply.medication_id,
        medication_name=name,
        tracking_enabled=supply.tracking_enabled,
        remaining_doses=supply.remaining_doses,
        refill_threshold_doses=supply.refill_threshold_doses,
        last_refill_date=supply.last_refill_date,
        low=supply_service.is_low(supply),
    )


def _times(
    payload: MedicationScheduleCreate | MedicationScheduleUpdate,
) -> list[schedule_service.TimeInput]:
    entries = payload.times or []
    return [
        schedule_service.TimeInput(time_of_day=entry.time_of_day, weekday=entry.weekday)
        for entry in entries
    ]


def _fetch_schedule(
    db: DbSession, profile: Profile, schedule_id: uuid.UUID
) -> MedicationSchedule:
    try:
        return schedule_service.get_schedule(db, profile.id, schedule_id)
    except DomainError as error:
        raise http_error(error) from error


def _fetch_dose(db: DbSession, profile: Profile, dose_id: uuid.UUID) -> MedicationDose:
    try:
        return dose_service.get_dose(db, profile.id, dose_id)
    except DomainError as error:
        raise http_error(error) from error


# --- schedules --------------------------------------------------------------

schedules = APIRouter(prefix="/medication-schedules")

MedicationFilter = Annotated[
    uuid.UUID | None, Query(description="Only schedules for this medication.")
]
ActiveFilter = Annotated[
    bool | None, Query(description="True for schedules that are not paused.")
]


@schedules.get("", response_model=list[MedicationScheduleRead])
def list_schedules(
    profile: OwnedProfile,
    db: DbSession,
    medication_id: MedicationFilter = None,
    active: ActiveFilter = None,
) -> list[MedicationScheduleRead]:
    rows = schedule_service.list_schedules(
        db,
        profile.id,
        medication_id=medication_id,
        active_only=bool(active),
    )
    return [_schedule_read(schedule) for schedule in rows]


@schedules.post("", response_model=MedicationScheduleRead, status_code=CREATED)
def create_schedule(
    payload: MedicationScheduleCreate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> MedicationScheduleRead:
    """Attaches a schedule to an existing medication record (PRD 5, section 4).

    The medication is resolved through the profile first, so a schedule can
    never be attached to somebody else's medication by sending its id.
    """
    try:
        medication = schedule_service.get_medication(
            db, profile.id, payload.medication_id
        )
        schedule = schedule_service.create_schedule(
            db,
            profile.id,
            medication,
            schedule_type=payload.schedule_type,
            timezone=payload.timezone,
            start_date=payload.start_date,
            end_date=payload.end_date,
            times=_times(payload),
            now=now,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _schedule_read(schedule)


@schedules.get("/{schedule_id}", response_model=MedicationScheduleRead)
def read_schedule(
    schedule_id: uuid.UUID, profile: OwnedProfile, db: DbSession
) -> MedicationScheduleRead:
    return _schedule_read(_fetch_schedule(db, profile, schedule_id))


@schedules.patch("/{schedule_id}", response_model=MedicationScheduleRead)
def update_schedule(
    schedule_id: uuid.UUID,
    payload: MedicationScheduleUpdate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> MedicationScheduleRead:
    """Changes a schedule and rebuilds its *future* doses (PRD 5, section 36).

    Nothing already recorded is touched, including earlier today.
    """
    schedule = _fetch_schedule(db, profile, schedule_id)
    fields = payload.model_dump(exclude_unset=True)
    try:
        updated = schedule_service.update_schedule(
            db,
            schedule,
            now,
            schedule_type=payload.schedule_type,
            timezone=payload.timezone,
            start_date=payload.start_date,
            end_date=payload.end_date,
            end_date_set="end_date" in fields,
            times=None if payload.times is None else _times(payload),
        )
    except DomainError as error:
        raise http_error(error) from error
    return _schedule_read(updated)


@schedules.post("/{schedule_id}/pause", response_model=MedicationScheduleRead)
def pause_schedule(
    schedule_id: uuid.UUID,
    payload: MedicationSchedulePause,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> MedicationScheduleRead:
    """Stops or restarts reminders, keeping the schedule and its history."""
    schedule = _fetch_schedule(db, profile, schedule_id)
    updated = schedule_service.set_paused(db, schedule, paused=payload.paused, now=now)
    return _schedule_read(updated)


@schedules.delete("/{schedule_id}", status_code=NO_CONTENT)
def delete_schedule(
    schedule_id: uuid.UUID, profile: OwnedProfile, db: DbSession, now: Now
) -> None:
    """Removes a schedule. Doses it already produced keep their history."""
    schedule_service.delete_schedule(db, _fetch_schedule(db, profile, schedule_id), now)


# --- doses ------------------------------------------------------------------

doses = APIRouter(prefix="/medication-doses")

FromDate = Annotated[
    date | None, Query(description="First local day to include, YYYY-MM-DD.")
]
ToDate = Annotated[
    date | None, Query(description="Last local day to include, YYYY-MM-DD.")
]
LocalDate = Annotated[
    date | None, Query(description="The date on the client's own clock.")
]


@doses.get("", response_model=list[MedicationDoseRead])
def list_doses(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    from_date: FromDate = None,
    to_date: ToDate = None,
    medication_id: MedicationFilter = None,
) -> list[MedicationDoseRead]:
    """Dose history over a range of the user's own local days.

    Replenishes first, so a client that has not opened the app for a while
    sees missed doses recorded rather than a row of stale "scheduled" entries
    (PRD 5, sections 22 and 71).
    """
    end = to_date or now.date()
    start = from_date or end - timedelta(days=DEFAULT_HISTORY_DAYS - 1)
    if (end - start).days > dose_service.HISTORY_MAX_DAYS:
        start = end - timedelta(days=dose_service.HISTORY_MAX_DAYS)

    dose_service.replenish(db, profile.id, now)
    rows = dose_service.list_doses(
        db, profile.id, from_date=start, to_date=end, medication_id=medication_id
    )
    return [_dose_read(dose, now) for dose in rows]


@doses.get("/today", response_model=list[MedicationDoseRead])
def list_today_doses(
    profile: OwnedProfile, db: DbSession, now: Now, local_date: LocalDate = None
) -> list[MedicationDoseRead]:
    """One local day's doses, earliest first.

    The client sends the date on its own clock, exactly as the daily check-in
    does: the server's UTC date is only ever right by accident.
    """
    on_date = local_date or now.date()
    dose_service.replenish(db, profile.id, now)
    rows = dose_service.list_doses(db, profile.id, from_date=on_date, to_date=on_date)
    return [_dose_read(dose, now) for dose in rows]


@doses.post("/{dose_id}/taken", response_model=DoseActionRead)
def mark_taken(
    dose_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: DoseTakenAction | None = None,
) -> DoseActionRead:
    """Records a dose as taken.

    Idempotent: sending it twice leaves one taken dose and decrements supply
    once (PRD 5, section 48). Marking a dose taken long after it was due keeps
    the same row and records when it actually happened -- there is never a
    second, "late" dose (section 25).
    """
    body = payload or DoseTakenAction()
    dose = _fetch_dose(db, profile, dose_id)
    try:
        result = dose_service.record_taken(
            db, dose, now, source="app", action_at=body.action_at
        )
    except DomainError as error:
        raise http_error(error) from error
    return _action_read(result, now)


@doses.post("/{dose_id}/snooze", response_model=DoseActionRead)
def snooze_dose(
    dose_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: DoseSnoozeAction | None = None,
) -> DoseActionRead:
    """Puts a dose off, leaving it unrecorded (PRD 5, section 18)."""
    body = payload or DoseSnoozeAction()
    dose = _fetch_dose(db, profile, dose_id)
    try:
        result = dose_service.record_snoozed(
            db, dose, now, minutes=body.minutes, source="app"
        )
    except DomainError as error:
        raise http_error(error) from error
    return _action_read(result, now)


@doses.post("/{dose_id}/skip", response_model=DoseActionRead)
def skip_dose(
    dose_id: uuid.UUID,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    payload: DoseSkipAction | None = None,
) -> DoseActionRead:
    """Records that a dose was not taken, with an optional reason.

    The reason is stored as chosen and never interpreted. Nothing follows from
    it: no alert, no advice, no change in what Nura says (PRD 5, s19 and 57).
    """
    body = payload or DoseSkipAction()
    dose = _fetch_dose(db, profile, dose_id)
    try:
        result = dose_service.record_skipped(
            db,
            dose,
            now,
            source="app",
            reason_code=body.reason_code,
            reason_text=body.reason_text,
            action_at=body.action_at,
        )
    except DomainError as error:
        raise http_error(error) from error
    return _action_read(result, now)


# --- adherence --------------------------------------------------------------

adherence = APIRouter(prefix="/medication-adherence")

DaysQuery = Annotated[
    int, Query(ge=1, le=dose_service.HISTORY_MAX_DAYS, description="Days to count back.")
]


@adherence.get("", response_model=AdherenceRead)
def read_adherence(
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
    days: DaysQuery = DEFAULT_HISTORY_DAYS,
    medication_id: MedicationFilter = None,
    to_date: ToDate = None,
) -> AdherenceRead:
    """taken / (taken + skipped + missed) over a window (PRD 5, section 27).

    Replenishes first so the figure counts doses that have quietly become
    missed rather than ignoring them, which would flatter it.
    """
    dose_service.replenish(db, profile.id, now)
    end = to_date or now.date()
    result = adherence_service.calculate(
        db,
        profile.id,
        from_date=end - timedelta(days=days - 1),
        to_date=end,
        medication_id=medication_id,
    )
    return AdherenceRead(
        profile_id=profile.id,
        from_date=result.from_date,
        to_date=result.to_date,
        taken=result.taken,
        skipped=result.skipped,
        missed=result.missed,
        total=result.total,
        percent=result.percent,
    )


# --- supply -----------------------------------------------------------------

supply = APIRouter(prefix="/medication-supply")


@supply.get("", response_model=list[MedicationSupplyRead])
def list_supply(profile: OwnedProfile, db: DbSession) -> list[MedicationSupplyRead]:
    """Every medication this profile is tracking a supply for."""
    return [
        _supply_read(record, medication.name)
        for record, medication in supply_service.list_supply(db, profile.id)
    ]


@supply.patch("/{medication_id}", response_model=MedicationSupplyRead)
def update_supply(
    medication_id: uuid.UUID,
    payload: MedicationSupplyUpdate,
    profile: OwnedProfile,
    db: DbSession,
) -> MedicationSupplyRead:
    """Turns tracking on, or corrects the numbers by hand (PRD 5, s32 and 33).

    Creates the record on first use, so the app does not need a separate
    "enable tracking" call before it can save a count.
    """
    try:
        medication = schedule_service.get_medication(db, profile.id, medication_id)
    except DomainError as error:
        raise http_error(error) from error

    fields = payload.model_dump(exclude_unset=True)
    record = supply_service.upsert_supply(
        db,
        profile.id,
        medication.id,
        tracking_enabled=payload.tracking_enabled,
        remaining_doses=payload.remaining_doses,
        remaining_set="remaining_doses" in fields,
        refill_threshold_doses=payload.refill_threshold_doses,
        threshold_set="refill_threshold_doses" in fields,
    )
    return _supply_read(record, medication.name)


@supply.post("/{medication_id}/refill", response_model=MedicationSupplyRead)
def record_refill(
    medication_id: uuid.UUID,
    payload: MedicationRefillCreate,
    profile: OwnedProfile,
    db: DbSession,
    now: Now,
) -> MedicationSupplyRead:
    """Records a new supply: the count the user now has (PRD 5, section 35)."""
    try:
        medication = schedule_service.get_medication(db, profile.id, medication_id)
    except DomainError as error:
        raise http_error(error) from error

    record = supply_service.refill(
        db,
        profile.id,
        medication.id,
        remaining_doses=payload.remaining_doses,
        on_date=payload.refilled_on or now.date(),
    )
    return _supply_read(record, medication.name)


router.include_router(schedules)
router.include_router(doses)
router.include_router(adherence)
router.include_router(supply)
