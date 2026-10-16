"""Makes safety timeouts happen for somebody who is not looking at their phone.

PRD 10, sections 27, 28, 79, 80, 81, 112 and 124.

**What this is for, stated precisely** (section 80 asks for the distinction in
writing).

*State correctness* does not need this script. Every read of the safety status
advances a deadline that has passed, so whoever opens the app sees the true
state whether or not anything else has run -- the same way PRD 5 replenishes
doses on every read.

*Timely escalation* does. Somebody whose phone is in another room is not
reading anything, and a response deadline that expires with nobody looking is
exactly the case this feature exists for. **Without this script running,
escalation happens when the event is next read, which may be much later or
never.** That is the honest limit, it is why section 80 insists on the
distinction, and it is why ``tests/test_safety_worker.py`` runs this code
rather than asserting that it would work.

**Four jobs, all idempotent** (section 81):

    expire monitoring sessions whose time is up
    process response deadlines -- second prompt, or escalate
    retry provider attempts that failed and are due
    nothing else

Running it twice changes nothing the second time: every transition it makes
moves a status out of the set it selects on, every attempt is unique on
(event, recipient, channel), and every alert is unique on (event, account).
Section 112 tests exactly that.

**It is a script, not infrastructure** (section 79). Run it from cron, a
scheduled task or a container's own scheduler. **Once a minute** is the right
cadence here, unlike the medication job's hourly: the shortest response
timeout is fifteen seconds, and a worker that runs hourly turns a 45-second
promise into an hour-long one. The honest statement for a deployment that
cannot run it that often is that escalation is not timely there.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.safety_maintenance
    python -m scripts.safety_maintenance --dry-run

**Nothing it does reaches anybody outside the app**, because no provider
exists to reach them with. What it writes is in-app alert records and attempt
rows saying which channels are not configured -- see
``services.safety.providers``.
"""

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import SafetyEvent
from app.services.safety import checks, escalation, monitoring

logger = logging.getLogger("nura.safety_maintenance")


@dataclass(frozen=True)
class Result:
    """What one run did. Counts only -- see the log line below for why."""

    sessions_expired: int
    events_advanced: int
    escalations_started: int
    attempts_retried: int


def open_session() -> Session:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def run(db: Session, now: datetime, *, dry_run: bool = False) -> Result:
    """One pass. Commits per job, so a failure late does not undo work early.

    The order matters once: sessions are expired first, so an event whose
    monitoring has just run out is still processed -- the event's own deadline
    is what decides it, not whether monitoring is still on. A trigger needs
    monitoring (section 22); an *answer* to one that already happened does not.
    """
    expired = monitoring.expire_due(db, now)
    if dry_run:
        db.rollback()
    else:
        db.commit()

    advanced = 0
    escalated = 0
    for event in events_due(db, now):
        before = event.status
        moved = checks.advance(db, event, now)
        if moved.status != before:
            advanced += 1
            if moved.escalation_started_at is not None:
                escalated += 1
        if dry_run:
            db.rollback()
        else:
            db.commit()

    retried = 0
    for attempt in escalation.retryable(db, now):
        escalation.retry(db, attempt, now)
        retried += 1
        if dry_run:
            db.rollback()
        else:
            db.commit()

    return Result(
        sessions_expired=expired,
        events_advanced=advanced,
        escalations_started=escalated,
        attempts_retried=retried,
    )


def events_due(db: Session, now: datetime) -> list[SafetyEvent]:
    """Everything with a deadline in the past. One indexed query."""
    return checks.due_events(db, now)


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
        result = run(db, datetime.now(UTC), dry_run=args.dry_run)

    # Counts only. No profile, no event id, no recipient, no channel detail --
    # section 121 keeps safety logs to required operational data, and a line
    # naming whose escalation ran is not required for anything.
    prefix = "would have " if args.dry_run else ""
    logger.info(
        "safety maintenance: %s%d sessions expired, %s%d events advanced, "
        "%s%d escalations started, %s%d attempts retried",
        prefix,
        result.sessions_expired,
        prefix,
        result.events_advanced,
        prefix,
        result.escalations_started,
        prefix,
        result.attempts_retried,
    )


if __name__ == "__main__":
    main()
