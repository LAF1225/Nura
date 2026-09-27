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

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import (
    Allergy,
    Clinician,
    DailyCheckIn,
    Device,
    HealthRecord,
    MedicalCondition,
    MedicalNote,
    Medication,
    MedicationDose,
    MedicationSchedule,
    Procedure,
    Profile,
    SymptomEntry,
    SymptomEpisode,
    SymptomPhoto,
    User,
)
from app.services import checkins as checkin_service
from app.services import health as health_service
from app.services import profiles as profile_service
from app.services.devices import ONLINE_THRESHOLD, generate_token, hash_secret
from app.services.medications import doses as dose_service
from app.services.medications import schedules as schedule_service
from app.services.medications import supply as supply_service
from app.services.storage import get_object_store
from app.services.symptoms import episodes as episode_service
from app.services.symptoms import photos as photo_service
from app.services.symptoms import summary as symptom_summary

#: Deliberately not a real MAC address. A physical XIAO reports its factory
#: MAC, so a seeded row can never collide with a board you later build.
SEEDED_HARDWARE_ID = "NURA-DEADBEEF0001"

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Seed development data for Today, the health record, "
            "medications and symptoms. Never for production."
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
            "IANA zone for --medications demo (default: UTC). The app sends "
            "the phone's own zone; this is only for fixtures."
        ),
    )
    parser.add_argument(
        "--symptoms",
        choices=["empty", "demo"],
        help="replace symptom episodes, entries and photos with fixtures",
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
            or args.device_token
        ):
            print(
                "nothing to do -- pass --device, --checkin, --health, "
                "--medications, --symptoms and/or --device-token."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
