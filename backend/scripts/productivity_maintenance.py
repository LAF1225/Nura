"""Keeps reminder occurrences and routine runs current (PRD 12, section 63).

Section 63 asks for two dependencies to be documented separately, so here they
are, plainly.

**State correctness does not depend on this.** Every read of Today, of the
reminder list, of the routine list and of the daily-life summary replenishes
the profile it is about first -- generate forward, mark what was missed -- so
anybody who opens the app sees the truth whether or not this has ever run. The
same shape PRD 5 gave doses, for the same reason: a product whose correctness
depends on a cron job is a product that is wrong whenever the cron job is.

**Timeliness does depend on it, and only for somebody who is not looking.** A
person whose phone has been off for a week should find last Tuesday's reminder
recorded honestly rather than sitting as "scheduled" forever, and tomorrow's
occurrences should exist before their phone asks for them rather than being
created by the asking. That is what this is for.

**Nothing in this repository schedules it.** There is no cron entry, no systemd
timer and no container scheduler configured anywhere in the project, and
section 63 is explicit that a scheduler must not be implied if one is not
actually configured. If you want it run, run it from whatever the deployment
already has; hourly is plenty and it is idempotent.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.productivity_maintenance
    python -m scripts.productivity_maintenance --dry-run

Meant for production: it writes only what the app would have written anyway,
and it never invents an occurrence, a run, an action or a status the rules do
not already imply.
"""

import argparse
import logging
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import GeneralReminder, Profile, Routine
from app.services.productivity import reminders as reminder_service
from app.services.productivity import routines as routine_service

logger = logging.getLogger("nura.productivity_maintenance")


def open_session() -> Session:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def profiles_with_daily_life(db: Session) -> list[Profile]:
    """Only profiles that actually have a reminder or a routine.

    Everyone else has nothing to generate and nothing to miss, and walking
    them would turn a cheap job into a full table scan for no result. Tasks and
    alarms are deliberately absent from this query: a task generates nothing
    and never becomes ``missed``, and an alarm has no rows at all -- "is it
    ringing" is derived from the clock.
    """
    reminders = select(Profile).join(
        GeneralReminder, GeneralReminder.profile_id == Profile.id
    )
    routines = select(Profile).join(Routine, Routine.profile_id == Profile.id)
    rows = list(db.execute(reminders.union(routines)).all())
    ids = {row[0] for row in rows}
    if not ids:
        return []
    return list(db.execute(select(Profile).where(Profile.id.in_(ids))).scalars().all())


def run(db: Session, now: datetime, *, dry_run: bool = False) -> tuple[int, int, int]:
    """Returns (profiles seen, occurrences and runs generated, rows marked missed)."""
    profiles = profiles_with_daily_life(db)
    generated = missed = 0

    for profile in profiles:
        for reminder in reminder_service.active_reminders(db, profile.id):
            generated += len(reminder_service.generate_for_reminder(db, reminder, now))
        missed += reminder_service.mark_missed(db, profile.id, now)

        for routine in routine_service.list_routines(db, profile.id, active_only=True):
            generated += len(routine_service.generate_for_routine(db, routine, now))
        missed += routine_service.mark_missed(db, profile.id, now)

        if dry_run:
            db.rollback()
        else:
            db.commit()

    return len(profiles), generated, missed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    with open_session() as db:
        profiles, generated, missed = run(db, datetime.now(UTC), dry_run=args.dry_run)

    # Counts only. No profile id, no title, no time -- the same rule the
    # services follow (PRD 12, sections 45 and 46).
    prefix = "would have " if args.dry_run else ""
    logger.info(
        "productivity maintenance: %d profiles, %s%d generated, %s%d marked missed",
        profiles,
        prefix,
        generated,
        prefix,
        missed,
    )


if __name__ == "__main__":
    main()
