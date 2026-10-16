"""Keeps the presentation queue tidy.

PRD 11, sections 18, 20, 55, 56 and 99.

**Nothing depends on this running**, and that is the difference between this
script and PRD 10's. The safety worker is load-bearing: a response deadline
that passes with nobody looking is exactly the case Safety Monitoring exists
for, so without it escalation is not *timely*. Here there is no deadline whose
passing has to cause anything. Expiry is applied on every read -- the device's
fetch, the heartbeat, the app's status read and the history endpoint all call
``queue.expire_due`` first -- so a presentation is never handed over late
whether or not this has run.

What it does is housekeeping. A robot that was unplugged a month ago leaves
rows sitting in ``queued``, and a table of stale rows makes the app's history
screen and the queue-depth diagnostic read as though something is waiting. One
pass a few times an hour is plenty.

Two jobs, both idempotent:

    expire presentations whose moment has passed
    withdraw presentations belonging to robots that are no longer claimed

Running it twice changes nothing the second time: both select on statuses they
move rows out of.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.robot_maintenance
    python -m scripts.robot_maintenance --dry-run

**It cannot cause anything to be shown.** Nothing here queues a presentation,
and nothing here acknowledges one -- so no row this script touches can end up
claiming a robot displayed anything (sections 14 and 20).
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Device, DevicePresentation
from app.models.enums import ROBOT_PRESENTATION_OPEN_STATUSES
from app.services.robot import queue

logger = logging.getLogger("nura.robot_maintenance")


@dataclass(frozen=True)
class Result:
    """What one run did. Counts only: a payload has no business in a log."""

    presentations_expired: int
    presentations_withdrawn: int


def open_session() -> Session:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def run(db: Session, now: datetime, *, dry_run: bool = False) -> Result:
    """One pass. Commits per job, so a failure late does not undo work early."""
    expired = queue.expire_due(db, now)
    if dry_run:
        db.rollback()
    else:
        db.commit()

    withdrawn = 0
    for row in unlinked(db):
        queue.cancel(db, row, reason="device_unlinked", now=now)
        withdrawn += 1
    if dry_run:
        db.rollback()
    else:
        db.commit()

    return Result(presentations_expired=expired, presentations_withdrawn=withdrawn)


def unlinked(db: Session) -> list[DevicePresentation]:
    """Open presentations for a robot that is no longer claimed.

    PRD 2 keeps a device row when an account releases ownership, so a card
    queued before that stays otherwise valid for a robot nobody owns. It will
    never be fetched -- the device token is gone -- and leaving it ``queued``
    would make the history read as though something is still waiting.
    """
    return list(
        db.execute(
            select(DevicePresentation)
            .join(Device, Device.id == DevicePresentation.device_id)
            .where(
                DevicePresentation.status.in_(ROBOT_PRESENTATION_OPEN_STATUSES),
                Device.claimed_by_account_id.is_(None),
            )
        )
        .scalars()
        .all()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing anything.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = datetime.now(UTC)
    db = open_session()
    try:
        result = run(db, now, dry_run=args.dry_run)
    finally:
        db.close()

    logger.info(
        "robot maintenance%s: %d expired, %d withdrawn",
        " (dry run)" if args.dry_run else "",
        result.presentations_expired,
        result.presentations_withdrawn,
    )


if __name__ == "__main__":
    main()
