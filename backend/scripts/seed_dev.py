"""Development fixtures for the Today screen (PRD 3, sections 25 and 53).

The robot does not exist yet, so the only honest way to see the connected
states is to write the rows a robot would have written. That is all this does:
it creates a device row and sets ``last_seen_at``, which is the *same* input
the real heartbeat endpoint produces and the only thing that decides whether
Nura is reported online.

Nothing here is reachable from the app. There is no "pretend the robot is
online" button, and the script refuses to run unless ``APP_ENV`` is
``development`` (PRD 3, section 25).

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.seed_dev --list
    python -m scripts.seed_dev --account latest --device online
    python -m scripts.seed_dev --account latest --device online --keep-online 300
    python -m scripts.seed_dev --account latest --device offline --minutes-ago 42
    python -m scripts.seed_dev --account latest --device never-seen
    python -m scripts.seed_dev --account latest --device none
    python -m scripts.seed_dev --account you@example.com --checkin okay
    python -m scripts.seed_dev --account latest --checkin none
    python -m scripts.seed_dev --account latest --health partial
    python -m scripts.seed_dev --account latest --health complete
    python -m scripts.seed_dev --account latest --health empty
    python -m scripts.seed_dev --account latest --medications demo
    python -m scripts.seed_dev --account latest --medications demo --timezone UTC
    python -m scripts.seed_dev --account latest --medications empty
    python -m scripts.seed_dev --account latest --symptoms demo
    python -m scripts.seed_dev --account latest --symptoms empty
    python -m scripts.seed_dev --account latest --appointments demo
    python -m scripts.seed_dev --account latest --safety monitoring
    python -m scripts.seed_dev --account latest --safety possible-fall
    python -m scripts.seed_dev --account latest --safety no-response
    python -m scripts.seed_dev --account latest --safety sos
    python -m scripts.seed_dev --account latest --safety history
    python -m scripts.seed_dev --account latest --safety empty
    python -m scripts.seed_dev --account latest --daily-life demo
    python -m scripts.seed_dev --account latest --daily-life busy
    python -m scripts.seed_dev --account latest --daily-life empty
    python -m scripts.seed_dev --account latest --robot online
    python -m scripts.seed_dev --account latest --robot unverified
    python -m scripts.seed_dev --account latest --robot headless
    python -m scripts.seed_dev --account latest --robot offline
    python -m scripts.seed_dev --account latest --robot speaker
    python -m scripts.seed_dev --account latest --robot empty
    python -m scripts.seed_dev --account latest --device-token

``--account`` takes an email, a phone number, an auth provider subject, or
``latest`` for the most recently created account -- which during development is
almost always the one signed in on the phone.
"""

import argparse
import base64
import secrets
import sys
import time as clock_module
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import (
    AccountProfileRole,
    Alarm,
    Allergy,
    Appointment,
    AssistantMemory,
    CaregiverAuditEvent,
    CaregiverRelationship,
    CaregiverSuggestion,
    Clinician,
    Conversation,
    DailyCheckIn,
    Device,
    DeviceCapability,
    DevicePresentation,
    DevicePresentationPreferences,
    EmergencyContact,
    FamilyThread,
    GeneralReminder,
    GeneralReminderOccurrence,
    HealthRecord,
    MedicalCondition,
    MedicalNote,
    Medication,
    MedicationDose,
    MedicationSchedule,
    Procedure,
    Profile,
    Routine,
    RoutineRun,
    RoutineStep,
    RoutineStepCompletion,
    SafetyAlert,
    SafetyAuditEvent,
    SafetyEscalationAttempt,
    SafetyEvent,
    SafetyMonitoringSession,
    SymptomEntry,
    SymptomEpisode,
    SymptomPhoto,
    Task,
    User,
    UserSettings,
)
from app.services import checkins as checkin_service
from app.services import health as health_service
from app.services import profiles as profile_service
from app.services.appointments import appointments as appointment_service
from app.services.appointments import periods as period_service
from app.services.appointments import preparation as preparation_service
from app.services.appointments import questions as question_service
from app.services.appointments import reports as report_service
from app.services.appointments import snapshot as snapshot_service
from app.services.appointments import summary as appointment_summary
from app.services.appointments.pdf import get_pdf_service
from app.services.assistant import conversations as conversation_service
from app.services.assistant import memory as memory_service
from app.services.assistant import preferences as preference_service
from app.services.caregivers import contacts as contact_service
from app.services.caregivers import invitations as invitation_service
from app.services.caregivers import messaging as message_service
from app.services.caregivers import permissions as permission_service
from app.services.caregivers import relationships as relationship_service
from app.services.caregivers import suggestions as suggestion_service
from app.services.devices import ONLINE_THRESHOLD, generate_token, hash_secret
from app.services.medications import doses as dose_service
from app.services.medications import schedules as schedule_service
from app.services.medications import supply as supply_service
from app.services.productivity import alarms as alarm_service
from app.services.productivity import capabilities as daily_life_capabilities
from app.services.productivity import reminders as general_reminder_service
from app.services.productivity import routines as routine_service
from app.services.productivity import summary as daily_life_summary
from app.services.productivity import tasks as task_service
from app.services.productivity import wording as productivity_wording
from app.services.robot import capabilities as robot_capabilities
from app.services.robot import presenter as robot_presenter
from app.services.robot import simulator as robot_simulator
from app.services.robot import wording as robot_wording
from app.services.safety import capabilities as safety_capabilities
from app.services.safety import checks as safety_checks
from app.services.safety import escalation as safety_escalation
from app.services.safety import events as safety_events
from app.services.safety import monitoring as safety_monitoring
from app.services.safety import wording as safety_wording
from app.services.storage import get_object_store
from app.services.symptoms import episodes as episode_service
from app.services.symptoms import photos as photo_service
from app.services.symptoms import summary as symptom_summary

#: Deliberately not a real MAC address. A physical XIAO reports its factory
#: MAC, so a seeded row can never collide with a board you later build.
SEEDED_HARDWARE_ID = "NURA-DEADBEEF0001"

#: The second person ``--caregivers multi`` creates, so one caregiver account
#: can be seen supporting two profiles (PRD 9, section 56).
SECOND_PROFILE_NAME = "Yusuf"

#: How often ``--keep-online`` refreshes the heartbeat. Comfortably inside the
#: 90-second window the backend uses to call a robot online.
KEEP_ALIVE_INTERVAL_SECONDS = 30


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def open_session() -> Session:
    settings = get_settings()
    if not settings.is_development:
        fail(
            "this script only runs with APP_ENV=development. It writes rows a "
            "real robot would write, which has no business happening in production."
        )
    engine = create_engine(settings.database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def find_account(db: Session, reference: str) -> User:
    if reference == "latest":
        user = db.execute(
            select(User).order_by(User.created_at.desc()).limit(1)
        ).scalar_one_or_none()
        if user is None:
            fail("no accounts yet -- sign in on the phone first, then re-run this.")
        assert user is not None
        return user

    user = db.execute(
        select(User).where(
            (User.email == reference)
            | (User.phone == reference)
            | (User.auth_provider_id == reference)
        )
    ).scalar_one_or_none()
    if user is None:
        fail(f"no account matches {reference!r}. Try --list.")
    assert user is not None
    return user


def describe(db: Session, user: User) -> str:
    profile = profile_service.primary_profile(user)
    name = profile.preferred_name if profile else "no profile yet"
    devices = ", ".join(
        f"{device.display_name} ({_presence(device)})" for device in user.devices
    )
    return (
        f"{user.email or user.phone or user.auth_provider_id}  "
        f"[{name}]  onboarding={user.onboarding_status}  "
        f"devices={devices or 'none'}"
    )


def _presence(device: Device) -> str:
    if device.last_seen_at is None:
        return "never seen"
    age = datetime.now(UTC) - device.last_seen_at
    if age <= ONLINE_THRESHOLD:
        return "online"
    minutes = int(age.total_seconds() // 60)
    if minutes < 60:
        return f"offline, last seen {minutes}m ago"
    hours = minutes // 60
    return f"offline, last seen {hours}h ago" if hours < 48 else "offline, days ago"


def seeded_device(db: Session, user: User) -> Device | None:
    for device in user.devices:
        if device.hardware_id == SEEDED_HARDWARE_ID:
            return device
    return None


def set_device(db: Session, user: User, state: str, minutes_ago: int) -> None:
    existing = seeded_device(db, user)

    if state == "none":
        if existing is None:
            print("no seeded device to remove.")
            return
        db.delete(existing)
        db.commit()
        print("removed the seeded device. Today should show 'not connected yet'.")
        return

    last_seen: datetime | None
    if state == "online":
        last_seen = datetime.now(UTC)
    elif state == "offline":
        last_seen = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    else:  # never-seen
        last_seen = None

    device = existing
    if device is None:
        device = Device(
            hardware_id=SEEDED_HARDWARE_ID,
            display_name="Nura",
            claimed_by_account_id=user.id,
            owner_profile_id=profile_service.primary_profile_id(user),
            provisioning_status="claimed",
            # Random, and never shared with anything: no robot can authenticate
            # as this row, which is the point. It is a row, not a device.
            bootstrap_secret_hash=hash_secret(secrets.token_hex(32)),
            device_token_hash=hash_secret(secrets.token_hex(32)),
            firmware_version="0.0.0-seed",
            claimed_at=datetime.now(UTC),
        )
        db.add(device)

    device.last_seen_at = last_seen
    db.commit()
    print(f"seeded device is now: {state}.")


def keep_online(db: Session, user: User, seconds: int) -> None:
    """Refreshes the heartbeat for a while, so the app stays on 'Online'.

    A single ``--device online`` goes stale after 90 seconds, exactly as a real
    robot would if it were unplugged. This holds it up long enough to walk
    through the screen.
    """
    device = seeded_device(db, user)
    if device is None:
        fail("seed a device first: --device online")
    assert device is not None

    deadline = clock_module.monotonic() + seconds
    print(f"holding {device.display_name} online for {seconds}s. Ctrl-C to stop.")
    try:
        while clock_module.monotonic() < deadline:
            device.last_seen_at = datetime.now(UTC)
            db.commit()
            clock_module.sleep(
                min(
                    KEEP_ALIVE_INTERVAL_SECONDS,
                    max(1, int(deadline - clock_module.monotonic())),
                )
            )
    except KeyboardInterrupt:
        print("\nstopped.")
    print("done -- the device will go offline within 90 seconds.")


def set_checkin(db: Session, user: User, level: str, note: str | None) -> None:
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to check in.")
    assert profile is not None

    today = date.today()
    existing = checkin_service.get_checkin(db, profile.id, today)

    if level == "none":
        if existing is None:
            print("no check-in today already.")
            return
        db.delete(existing)
        db.commit()
        print("cleared today's check-in.")
        return

    if existing is None:
        db.add(
            DailyCheckIn(
                profile_id=profile.id,
                checkin_date=today,
                wellbeing_level=level,
                note=note,
            )
        )
    else:
        existing.wellbeing_level = level
        existing.note = note
    db.commit()
    print(f"today's check-in for {profile.preferred_name} is now: {level}.")


#: Made-up records for a development account. Ordinary, unremarkable entries
#: on purpose: fixture data that looks alarming has a way of ending up in a
#: screenshot (PRD 4, section 53).
#: Model -> the rows to create for it.
HealthFixture = dict[type[HealthRecord], list[dict[str, Any]]]

PARTIAL_HEALTH: HealthFixture = {
    MedicalCondition: [
        {"name": "Asthma", "status": "active", "diagnosed_year": 2015},
        {"name": "Ankle sprain", "status": "resolved", "diagnosed_year": 2021},
    ],
    Medication: [
        {
            "name": "Salbutamol",
            "dose": "100",
            "dose_unit": "mcg",
            "form": "inhaler",
            "frequency_text": "two puffs when needed",
            "is_active": True,
        },
    ],
    Clinician: [{"name": "Dr Okafor", "specialty": "General practice"}],
}

COMPLETE_HEALTH: HealthFixture = {
    **PARTIAL_HEALTH,
    Medication: [
        *PARTIAL_HEALTH[Medication],
        {
            "name": "Amoxicillin",
            "dose": "500",
            "dose_unit": "mg",
            "form": "capsule",
            "frequency_text": "three times a day",
            "is_active": False,
        },
    ],
    Allergy: [
        {
            "allergen": "Penicillin",
            "allergy_type": "medication",
            "reaction": "Rash",
            "severity": "moderate",
        }
    ],
    Procedure: [{"name": "Appendectomy", "performed_year": 2009}],
    MedicalNote: [
        {
            "title": "Mobility",
            "body": "Uses a walking stick outdoors.",
            "category": "accessibility",
        }
    ],
}


def _clear_health(db: Session, profile: Profile) -> None:
    for model in health_service.SECTION_MODELS.values():
        for record in health_service.list_records(db, model, profile.id):
            db.delete(record)
    profile.blood_type = None
    profile.health_profile_status = "not_started"
    profile.health_profile_step = None
    db.commit()


def set_health(db: Session, user: User, preset: str) -> None:
    """Replaces the health profile with one of the three development shapes."""
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to be about.")
    assert profile is not None

    _clear_health(db, profile)

    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s health profile.")
        return

    records = PARTIAL_HEALTH if preset == "partial" else COMPLETE_HEALTH
    for model, entries in records.items():
        for fields in entries:
            db.add(model(profile_id=profile.id, **fields))

    profile.health_profile_status = "in_progress" if preset == "partial" else "complete"
    profile.health_profile_step = "allergies" if preset == "partial" else None
    if preset == "complete":
        profile.blood_type = "O+"
    db.commit()

    summary = health_service.build_summary(db, profile)
    print(
        f"{profile.preferred_name}'s health profile is now {preset}: "
        f"{summary.percent}% complete."
    )


# --- medications (PRD 5, section 77) ----------------------------------------

#: Everyday medications with unremarkable names, for the same reason the
#: health fixtures are dull: development data has a way of ending up in a
#: screenshot (PRD 4, section 53).
#:
#: Between them these four cover every state PRD 5 section 77 asks for --
#: a medication with no schedule, a paused schedule, an inactive medication,
#: a low supply, and doses that are due now, overdue, taken, skipped and
#: missed.
DEMO_MEDICATIONS: list[dict[str, Any]] = [
    {"name": "Metformin", "dose": "500", "dose_unit": "mg", "form": "tablet"},
    {"name": "Ramipril", "dose": "5", "dose_unit": "mg", "form": "tablet"},
    {"name": "Amoxicillin", "dose": "500", "dose_unit": "mg", "form": "capsule"},
    {"name": "Vitamin D", "dose": "1000", "dose_unit": "IU", "form": "tablet"},
]


def _find_or_create_medication(
    db: Session, profile: Profile, fields: dict[str, Any]
) -> Medication:
    existing = db.execute(
        select(Medication).where(
            Medication.profile_id == profile.id, Medication.name == fields["name"]
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    medication = Medication(profile_id=profile.id, **fields)
    db.add(medication)
    db.flush()
    return medication


def _clear_medications(db: Session, profile: Profile) -> None:
    """Removes schedules, doses and supply -- but not the PRD 4 records.

    The medication *records* are health data the user entered and are cleared
    by ``--health empty``. This flag only ever touches what PRD 5 added.
    """
    for dose in (
        db.execute(select(MedicationDose).where(MedicationDose.profile_id == profile.id))
        .scalars()
        .all()
    ):
        db.delete(dose)
    for schedule in (
        db.execute(
            select(MedicationSchedule).where(MedicationSchedule.profile_id == profile.id)
        )
        .scalars()
        .all()
    ):
        db.delete(schedule)
    for supply, _ in supply_service.list_supply(db, profile.id):
        db.delete(supply)
    db.commit()


def _past_dose(
    profile: Profile,
    medication: Medication,
    schedule: MedicationSchedule,
    *,
    when: datetime,
    zone: Any,
    status: str,
    **extra: Any,
) -> MedicationDose:
    """A dose that has already happened, written the way the app would have.

    Deliberately not generated: the generator only ever looks forward, which
    is correct, so history for a brand-new development account has to be
    written directly. Every field is one the API would have set.
    """
    return MedicationDose(
        profile_id=profile.id,
        medication_id=medication.id,
        schedule_id=schedule.id,
        scheduled_for=when,
        local_date=when.astimezone(zone).date(),
        status=status,
        **extra,
    )


def set_medications(db: Session, user: User, preset: str, timezone: str) -> None:
    """Builds the medication states PRD 5 section 77 asks a developer for."""
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to remind.")
    assert profile is not None

    _clear_medications(db, profile)
    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s schedules, doses and supply.")
        return

    zone = dose_service.zone_for(timezone)
    now = datetime.now(UTC)
    today = now.astimezone(zone).date()

    metformin, ramipril, amoxicillin, vitamin_d = (
        _find_or_create_medication(db, profile, fields) for fields in DEMO_MEDICATIONS
    )

    # Vitamin D is left exactly as it is: a medication record with no schedule.
    _ = vitamin_d
    # Amoxicillin is a course that has finished. An inactive medication never
    # generates, whatever schedules it may still carry (PRD 5, section 38).
    amoxicillin.is_active = False

    # Metformin: the one with a real routine and a history behind it.
    metformin_schedule = schedule_service.create_schedule(
        db,
        profile.id,
        metformin,
        schedule_type="daily",
        timezone=timezone,
        start_date=today - timedelta(days=7),
        end_date=None,
        times=[
            schedule_service.TimeInput(time_of_day=time(8, 0)),
            schedule_service.TimeInput(time_of_day=time(20, 0)),
        ],
        now=now,
    )

    db.add_all(
        [
            # Due right now, so the Today card has something to act on.
            _past_dose(
                profile,
                metformin,
                metformin_schedule,
                when=now,
                zone=zone,
                status="scheduled",
            ),
            # Past its grace period and unrecorded.
            _past_dose(
                profile,
                metformin,
                metformin_schedule,
                when=now - dose_service.GRACE_PERIOD - timedelta(hours=1),
                zone=zone,
                status="missed",
            ),
            _past_dose(
                profile,
                metformin,
                metformin_schedule,
                when=now - timedelta(days=1, hours=4),
                zone=zone,
                status="taken",
                action_at=now - timedelta(days=1, hours=3, minutes=50),
                source="app",
            ),
            _past_dose(
                profile,
                metformin,
                metformin_schedule,
                when=now - timedelta(days=2, hours=4),
                zone=zone,
                status="skipped",
                action_at=now - timedelta(days=2, hours=3),
                source="app",
                skip_reason_code="ran_out",
            ),
            _past_dose(
                profile,
                metformin,
                metformin_schedule,
                when=now - timedelta(days=3, hours=4),
                zone=zone,
                status="missed",
            ),
        ]
    )

    # Ramipril: a schedule the user has paused.
    ramipril_schedule = schedule_service.create_schedule(
        db,
        profile.id,
        ramipril,
        schedule_type="daily",
        timezone=timezone,
        start_date=today,
        end_date=None,
        times=[schedule_service.TimeInput(time_of_day=time(9, 0))],
        now=now,
    )
    schedule_service.set_paused(db, ramipril_schedule, paused=True, now=now)

    # Metformin is running low, against a threshold the "user" chose.
    supply_service.upsert_supply(
        db,
        profile.id,
        metformin.id,
        tracking_enabled=True,
        remaining_doses=4,
        remaining_set=True,
        refill_threshold_doses=5,
        threshold_set=True,
        last_refill_date=today - timedelta(days=20),
        last_refill_set=True,
    )

    db.commit()

    upcoming = len(
        dose_service.list_doses(
            db,
            profile.id,
            from_date=today,
            to_date=today + timedelta(days=dose_service.GENERATION_HORIZON_DAYS),
        )
    )
    print(
        f"{profile.preferred_name} now has: Metformin twice daily ({timezone}) with "
        f"{upcoming} doses in the window, one due now and one overdue; "
        "Ramipril paused; Amoxicillin inactive; Vitamin D with no schedule; "
        "and Metformin supply low (4 left, warn at 5)."
    )


# --- symptoms (PRD 6, section 85) -------------------------------------------

#: A 1x1 PNG, used as the attachment on the fixture with a photo. Deliberately
#: a blank pixel rather than a picture of anything: development data has a way
#: of ending up in a screenshot, and a photo fixture that looked like a real
#: symptom would be the worst possible version of that (PRD 4, section 53).
BLANK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)


def _clear_symptoms(db: Session, profile: Profile) -> None:
    """Removes episodes, entries and photos -- including stored objects.

    The database cascade takes entries and photo rows with an episode; the bytes
    are not in the database, so they have to go explicitly (PRD 6, section 35).
    """
    store = get_object_store()
    episodes = (
        db.execute(select(SymptomEpisode).where(SymptomEpisode.profile_id == profile.id))
        .scalars()
        .all()
    )
    for episode in episodes:
        photo_service.purge_objects(
            store, photo_service.photos_for_episode(db, episode.id)
        )
        db.delete(episode)
    db.commit()


def _symptom_entry(
    profile: Profile,
    episode: SymptomEpisode,
    *,
    when: datetime,
    severity: int | None = None,
    change_state: str | None = None,
    **extra: Any,
) -> SymptomEntry:
    """One observation, written the way the app would have written it."""
    return SymptomEntry(
        profile_id=profile.id,
        symptom_episode_id=episode.id,
        recorded_at=when,
        severity=severity,
        change_state=change_state,
        source="manual_app",
        **extra,
    )


def set_symptoms(db: Session, user: User, preset: str) -> None:
    """Builds the symptom states PRD 6 section 85 asks a developer for.

    One state on that list cannot be seeded from here: an *offline pending*
    symptom lives only on the phone, in the app's own queue, and the server has
    by definition never heard of it. The app's tests cover it, and a developer
    reaches it by turning off Wi-Fi and saving a symptom.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to log a symptom for.")
    assert profile is not None

    _clear_symptoms(db, profile)
    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s symptoms.")
        return

    now = datetime.now(UTC)

    # 1. A headache the user has recorded as getting worse. This is the one
    #    that reaches Important Today and shows the worsening notice.
    headache = episode_service.create_episode(
        db,
        profile,
        name="Headache",
        body_site="behind both eyes",
        first_noticed_date=(now - timedelta(days=3)).date(),
        first_noticed_text="Wednesday morning",
        commit=False,
    )
    db.add_all(
        [
            _symptom_entry(
                profile,
                headache,
                when=now - timedelta(days=3),
                severity=3,
                main_symptom="headache",
                site="behind both eyes",
                character="throbbing",
                onset_text="gradually",
            ),
            _symptom_entry(
                profile,
                headache,
                when=now - timedelta(days=1),
                severity=4,
                change_state="same",
            ),
            _symptom_entry(
                profile,
                headache,
                when=now - timedelta(hours=2),
                severity=6,
                change_state="worsening",
                associated_symptoms=["nausea", "light sensitivity"],
                exacerbating_factors=["bright light"],
                negated_items=["vomiting"],
                free_text_note="Worse than yesterday.",
            ),
        ]
    )

    # 2. A knee that is improving, with a photo attached -- the fixture for
    #    the private-photo path.
    knee = episode_service.create_episode(
        db,
        profile,
        name="Knee pain",
        body_site="left knee",
        first_noticed_date=(now - timedelta(days=10)).date(),
        commit=False,
    )
    knee_entry = _symptom_entry(
        profile,
        knee,
        when=now - timedelta(days=1),
        severity=3,
        change_state="improving",
        main_symptom="knee pain",
        site="left knee",
        character="aching",
        relieving_factors=["rest"],
    )
    db.add(knee_entry)
    db.flush()

    photo_id = uuid.uuid4()
    key = photo_service.storage_key_for(profile.id, photo_id, "image/png")
    get_object_store().put(key, BLANK_PNG)
    db.add(
        SymptomPhoto(
            id=photo_id,
            profile_id=profile.id,
            symptom_entry_id=knee_entry.id,
            storage_key=key,
            content_type="image/png",
            byte_size=len(BLANK_PNG),
        )
    )

    # 3. Something that is over. Resolved, still in the history, out of the
    #    active list (PRD 6, section 37).
    #
    #    Created active and then resolved, which is the order a user does it in
    #    -- and the only order the database allows, since a resolved episode has
    #    to carry a timestamp.
    sore_throat = episode_service.create_episode(
        db,
        profile,
        name="Sore throat",
        first_noticed_date=(now - timedelta(days=30)).date(),
        commit=False,
    )
    db.add(
        _symptom_entry(profile, sore_throat, when=now - timedelta(days=28), severity=4)
    )
    episode_service.resolve_episode(db, sore_throat, now - timedelta(days=24))

    # 4. Something that came back: a resolved bout, and a new episode linked to
    #    it carrying the status `recurring` (PRD 6, section 38).
    old_back = episode_service.create_episode(
        db,
        profile,
        name="Lower back pain",
        body_site="lower back",
        first_noticed_year=now.year - 1,
        commit=False,
    )
    db.add(_symptom_entry(profile, old_back, when=now - timedelta(days=150), severity=5))
    episode_service.resolve_episode(db, old_back, now - timedelta(days=120))

    new_back = episode_service.create_episode(
        db,
        profile,
        name="Lower back pain",
        body_site="lower back",
        status="recurring",
        first_noticed_date=(now - timedelta(days=2)).date(),
        first_noticed_text="after lifting a box",
        previous_episode_id=old_back.id,
        commit=False,
    )
    db.add(
        _symptom_entry(
            profile,
            new_back,
            when=now - timedelta(days=2),
            severity=4,
            main_symptom="lower back pain",
            onset_text="after lifting a box",
            exacerbating_factors=["bending"],
        )
    )

    db.commit()

    summary = symptom_summary.build_summary(db, profile.id, now)
    print(
        f"{profile.preferred_name} now has {summary.active_count} active symptoms "
        f"({summary.worsening_count} recorded as worsening): a worsening headache "
        "with three entries, an improving knee with one photo, a resolved sore "
        "throat, and lower back pain that has recurred. "
        "An offline pending symptom cannot be seeded -- it only exists on a phone."
    )


def _clear_appointments(db: Session, profile: Profile) -> None:
    """Removes appointments, their questions and their reports -- files included.

    The database cascade takes the question and report rows with an appointment;
    the PDFs are not in the database, so they have to go explicitly
    (PRD 7, section 35).
    """
    store = get_object_store()
    appointments = (
        db.execute(select(Appointment).where(Appointment.profile_id == profile.id))
        .scalars()
        .all()
    )
    for appointment in appointments:
        report_service.purge_objects(
            store, report_service.list_reports(db, appointment.id)
        )
        db.delete(appointment)
    db.commit()


def _seed_clinician(db: Session, profile: Profile) -> Clinician:
    """The clinician the fixtures link to, reused if one is already there."""
    existing = (
        db.execute(
            select(Clinician).where(
                Clinician.profile_id == profile.id, Clinician.name == "Dr Ahmed Khan"
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        return existing
    clinician = Clinician(
        profile_id=profile.id,
        name="Dr Ahmed Khan",
        specialty="Cardiology",
        clinic_name="City Hospital",
    )
    db.add(clinician)
    db.commit()
    db.refresh(clinician)
    return clinician


def _seed_appointment(
    db: Session,
    profile: Profile,
    *,
    title: str,
    when: datetime,
    timezone: str,
    clinician: Clinician | None = None,
    appointment_type: str = "specialist",
    location_name: str | None = None,
    notes: str | None = None,
) -> Appointment:
    return appointment_service.create_appointment(
        db,
        profile.id,
        appointment_service.AppointmentInput(
            title=title,
            scheduled_at=when,
            timezone=timezone,
            appointment_type=appointment_type,
            clinician_id=None if clinician is None else clinician.id,
            location_name=location_name,
            notes=notes,
        ),
    )


def _seed_report(
    db: Session,
    profile: Profile,
    appointment: Appointment,
    *,
    with_appendix: bool,
    now: datetime,
) -> None:
    """Generates a real report version through the real pipeline.

    Not a hand-written row: the snapshot, the PDF and the stored object all come
    from the shipped code, so a fixture cannot be a report the app could not
    have produced.
    """
    period = period_service.resolve(
        db,
        appointment,
        preset="30_days",
        today=now.date(),
    )
    data = preparation_service.build(db, profile, appointment, period)
    selection = snapshot_service.ReportSelection(
        symptom_episode_ids=[review.episode_id for review in data.symptoms],
        include_appendix=with_appendix,
    )
    report_service.generate(
        db,
        get_object_store(),
        get_pdf_service(),
        profile,
        appointment,
        selection=selection,
        period=period,
        now=now,
    )


def set_appointments(db: Session, user: User, preset: str, timezone: str) -> None:
    """Builds the appointment states PRD 7 section 69 asks a developer for.

    Two states on that list cannot be seeded from here. An *appointment with no
    health data* is not an appointment setting at all -- it is an account with
    nothing recorded, which is what ``--health empty --medications empty
    --symptoms empty`` produces. And an *offline question draft* lives only on
    the phone, in the app's own queue, so the server has by definition never
    heard of it; a developer reaches it by turning off Wi-Fi and adding a
    question.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to see a doctor.")
    assert profile is not None

    _clear_appointments(db, profile)
    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s appointments.")
        return

    now = datetime.now(UTC)
    clinician = _seed_clinician(db, profile)

    # 1. Tomorrow, with a clinician and questions already added. The main
    #    Prepare for Appointment target, and the one Important Today shows.
    tomorrow = _seed_appointment(
        db,
        profile,
        title="Cardiology follow-up",
        when=now + timedelta(days=1),
        timezone=timezone,
        clinician=clinician,
        location_name="City Hospital",
        notes="Bring the previous scan.",
    )
    for text in (
        "Could this medication be contributing to my fatigue?",
        "Should I continue physiotherapy when my knee hurts?",
        "Do I need any follow-up tests?",
    ):
        question_service.create_question(db, tomorrow, text=text)
    appointment_service.refresh_preparation_status(db, tomorrow)

    # 2. Today, with nothing prepared. This is the row Important Today raises,
    #    and the only one it ever raises (PRD 7, section 10).
    _seed_appointment(
        db,
        profile,
        title="Physiotherapy",
        when=now + timedelta(hours=5),
        timezone=timezone,
        appointment_type="physiotherapy",
        location_name="Riverside Clinic",
    )

    # 3. A past appointment, completed, carrying both kinds of report: one
    #    summary-only and one with the detailed appendix (PRD 7, sections 26-27).
    past = _seed_appointment(
        db,
        profile,
        title="Annual review",
        when=now - timedelta(days=21),
        timezone=timezone,
        clinician=clinician,
        appointment_type="primary_care",
    )
    appointment_service.complete_appointment(
        db,
        past,
        now - timedelta(days=21),
        visit_notes="Doctor said continue at a lower intensity.",
        follow_up_date=(now + timedelta(days=60)).date(),
    )
    _seed_report(db, profile, past, with_appendix=False, now=now - timedelta(days=21))
    _seed_report(db, profile, past, with_appendix=True, now=now - timedelta(days=20))

    # 4. A cancelled appointment, so the third history list is not empty.
    cancelled = _seed_appointment(
        db,
        profile,
        title="Dentist",
        when=now + timedelta(days=9),
        timezone=timezone,
        appointment_type="dentist",
    )
    appointment_service.cancel_appointment(db, cancelled, now - timedelta(days=1))

    # 5. A bare appointment: no clinician, no location, no questions. What most
    #    real ones look like when somebody has just noted a date down.
    _seed_appointment(
        db,
        profile,
        title="Blood test",
        when=now + timedelta(days=4),
        timezone=timezone,
        appointment_type="lab",
    )

    summary = appointment_summary.build_summary(db, profile.id, now.date(), now)
    versions = len(report_service.list_reports(db, past.id))
    print(
        f"{profile.preferred_name} now has {summary.upcoming_count} upcoming "
        f"appointments: a prepared cardiology follow-up tomorrow, an unprepared "
        f"physiotherapy session today, a blood test, plus a completed annual "
        f"review with {versions} report versions and a cancelled dentist visit. "
        "An offline question draft cannot be seeded -- it only exists on a phone."
    )


# --- the Nura assistant (PRD 8, section 104) --------------------------------


def _clear_assistant(db: Session, profile: Profile) -> None:
    """Removes conversations, memories and preferences for this profile.

    Not the health record, not the appointments, not the symptoms -- PRD 8
    section 61 is exactly this rule, and a seed script that broke it would be
    a very confusing way to find out.
    """
    for conversation in (
        db.execute(select(Conversation).where(Conversation.profile_id == profile.id))
        .scalars()
        .all()
    ):
        db.delete(conversation)
    for memory in (
        db.execute(
            select(AssistantMemory).where(AssistantMemory.profile_id == profile.id)
        )
        .scalars()
        .all()
    ):
        db.delete(memory)
    db.commit()


def _seed_conversation(
    db: Session,
    profile: Profile,
    *,
    title: str,
    lines: list[tuple[str, str]],
    when: datetime,
    safety_mode: str = "normal",
    meta: dict[str, Any] | None = None,
) -> Conversation:
    """One thread, written through the real service so the rows are real."""
    conversation = conversation_service.create_conversation(db, profile.id, title=title)
    for index, (role, content) in enumerate(lines):
        conversation_service.append_message(
            db,
            conversation,
            role=role,
            content=content,
            now=when + timedelta(seconds=index * 20),
            safety_mode=safety_mode if role == "assistant" else "normal",
            message_type="text",
            meta=(meta or {}) if role == "assistant" else {},
        )
    return conversation


def set_assistant(db: Session, user: User, preset: str) -> None:
    """Builds the assistant states PRD 8 section 104 asks a developer for.

    ``empty`` is the profile with no memories and nothing said. ``demo`` is
    the rest of the list: several memories, custom instructions, a thread
    with a tool call in it, a serious-mode thread, and a profile in Privacy
    mode -- reached with ``--assistant privacy``.

    Two states on that list are not seeded from here. A *provider timeout*
    and a *provider error* are properties of the model connection, not of
    the database: set ``AI_PROVIDER=`` to see the unconfigured path, or
    point ``AI_API_KEY`` at a wrong value to see a real failure translated.
    Nothing here fakes either, because a fixture that pretends the provider
    failed would be testing the fixture.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to talk to.")
    assert profile is not None

    _clear_assistant(db, profile)
    preferences = preference_service.get_or_create(db, profile.id)

    if preset == "empty":
        preference_service.update(
            db,
            preferences,
            {
                "personality_preset": preference_service.DEFAULT_PRESET,
                "custom_instructions": "",
                "mode": "normal",
                "proactivity": "low",
            },
        )
        print(f"cleared {profile.preferred_name}'s conversations and memories.")
        return

    now = datetime.now(UTC)

    preference_service.update(
        db,
        preferences,
        {
            "personality_preset": "friendly",
            "verbosity": "balanced",
            "proactivity": "high",
            "custom_instructions": (
                "Keep morning conversations short. Explain medical words simply."
            ),
            "mode": "privacy" if preset == "privacy" else "normal",
        },
    )

    for category, content in (
        ("communication", "Prefers to be called Baba."),
        ("communication", "Wants medical words explained simply."),
        ("routine", "Morning responses should be concise."),
        ("preferences", "Prefers short answers."),
    ):
        memory_service.create_memory(
            db,
            profile.id,
            category=category,
            content=content,
            source="conversation" if category == "routine" else "user",
            now=now,
        )

    # 1. An ordinary thread. What the history list mostly looks like.
    _seed_conversation(
        db,
        profile,
        title="What does inflammation mean?",
        when=now - timedelta(days=3),
        lines=[
            ("user", "What does inflammation mean?"),
            (
                "assistant",
                "Inflammation is the body's response to injury or infection. "
                "It is what causes redness, warmth and swelling around an "
                "affected area, and it is part of healing rather than a "
                "condition in itself.",
            ),
        ],
        meta={
            "model": "seeded",
            "tools": [],
            "safety_mode": "normal",
            "prompt_version": 1,
            "latency_ms": 1200,
        },
    )

    # 2. A thread with a tool call in it -- the row that proves the tool
    #    metadata renders, without a model having been called.
    _seed_conversation(
        db,
        profile,
        title="What's on today?",
        when=now - timedelta(days=1),
        lines=[
            ("user", "What's on today?"),
            (
                "assistant",
                "You have two doses still to record today and your cardiology "
                "follow-up is tomorrow at 3:30 PM. Today's check-in has not "
                "been done yet.",
            ),
        ],
        meta={
            "model": "seeded",
            "tools": ["get_today_summary"],
            "safety_mode": "normal",
            "prompt_version": 1,
            "latency_ms": 2100,
        },
    )

    # 3. A serious-mode thread, so the banner and the tone have something to
    #    render against (PRD 8, sections 37 and 69).
    _seed_conversation(
        db,
        profile,
        title="Should I stop taking my tablets?",
        when=now - timedelta(hours=4),
        safety_mode="serious",
        lines=[
            ("user", "Should I stop taking my tablets? They make me tired."),
            (
                "assistant",
                "I can show the schedule you've recorded, but changes to dose "
                "or whether to stop a medication should come from your "
                "clinician or pharmacist.\n\nYou have two medications with an "
                "active schedule. Tiredness is worth raising at your "
                "appointment tomorrow -- shall I add it to your questions?"
                "\n\nFor advice about changing or missing a dose, follow your "
                "clinician or pharmacist's instructions.",
            ),
        ],
        meta={
            "model": "seeded",
            "tools": ["get_active_medications"],
            "safety_mode": "serious",
            "prompt_version": 1,
            "latency_ms": 1800,
        },
    )

    mode = "privacy mode, " if preset == "privacy" else ""
    print(
        f"seeded {profile.preferred_name}'s assistant: {mode}"
        "4 memories, custom instructions, 3 conversations."
    )


# --- caregivers, family messages and emergency contacts (PRD 9) -------------


def _clear_caregivers(db: Session, profile: Profile) -> None:
    """Removes every PRD 9 row for this profile and nothing else.

    The health record, the medications, the symptoms, the appointments and the
    conversations are deliberately untouched: a developer reaching for caregiver
    fixtures has not asked to lose somebody's medication schedule, and there is
    no foreign key from a caregiver table into any of it that could take one with
    it.
    """
    relationships = (
        db.execute(
            select(CaregiverRelationship).where(
                CaregiverRelationship.profile_id == profile.id
            )
        )
        .scalars()
        .all()
    )
    for relationship in relationships:
        thread = db.execute(
            select(FamilyThread).where(FamilyThread.relationship_id == relationship.id)
        ).scalar_one_or_none()
        if thread is not None:
            db.delete(thread)
    for suggestion in (
        db.execute(
            select(CaregiverSuggestion).where(
                CaregiverSuggestion.profile_id == profile.id
            )
        )
        .scalars()
        .all()
    ):
        db.delete(suggestion)
    for relationship in relationships:
        db.delete(relationship)
    for contact in (
        db.execute(
            select(EmergencyContact).where(EmergencyContact.profile_id == profile.id)
        )
        .scalars()
        .all()
    ):
        db.delete(contact)
    for event in (
        db.execute(
            select(CaregiverAuditEvent).where(
                CaregiverAuditEvent.profile_id == profile.id
            )
        )
        .scalars()
        .all()
    ):
        db.delete(event)
    db.commit()


def _caregiver_account(db: Session, label: str) -> User:
    """A second account to play the caregiver, created on demand.

    Development only, and it is a real account row -- the same thing a second
    sign-in would produce -- because a caregiver fixture whose account does not
    exist cannot be signed in as, which is the whole point of having one.

    No profile is created for it. Section 14: supporting somebody must not
    require having a health profile of your own, and the fixtures are the place
    to prove that holds.
    """
    subject = f"dev-caregiver-{label}"
    existing = db.execute(
        select(User).where(User.auth_provider_id == subject)
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    account = User(
        auth_provider_id=subject,
        email=f"{label}@caregiver.invalid",
        onboarding_status="authenticated",
    )
    account.settings = UserSettings()
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _seed_relationship(
    db: Session,
    profile: Profile,
    inviter: User,
    *,
    label: str,
    name: str,
    role: str,
    permissions: dict[str, bool],
    status: str,
    now: datetime,
) -> CaregiverRelationship:
    """One relationship in whichever state the fixture wants.

    Built through the invitation service for ``pending`` and ``active`` so the
    token contract, the permission rows and the audit trail are the real ones --
    a fixture that inserted rows directly would be a fixture that disagrees with
    production about what a caregiver is.
    """
    minted = invitation_service.invite(
        db,
        profile,
        inviter,
        invited_name=name,
        role=role,
        permission_keys=permissions,
        email=f"{label}@caregiver.invalid",
        now=now,
    )
    relationship = minted.relationship
    if status == "pending":
        print(
            f"  invitation for {name} (expires {relationship.invite_expires_at:%d %b}):"
        )
        print(f"    {minted.token}")
        return relationship

    account = _caregiver_account(db, label)
    relationship = invitation_service.accept(db, minted.token, account, now=now)
    if status == "revoked":
        relationship_service.revoke(db, relationship, inviter, now=now)
    return relationship


def set_caregivers(db: Session, user: User, preset: str, timezone: str) -> None:
    """Builds the caregiver states PRD 9 section 98 asks a developer for.

    ``empty`` is the profile with nobody helping. ``demo`` is the rest of the
    list: a pending invitation, an active caregiver with limited permissions, a
    primary caregiver with broad permissions, a revoked caregiver, a pending
    medication suggestion, an approved one, a family thread with messages and
    three emergency contacts. ``multi`` additionally makes one caregiver account
    support a second profile, which is section 56's case.

    One item on section 98's list is not seeded from here: *a caregiver
    supporting two profiles* needs a second profile to support, so ``multi``
    creates one rather than pretending. And nothing here fabricates a safety
    alert: section 94 says the permission key may exist before its event source
    does, and a fixture that invented one would be the fabrication section 94
    rules out.

    The invitation tokens are printed. That is safe only because this script
    refuses to run outside development -- the stored value is still a hash, and
    an invitation is single-use and expires.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to care for.")
    assert profile is not None

    zone = ZoneInfo(timezone)
    now = datetime.now(tz=UTC)
    _clear_caregivers(db, profile)

    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s caregivers, messages and contacts.")
        return

    # A caregiver with a little, a caregiver with a lot, one who never answered,
    # and one who was removed.
    limited = _seed_relationship(
        db,
        profile,
        user,
        label="ayesha",
        name="Ayesha",
        role="family",
        permissions={"medications": True, "appointments": True, "communication": True},
        status="active",
        now=now,
    )
    _seed_relationship(
        db,
        profile,
        user,
        label="bilal",
        name="Bilal",
        role="primary_caregiver",
        permissions={
            "medications": True,
            "appointments": True,
            "symptoms": True,
            "reports": True,
            "communication": True,
            "general_health_summary": True,
        },
        status="active",
        now=now,
    )
    _seed_relationship(
        db,
        profile,
        user,
        label="carmen",
        name="Carmen",
        role="caregiver",
        permissions={"appointments": True},
        status="pending",
        now=now,
    )
    _seed_relationship(
        db,
        profile,
        user,
        label="dara",
        name="Dara",
        role="family",
        permissions={"medications": True},
        status="revoked",
        now=now,
    )

    # A pending suggestion and an approved one, against a real schedule if there
    # is one. No schedule means no medication suggestion, rather than a
    # suggestion pointing at nothing.
    schedule = db.execute(
        select(MedicationSchedule)
        .where(MedicationSchedule.profile_id == profile.id)
        .order_by(MedicationSchedule.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    suggestion_note = "no medication schedule, so no medication suggestion"
    if schedule is not None:
        scope = permission_service.resolve_scope(
            db, _caregiver_account(db, "ayesha"), profile.id
        )
        pending = suggestion_service.create(
            db,
            scope,
            action_type="change_medication_reminder_time",
            payload={"times": [{"time_of_day": "20:00"}]},
            target_resource_id=schedule.id,
            now=now,
        )
        approved = suggestion_service.create(
            db,
            scope,
            action_type="resume_medication_reminder",
            target_resource_id=schedule.id,
            now=now,
        )
        suggestion_service.approve(db, profile, approved, user, now=now)
        suggestion_note = f"1 pending suggestion ({pending.action_type}), 1 approved"

    # A thread with something in it from both sides, and a check-in.
    owner_scope = permission_service.resolve_scope(db, user, profile.id)
    caregiver_scope = permission_service.resolve_scope(
        db, _caregiver_account(db, "ayesha"), profile.id
    )
    thread = message_service.get_or_create_thread(db, limited, now=now)
    message_service.send_message(
        db,
        caregiver_scope,
        thread,
        sender_account_id=_caregiver_account(db, "ayesha").id,
        message_type="check_in",
        check_in_code="how_are_you",
        now=now - timedelta(hours=3),
    )
    message_service.send_message(
        db,
        owner_scope,
        thread,
        sender_account_id=user.id,
        message_type="check_in",
        check_in_code="im_okay",
        now=now - timedelta(hours=2, minutes=55),
    )
    message_service.send_message(
        db,
        caregiver_scope,
        thread,
        sender_account_id=_caregiver_account(db, "ayesha").id,
        message_type="text",
        text="Good. I'll bring the prescription over on Saturday.",
        now=now - timedelta(minutes=40),
    )

    # The chain PRD 10 will escalate through. Nothing in PRD 9 walks it.
    for index, (name, relationship_label, phone) in enumerate(
        (
            ("Bilal", "Son", "+447700900111"),
            ("Ayesha", "Daughter", "+447700900222"),
            ("Hana", "Neighbour", "+447700900333"),
        ),
        start=1,
    ):
        contact_service.create_contact(
            db,
            profile,
            contact_service.ContactInput(
                name=name, phone=phone, relationship_label=relationship_label
            ),
            user,
            now=now,
        )
        assert index <= contact_service.MAX_CONTACTS

    if preset == "multi":
        # Section 56: one caregiver account, two people, independent permissions.
        # Reused rather than recreated, so running this twice gives one second
        # person instead of a pile of them -- the fixtures are re-run constantly
        # and nothing here should accumulate.
        second = next(
            (
                link.profile
                for link in user.profile_roles
                if link.profile.preferred_name == SECOND_PROFILE_NAME
            ),
            None,
        )
        if second is None:
            second = Profile(preferred_name=SECOND_PROFILE_NAME)
            db.add(second)
            db.flush()
            db.add(
                AccountProfileRole(
                    account_id=user.id, profile_id=second.id, role="setup_helper"
                )
            )
            db.commit()
            db.refresh(user)
        else:
            _clear_caregivers(db, second)
        _seed_relationship(
            db,
            profile=second,
            inviter=user,
            label="ayesha",
            name="Ayesha",
            role="family",
            permissions={"symptoms": True},
            status="active",
            now=now,
        )
        print(f"  Ayesha also supports {second.preferred_name} (symptoms only)")

    local = now.astimezone(zone)
    print(
        f"seeded {profile.preferred_name}'s care network as of {local:%d %b %H:%M %Z}: "
        "2 active caregivers, 1 pending invitation, 1 revoked, "
        f"{suggestion_note}, a thread with 3 messages, 3 emergency contacts."
    )
    print(
        "  sign in as a caregiver with the accounts above "
        "(auth subject 'dev-caregiver-<name>')."
    )


# --- safety monitoring and SOS (PRD 10, sections 18, 53 and 114) -------------
#
# This is PRD 10's developer trigger harness, and section 18 is specific about
# where it may live: tests, seed scripts or developer diagnostics -- and **not**
# a production-visible fake emergency control. There is no such control in the
# app and there never will be: what a detector has is a device token and an
# authenticated route, so what a developer needs in order to exercise the
# detector path is a device token and a curl command.
#
# Nothing here fabricates a safety *alert* for a caregiver out of nothing: the
# presets raise real events through ``services.safety.events``, and the
# caregiver alerts that follow are the ones escalation really created. A
# fixture that wrote an alert row directly would be the fabrication section 94
# warned against, one PRD later.


def _clear_safety(db: Session, profile: Profile) -> None:
    """Removes every PRD 10 row for this profile and nothing else.

    The caregiver relationships, the emergency contacts and the health record
    are deliberately untouched -- a developer reaching for safety fixtures has
    not asked to lose somebody's care network, and the contacts are what makes
    an escalation worth looking at.
    """
    for model in (
        SafetyAuditEvent,
        SafetyEscalationAttempt,
        SafetyAlert,
        SafetyEvent,
        SafetyMonitoringSession,
    ):
        for row in (
            db.execute(select(model).where(model.profile_id == profile.id))
            .scalars()
            .all()
        ):
            db.delete(row)
    db.commit()


def _describe_event(db: Session, event: SafetyEvent) -> None:
    """Prints what really happened, in the words the app would show.

    Straight from ``services.safety.wording``, so a developer reading the
    terminal sees the same sentences a user would -- including the ones saying
    a channel is not set up.
    """
    print(f"  {safety_wording.EVENT_TYPE_LABELS[event.event_type]} -- {event.status}")
    for attempt in safety_escalation.attempts_for(db, event.id):
        print(
            "    "
            + safety_wording.escalation_line(
                label=attempt.recipient_label,
                channel=attempt.channel,
                status=attempt.status,
            )
        )
    if event.escalation_outcome:
        print(f"    outcome: {safety_wording.OUTCOME_LABELS[event.escalation_outcome]}")


def set_safety(db: Session, user: User, preset: str, timezone: str) -> None:
    """Builds the safety states PRD 10 section 114 asks a developer for.

    ``empty``          nothing: no session, no events, no alerts.
    ``monitoring``     monitoring on for an hour, nothing else.
    ``possible-fall``  monitoring on and a check-in waiting, with its real
                       deadline -- the state section 23's prompt is for.
    ``no-response``    the same, with the deadline already past and escalation
                       run, which is what the maintenance worker would produce.
    ``sos``            an emergency request raised with monitoring off
                       (section 21), escalated, still live.
    ``history``        three finished events: a possible-distress check-in
                       answered "I'm okay" with no escalation at all, a
                       possible fall marked a false alarm, and an emergency
                       request that really escalated.

    Every preset goes through the same service the API does, so what a
    developer sees is what a user would -- including the lines saying phone
    calling and text messages are not set up in this build.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is nobody to watch over.")
    assert profile is not None

    zone = ZoneInfo(timezone)
    now = datetime.now(tz=UTC)
    _clear_safety(db, profile)

    if preset == "empty":
        print(f"cleared {profile.preferred_name}'s safety sessions, events and alerts.")
        return

    contacts = contact_service.list_contacts(db, profile.id, active_only=True)
    if not contacts:
        print(
            "  note: no emergency contacts. Escalation will report "
            "'no contacts' -- seed some with --caregivers demo."
        )

    if preset in ("monitoring", "possible-fall", "no-response"):
        session = safety_monitoring.start(
            db,
            profile,
            user,
            duration_mode="1_hour",
            timezone_name=timezone,
            now=now,
            second_prompt_enabled=preset == "no-response",
        )
        local_end = session.ends_at.astimezone(zone) if session.ends_at else None
        print(
            f"  Safety Monitoring on until {local_end:%H:%M %Z}"
            if local_end
            else "  Safety Monitoring on until turned off"
        )

    if preset == "possible-fall":
        event = safety_events.create(
            db,
            profile,
            event_type="possible_fall",
            trigger_source="developer_simulation",
            now=now,
            actor_account_id=None,
            actor_kind="system",
            idempotency_key=f"seed-{secrets.token_hex(6)}",
        )
        db.commit()
        deadline = event.response_deadline_at
        assert deadline is not None
        print(
            f"  a check-in is waiting until {deadline.astimezone(zone):%H:%M:%S %Z} "
            "-- answer it in the app, or let it run out"
        )

    if preset == "no-response":
        started = now - timedelta(minutes=5)
        event = safety_events.create(
            db,
            profile,
            event_type="possible_distress",
            trigger_source="developer_simulation",
            now=started,
            actor_account_id=None,
            actor_kind="system",
            idempotency_key=f"seed-{secrets.token_hex(6)}",
        )
        db.commit()
        # The same two steps the maintenance worker takes, with the clock
        # moved rather than waited out (section 82).
        safety_checks.advance(db, event, started + timedelta(seconds=46))
        db.commit()
        safety_checks.advance(db, event, started + timedelta(seconds=70))
        db.commit()
        db.refresh(event)
        _describe_event(db, event)

    if preset == "sos":
        event = safety_events.create(
            db,
            profile,
            event_type="manual_sos",
            trigger_source="mobile_manual",
            now=now,
            actor_account_id=user.id,
            actor_kind="primary_user",
        )
        db.commit()
        db.refresh(event)
        print("  an emergency request is live (monitoring was off -- section 21)")
        _describe_event(db, event)

    if preset == "history":
        # An open-ended session, so the two passive events are accepted at the
        # times they claim to have happened (section 22 is about monitoring
        # being on, not about the clock). It is stopped again at the end --
        # the fixture is a history, not a state.
        session = safety_monitoring.start(
            db,
            profile,
            user,
            duration_mode="until_turned_off",
            timezone_name=timezone,
            now=now - timedelta(days=4),
        )
        plan: list[tuple[str, str | None, str | None, int]] = [
            # A check-in answered in time: no escalation at all, which is the
            # whole of section 25 and the most important row in this list.
            ("possible_distress", "im_okay", None, 3),
            ("possible_fall", "false_alarm", "user_testing", 2),
            # And one that really escalated, so the lines saying a channel is
            # not set up are visible in the history too.
            ("manual_sos", None, None, 1),
        ]
        for event_type, answer, reason, days_ago in plan:
            when = now - timedelta(days=days_ago)
            event = safety_events.create(
                db,
                profile,
                event_type=event_type,
                trigger_source=(
                    "mobile_manual"
                    if event_type == "manual_sos"
                    else "developer_simulation"
                ),
                now=when,
                actor_account_id=user.id if event_type == "manual_sos" else None,
                actor_kind="primary_user" if event_type == "manual_sos" else "system",
                idempotency_key=f"seed-{secrets.token_hex(6)}",
            )
            db.commit()
            if answer is not None:
                safety_checks.respond(
                    db,
                    event,
                    response=answer,
                    actor=user,
                    now=when + timedelta(seconds=20),
                )
                if reason is not None:
                    safety_checks.mark_false_alarm(
                        db,
                        event,
                        user,
                        false_positive=True,
                        reason=reason,
                        now=when + timedelta(seconds=30),
                    )
            db.refresh(event)
            _describe_event(db, event)
        safety_monitoring.stop(db, session, user, now=now)

    capability = safety_capabilities.capability_map()
    unavailable = [key for key, state in capability.items() if state != "available"]
    print(
        f"seeded {profile.preferred_name}'s safety state ({preset}). "
        f"Not available in this build: {', '.join(unavailable)}."
    )
    print(
        "  simulate a robot detector with a device token:\n"
        "    python -m scripts.seed_dev --account latest --device-token\n"
        "    curl -X POST -H 'Authorization: Bearer <token>' "
        "-H 'Content-Type: application/json' \\\n"
        '      -d \'{"event_type": "possible_fall", '
        '"trigger_source": "developer_simulation", '
        '"idempotency_key": "sim-1"}\' \\\n'
        "      http://localhost:8000/api/v1/device-actions/safety-events"
    )


def _clear_daily_life(db: Session, profile: Profile) -> None:
    """Removes every PRD 12 row for this profile and nothing else.

    Children first, because a step completion points at a run and a run points
    at a routine. Nothing medical is touched: a task list is not a health
    record, which is the whole reason PRD 12 keeps its own tables.
    """
    for model in (
        RoutineStepCompletion,
        RoutineRun,
        RoutineStep,
        Routine,
        GeneralReminderOccurrence,
        GeneralReminder,
        Alarm,
        Task,
    ):
        for row in (
            db.execute(select(model).where(model.profile_id == profile.id))
            .scalars()
            .all()
        ):
            db.delete(row)
    db.commit()


def set_daily_life(db: Session, user: User, preset: str, timezone: str) -> None:
    """Builds the daily-life states PRD 12 section 70 asks a developer for.

    ``demo``  one of each: an overdue task, a task due today, a task with no
              due date at all (section 5's normal case), a daily reminder, a
              weekday alarm and a three-step morning routine with two steps
              already ticked. Enough to see every Today row type and the
              robot's four new cards.
    ``busy``  the same plus a second routine, a monthly reminder and a
              one-off alarm, for a Today screen with something in every group.
    ``empty`` clears every task, reminder, alarm and routine.

    No notification is scheduled by any of this and none could be: scheduling
    happens on the phone, and nothing in this project has ever run on one.
    """
    profile = profile_service.primary_profile(user)
    if profile is None:
        fail("this account has no profile yet, so there is no list to put a task on.")
    assert profile is not None

    _clear_daily_life(db, profile)
    if preset == "empty":
        print("  daily life: cleared every task, reminder, alarm and routine")
        return

    now = datetime.now(UTC)
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    today = local.date()

    # --- tasks (sections 5 and 6) -------------------------------------------
    task_service.create_task(
        db,
        profile.id,
        task_service.TaskInput(
            title="Call the physiotherapist",
            notes="Ask about the Thursday slot.",
            priority="important",
            due_at=(local - timedelta(hours=5)).astimezone(UTC),
            timezone=timezone,
        ),
        now,
    )
    task_service.create_task(
        db,
        profile.id,
        task_service.TaskInput(
            title="Collect the prescription",
            priority="normal",
            due_at=datetime.combine(today, time(17, 0), tzinfo=zone).astimezone(UTC),
            timezone=timezone,
        ),
        now,
    )
    # Section 5: a task with no time is a normal task, not an incomplete one.
    task_service.create_task(
        db,
        profile.id,
        task_service.TaskInput(title="Look into the walking group", timezone=timezone),
        now,
    )
    done = task_service.create_task(
        db,
        profile.id,
        task_service.TaskInput(title="Water the plants", timezone=timezone),
        now,
    )
    task_service.complete_task(db, done, now)

    # --- reminders (sections 7 and 8) ---------------------------------------
    general_reminder_service.create_reminder(
        db,
        profile.id,
        general_reminder_service.ReminderInput(
            title="Stand up and stretch",
            body="Just for a minute.",
            time_of_day=time(11, 0),
            start_date=today - timedelta(days=3),
            recurrence="daily",
            timezone=timezone,
        ),
        now,
    )
    general_reminder_service.create_reminder(
        db,
        profile.id,
        general_reminder_service.ReminderInput(
            title="Ring Mum",
            time_of_day=time(19, 30),
            start_date=today,
            recurrence="weekly",
            weekdays=[6],
            timezone=timezone,
        ),
        now,
    )

    # --- alarms (sections 10 and 11) ----------------------------------------
    alarm_service.create_alarm(
        db,
        profile.id,
        alarm_service.AlarmInput(
            label="Morning",
            time_of_day=time(7, 0),
            recurrence="selected_days",
            weekdays=[0, 1, 2, 3, 4],
            timezone=timezone,
        ),
        now,
    )

    # --- routines (sections 12 to 14) ---------------------------------------
    morning = routine_service.create_routine(
        db,
        profile.id,
        routine_service.RoutineInput(
            title="Morning routine",
            description="The three things that make the rest of the day easier.",
            time_of_day=time(8, 0),
            start_date=today - timedelta(days=7),
            schedule_type="daily",
            timezone=timezone,
        ),
        [
            routine_service.StepInput(title="Take tablets"),
            routine_service.StepInput(title="Stretch"),
            routine_service.StepInput(title="Short walk", optional=True),
        ],
        now,
    )
    runs = routine_service.runs_for_today(db, profile.id, now)
    today_run = next((run for run in runs if run.routine_id == morning.id), None)
    if today_run is not None:
        for step in morning.steps[:2]:
            routine_service.complete_step(db, today_run, step, now)

    if preset == "busy":
        general_reminder_service.create_reminder(
            db,
            profile.id,
            general_reminder_service.ReminderInput(
                title="Pay the electricity bill",
                time_of_day=time(9, 0),
                start_date=today,
                recurrence="monthly",
                day_of_month=min(today.day, 28),
                timezone=timezone,
            ),
            now,
        )
        alarm_service.create_alarm(
            db,
            profile.id,
            alarm_service.AlarmInput(
                label="Leave for the appointment",
                time_of_day=time(13, 45),
                recurrence="one_time",
                on_date=today + timedelta(days=2),
                timezone=timezone,
            ),
            now,
        )
        routine_service.create_routine(
            db,
            profile.id,
            routine_service.RoutineInput(
                title="Wind down",
                time_of_day=time(21, 30),
                start_date=today - timedelta(days=2),
                schedule_type="daily",
                timezone=timezone,
            ),
            [
                routine_service.StepInput(title="Put the phone down"),
                routine_service.StepInput(title="Lay out tomorrow's tablets"),
            ],
            now,
        )

    db.commit()

    summary = daily_life_summary.build_summary(
        db, profile.id, task_service.today_date(timezone, now), now
    )
    print(f"  daily life: {preset} ({timezone})")
    print(
        "    "
        + productivity_wording.today_summary_sentence(
            summary.tasks.due_today,
            summary.routines.due_today,
            summary.reminders.due_today,
        )
    )
    print(
        f"    tasks: {summary.tasks.due_today} due today, "
        f"{summary.tasks.overdue} overdue, {summary.tasks.open_total} open"
    )
    print(
        f"    reminders: {summary.reminders.due_today} today, "
        f"{summary.reminders.due_now} due now"
    )
    print(
        f"    routines: {summary.routines.due_today} today, "
        f"{summary.routines.in_progress} in progress, "
        f"{summary.routines.completed_today} complete"
    )
    if summary.next_alarm_at is not None:
        local_alarm = summary.next_alarm_at.astimezone(zone)
        print(
            f"    next alarm: {local_alarm:%a %d %b} at "
            f"{productivity_wording.format_clock(local_alarm.time())}"
        )
    # Section 11, said here too: a developer reading this terminal should not
    # have to find the completion report to learn what an alarm in this build
    # is.
    print(f"    {productivity_wording.ALARM_LIMITATION}")
    # Section 12: the three external capabilities read ``not_configured`` in
    # every deployment, and a developer looking for weather or news should
    # find that out here rather than from a model's answer.
    for key, state in daily_life_capabilities.external_states().items():
        print("    " + productivity_wording.capability_sentence(key=key, state=state))


def rotate_device_token(db: Session, user: User) -> None:
    """Issues a fresh device token and prints it (PRD 5, section 47).

    This is the whole of the "simulated robot" path. There is no pretend-robot
    button anywhere in the app, and there never will be: what a robot has is a
    device token, so what a developer needs in order to exercise the robot
    route is a device token.

    Printing it is safe *only* because this script refuses to run outside
    development. The stored value is still a hash, and rotating here has the
    same effect as a re-claim: any previous token stops working.

        curl -X POST \
          -H "Authorization: Bearer <the token below>" \
          http://localhost:8000/api/v1/device-actions/medication-doses/<dose id>/taken
    """
    device = seeded_device(db, user)
    if device is None:
        fail("seed a device first: --device offline")
    assert device is not None

    token = generate_token("nura-dev-")
    device.device_token_hash = hash_secret(token)
    db.commit()
    print(f"device token for {device.display_name} (development only):\n  {token}")


def _clear_robot(db: Session, device: Device) -> None:
    """Removes every PRD 11 row for this robot and nothing else.

    The device itself, its claim and its token are untouched: a developer
    reaching for presentation fixtures has not asked to unpair their robot.
    """
    for model in (DevicePresentation, DevicePresentationPreferences, DeviceCapability):
        for row in (
            db.execute(select(model).where(model.device_id == device.id)).scalars().all()
        ):
            db.delete(row)
    db.commit()


def _describe_screen(screen: robot_simulator.Screen | None) -> None:
    """Prints what a person standing in front of the robot would see."""
    if screen is None:
        print("    (nothing to show)")
        return
    print(f"    [{screen.layout}] mode={screen.mode}")
    for text in screen.lines:
        print(f"      | {text}")


def set_robot(db: Session, user: User, preset: str) -> None:
    """Builds the robot states PRD 11 section 132 asks a developer for.

    ``offline``    a claimed robot that has reported a screen and has not been
                   heard from for hours. Section 20's case: cards stay queued,
                   nothing is displayed, and the app says so.
    ``online``     the same robot, heartbeating now, with a screen reported
                   available. Section 132's first two steps.
    ``unverified`` a robot whose firmware has the display driver and has
                   proven nothing -- section 12's case, and what a real first
                   build would honestly report.
    ``headless``   a robot with no screen at all. Section 123's
                   ``not_supported``.
    ``speaker``    a robot reporting a working speaker, which nothing in this
                   project has ever produced. There to exercise the audio
                   settings and the read-aloud preferences (section 64).
    ``empty``      clears every presentation, preference and capability row.

    Every preset reconciles afterwards and prints what the robot would be
    handed, so the terminal shows the experience rather than a row count.
    """
    device = (
        db.execute(
            select(Device)
            .where(Device.claimed_by_account_id == user.id)
            .order_by(Device.created_at)
        )
        .scalars()
        .first()
    )
    if device is None:
        print("  no robot on this account -- run --device online first")
        return

    _clear_robot(db, device)
    if preset == "empty":
        print("  robot: cleared every presentation, preference and capability")
        return

    now = datetime.now(UTC)
    states = {
        "offline": robot_simulator.DISPLAY_ONLY,
        "online": robot_simulator.DISPLAY_ONLY,
        "unverified": robot_simulator.UNVERIFIED_DISPLAY,
        "headless": robot_simulator.HEADLESS,
        "speaker": robot_simulator.WITH_SPEAKER,
    }[preset]

    robot_capabilities.report(db, device, dict(states), now)
    device.last_seen_at = now - timedelta(hours=3) if preset == "offline" else now
    if device.setup_completed_at is None:
        device.setup_completed_at = now - timedelta(days=1)
    db.commit()

    result = robot_presenter.refresh(db, device, now)
    db.commit()

    print(f"  robot: {preset} ({device.hardware_id})")
    print(f"    mode {result.mode.mode}, {result.queue_depth} presentation(s) open")
    for view in robot_capabilities.views(db, device, now):
        if view.key in ("display", "display_text", "speaker", "buttons"):
            print(
                "    " + robot_wording.capability_sentence(key=view.key, state=view.state)
            )

    if preset == "offline":
        # Section 20: nothing is fetched, so nothing is displayed, and the
        # sentence the app shows comes from the server.
        print(f"    {robot_wording.OFFLINE_NOTE}")
        return

    simulated = robot_simulator.SimulatedRobot(
        db=db, device=device, capability_states=dict(states)
    )
    drawn = simulated.drain(now)
    db.commit()
    if not drawn:
        print("    nothing to draw yet -- add medications, appointments or messages")
    for screen in drawn:
        _describe_screen(screen)
    print(f"    {robot_wording.NO_HARDWARE_NOTE}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Seed development data for Today, the health record, "
            "medications, symptoms, appointments, the Nura assistant and "
            "the care network. Never for production."
        )
    )
    parser.add_argument("--list", action="store_true", help="show the known accounts")
    parser.add_argument(
        "--account",
        help="email, phone, auth subject, or 'latest' for the newest account",
    )
    parser.add_argument(
        "--device",
        choices=["online", "offline", "never-seen", "none"],
        help="what state the seeded robot should be in",
    )
    parser.add_argument(
        "--minutes-ago",
        type=int,
        default=42,
        help="how stale an --device offline heartbeat should be (default: 42)",
    )
    parser.add_argument(
        "--keep-online",
        type=int,
        metavar="SECONDS",
        help="keep refreshing the heartbeat, so the app stays on Online",
    )
    parser.add_argument(
        "--checkin",
        choices=["good", "okay", "not_great", "none"],
        help="set or clear today's check-in",
    )
    parser.add_argument("--note", help="optional note to store with --checkin")
    parser.add_argument(
        "--health",
        choices=["empty", "partial", "complete"],
        help="replace the health profile with a development fixture",
    )
    parser.add_argument(
        "--medications",
        choices=["empty", "demo"],
        help="replace medication schedules, doses and supply with fixtures",
    )
    parser.add_argument(
        "--timezone",
        default="UTC",
        help=(
            "IANA zone for --medications and --appointments demo "
            "(default: UTC). The app sends the phone's own zone; this is only "
            "for fixtures."
        ),
    )
    parser.add_argument(
        "--symptoms",
        choices=["empty", "demo"],
        help="replace symptom episodes, entries and photos with fixtures",
    )
    parser.add_argument(
        "--appointments",
        choices=["empty", "demo"],
        help="replace appointments, questions and generated reports with fixtures",
    )
    parser.add_argument(
        "--assistant",
        choices=["empty", "demo", "privacy"],
        help="replace Nura conversations, memories and preferences with fixtures",
    )
    parser.add_argument(
        "--caregivers",
        choices=["empty", "demo", "multi"],
        help=(
            "replace caregivers, family messages, suggestions and emergency "
            "contacts with fixtures"
        ),
    )
    parser.add_argument(
        "--safety",
        choices=[
            "empty",
            "monitoring",
            "possible-fall",
            "no-response",
            "sos",
            "history",
        ],
        help=(
            "PRD 10's developer trigger harness: replace safety sessions, "
            "events and alerts with fixtures"
        ),
    )
    parser.add_argument(
        "--robot",
        choices=["empty", "offline", "online", "unverified", "headless", "speaker"],
        help=(
            "PRD 11's robot presentation harness: replace the robot's "
            "capabilities, preferences and queued presentations with fixtures"
        ),
    )
    parser.add_argument(
        "--daily-life",
        choices=["empty", "demo", "busy"],
        help=(
            "PRD 12's daily-life fixtures: replace tasks, reminders, alarms "
            "and routines with fixtures"
        ),
    )
    parser.add_argument(
        "--device-token",
        action="store_true",
        help="issue and print a device token, to exercise the robot action route",
    )
    args = parser.parse_args()

    db = open_session()
    try:
        if args.list:
            users = db.execute(select(User).order_by(User.created_at)).scalars().all()
            if not users:
                print("no accounts yet.")
            for user in users:
                print(describe(db, user))
            if not args.account:
                return

        if not args.account:
            parser.error("--account is required (or use --list)")

        user = find_account(db, args.account)
        print(f"account: {describe(db, user)}")

        if args.device:
            set_device(db, user, args.device, args.minutes_ago)
        if args.checkin:
            set_checkin(db, user, args.checkin, args.note)
        if args.health:
            set_health(db, user, args.health)
        if args.medications:
            set_medications(db, user, args.medications, args.timezone)
        if args.symptoms:
            set_symptoms(db, user, args.symptoms)
        if args.appointments:
            set_appointments(db, user, args.appointments, args.timezone)
        if args.assistant:
            set_assistant(db, user, args.assistant)
        if args.caregivers:
            set_caregivers(db, user, args.caregivers, args.timezone)
        if args.safety:
            set_safety(db, user, args.safety, args.timezone)
        if args.robot:
            set_robot(db, user, args.robot)
        if args.daily_life:
            set_daily_life(db, user, args.daily_life, args.timezone)
        if args.device_token:
            rotate_device_token(db, user)
        if args.keep_online:
            keep_online(db, user, args.keep_online)

        if not (
            args.device
            or args.checkin
            or args.keep_online
            or args.health
            or args.medications
            or args.symptoms
            or args.appointments
            or args.assistant
            or args.caregivers
            or args.safety
            or args.robot
            or args.daily_life
            or args.device_token
        ):
            print(
                "nothing to do -- pass --device, --checkin, --health, "
                "--medications, --symptoms, --appointments, --assistant, "
                "--caregivers, --safety, --robot, --daily-life and/or "
                "--device-token."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
