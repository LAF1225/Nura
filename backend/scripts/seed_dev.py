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

``--account`` takes an email, a phone number, an auth provider subject, or
``latest`` for the most recently created account -- which during development is
almost always the one signed in on the phone.
"""

import argparse
import secrets
import sys
import time
from datetime import UTC, date, datetime, timedelta
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
    Procedure,
    Profile,
    User,
)
from app.services import checkins as checkin_service
from app.services import health as health_service
from app.services import profiles as profile_service
from app.services.devices import ONLINE_THRESHOLD, hash_secret

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

    deadline = time.monotonic() + seconds
    print(f"holding {device.display_name} online for {seconds}s. Ctrl-C to stop.")
    try:
        while time.monotonic() < deadline:
            device.last_seen_at = datetime.now(UTC)
            db.commit()
            time.sleep(
                min(KEEP_ALIVE_INTERVAL_SECONDS, max(1, int(deadline - time.monotonic())))
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed development data for the Today screen. Never for production."
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
        if args.keep_online:
            keep_online(db, user, args.keep_online)

        if not (args.device or args.checkin or args.keep_online or args.health):
            print("nothing to do -- pass --device, --checkin and/or --health.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
