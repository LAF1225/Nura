"""Keeps medication doses current for every profile (PRD 5, section 71).

Two jobs, both of which the app already triggers for whoever is using it:

  - top each active schedule's dose window back up to the horizon
  - record doses that have passed their grace period as missed

**Nothing depends on this running.** Every read of Today, of the dose list and
of adherence replenishes the profile it is about first, so an app that is
opened is always correct. This exists for the profile nobody opened: somebody
whose phone was off for a week should still find last Tuesday recorded
honestly rather than sitting as "scheduled" forever.

So it is deliberately the simplest mechanism that works -- a script, run by
whatever the deployment already has (cron, a scheduled task, a container's
own scheduler). PRD 5 section 71 asks for exactly that and warns against
adding distributed infrastructure for it. It is idempotent and safe to run as
often as you like; hourly is plenty.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.medication_maintenance
    python -m scripts.medication_maintenance --dry-run

Unlike ``seed_dev``, this one is meant for production: it writes only what the
app would have written anyway, and it never invents a dose, an action or a
status the rules do not already imply.
"""

import argparse
import logging
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Profile
from app.services.medications import doses as dose_service

logger = logging.getLogger("nura.medication_maintenance")


def open_session() -> Session:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def profiles_with_schedules(db: Session) -> list[Profile]:
    """Only profiles that actually have a schedule.

    Everyone else has nothing to generate and nothing to miss, and walking
    them would turn a cheap job into a full table scan for no result.
    """
    from app.models import MedicationSchedule

    return list(
        db.execute(
            select(Profile)
            .join(MedicationSchedule, MedicationSchedule.profile_id == Profile.id)
            .distinct()
        )
        .scalars()
        .all()
    )


def run(db: Session, now: datetime, *, dry_run: bool = False) -> tuple[int, int, int]:
    """Returns (profiles seen, doses generated, doses marked missed)."""
    profiles = profiles_with_schedules(db)
    generated = missed = 0

    for profile in profiles:
        for schedule in dose_service.active_schedules(db, profile.id):
            generated += len(dose_service.generate_for_schedule(db, schedule, now))
        missed += dose_service.mark_missed(db, profile.id, now)

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

    # Counts only. No profile id, no medication, no time -- the same rule the
    # services follow (PRD 5, sections 58 and 59).
    prefix = "would have " if args.dry_run else ""
    logger.info(
        "medication maintenance: %d profiles, %s%d doses generated, %s%d marked missed",
        profiles,
        prefix,
        generated,
        prefix,
        missed,
    )


if __name__ == "__main__":
    main()
