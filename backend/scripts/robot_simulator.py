"""A robot you can drive from a terminal.

PRD 11, sections 62, 63, 64, 95, 129, 132 and 140.

Section 62 asks for a first-class simulator and names three possible shapes: a
developer screen, a CLI, or a test harness. This is the CLI, and it shares its
core with the test harness -- ``app.services.robot.simulator`` -- so the thing
a developer drives by hand is the thing the tests drive automatically.

**It is a device, not a mock.** Every command below goes through the same
services the HTTP endpoints call: report capabilities, reconcile, fetch the
next presentation, acknowledge it. Nothing underneath is stubbed.

**It renders.** ``poll`` prints the lines a person would read off the screen,
which is what makes "did the private medication preview actually hide the
name?" a question you can answer by looking.

Usage, from the ``backend`` directory with the virtualenv active::

    python -m scripts.robot_simulator status
    python -m scripts.robot_simulator capabilities --preset display
    python -m scripts.robot_simulator poll --times 5
    python -m scripts.robot_simulator poll --render failed
    python -m scripts.robot_simulator queue
    python -m scripts.robot_simulator plan

``plan`` walks PRD 11 section 132's manual test plan against the dev database
and prints each step, which is the fastest way to see the whole experience
without hardware.

**Writes to the development database.** Unlike the verification scripts in
earlier PRDs, this one is meant to leave state behind -- that is the point of
driving a robot by hand. Use ``scripts/seed_dev.py --robot`` to set one up
first, and ``--dry-run`` here to roll everything back on exit.

**This is not in the app and never will be** (section 62: no simulator
controls in production UI). ``tests/test_robot_simulator.py`` asserts that
nothing under ``app/api`` imports the simulator, so there is no route that can
drive a pretend robot.

**And it is not hardware proof** (section 135). What this exercises is the
queue, the privacy filter, the preemption rule, the expiry comparison and the
acknowledgement machine. No panel, speaker or microphone is involved, and no
physical acknowledgement has ever reached this backend.
"""

import argparse
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.models import Device, Profile
from app.services import devices as device_service
from app.services.robot import capabilities as capability_service
from app.services.robot import modes, preferences, presenter, queue, wording
from app.services.robot import simulator as sim

logger = logging.getLogger("nura.robot_simulator")

#: Section 64's capability sets, by name.
PRESETS = {
    "display": sim.DISPLAY_ONLY,
    "unverified": sim.UNVERIFIED_DISPLAY,
    "speaker": sim.WITH_SPEAKER,
    "buttons": sim.WITH_BUTTONS,
    "headless": sim.HEADLESS,
}


def open_session() -> Session:
    engine = create_engine(get_settings().database_url)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def pick_device(db: Session, hardware_id: str | None) -> Device:
    """The robot to drive. The only one, unless there are several."""
    statement = select(Device).where(Device.claimed_by_account_id.is_not(None))
    if hardware_id is not None:
        statement = statement.where(Device.hardware_id == hardware_id)
    devices = list(db.execute(statement.order_by(Device.created_at)).scalars().all())
    if not devices:
        raise SystemExit(
            "No claimed robot in this database. Run:\n"
            "    python -m scripts.seed_dev --robot online"
        )
    if len(devices) > 1 and hardware_id is None:
        names = ", ".join(device.hardware_id for device in devices)
        raise SystemExit(f"Several robots here; pass --hardware-id. One of: {names}")
    return devices[0]


def line(text: str = "") -> None:
    print(text)


def show_screen(screen: sim.Screen | None) -> None:
    if screen is None:
        line("  (nothing to show)")
        return
    line(f"  mode: {screen.mode}   layout: {screen.layout}")
    for text in screen.lines:
        line(f"  | {text}")
    if screen.serious:
        line("  (serious: no face, high contrast)")
    if screen.spoken:
        line("  (would be read aloud)")


# --- commands ----------------------------------------------------------------


def command_status(
    db: Session, device: Device, now: datetime, args: argparse.Namespace
) -> None:
    mode = modes.resolve(db, device, now)
    row, resolved = preferences.resolved_for(db, device, now)

    line(f"robot {device.hardware_id} ({device.display_name})")
    line(f"  connection: {device_service.connection_status(device, now)}")
    line(f"  mode:       {mode.mode}  ({wording.MODE_LABELS[mode.mode]})")
    line(f"  face:       {mode.face or 'none -- showing information'}")
    line(f"  queue:      {queue.queue_depth(db, device.id)} open")
    line()
    line("  capabilities (section 10):")
    for view in capability_service.views(db, device, now):
        stale = "  [stale]" if view.stale else ""
        line(f"    {wording.capability_sentence(key=view.key, state=view.state)}{stale}")
    line()
    line("  preferences (section 48):")
    line(f"    brightness {resolved.brightness}  volume {resolved.volume}")
    following = "  (following the accessibility setting)"
    line(
        f"    reduced motion {resolved.reduced_motion}"
        + (following if row.reduced_motion is None else "")
    )
    line(f"    medication preview: {resolved.medication_privacy_level}")
    line(
        f"    read aloud: medications {resolved.read_medications_aloud}, "
        f"messages {resolved.read_messages_aloud}, "
        f"assistant {resolved.read_assistant_aloud}"
    )
    line()
    line(f"  {wording.NO_HARDWARE_NOTE}")


def command_capabilities(
    db: Session, device: Device, now: datetime, args: argparse.Namespace
) -> None:
    states = PRESETS[args.preset]
    robot = sim.SimulatedRobot(db=db, device=device, capability_states=dict(states))
    robot.report_capabilities(now)
    db.commit()
    line(f"reported the '{args.preset}' set (section 61):")
    for view in capability_service.views(db, device, now):
        line(f"  {wording.capability_sentence(key=view.key, state=view.state)}")


def command_poll(
    db: Session, device: Device, now: datetime, args: argparse.Namespace
) -> None:
    robot = sim.SimulatedRobot(
        db=db,
        device=device,
        render_outcome=args.render,
        capability_states=dict(capability_service.capability_map(db, device, now)),
    )
    if args.offline:
        robot.go_offline()

    for index in range(args.times):
        line(f"poll {index + 1}:")
        screen = robot.poll(now)
        show_screen(screen)
        db.commit()
        if screen is None:
            break


def command_queue(
    db: Session, device: Device, now: datetime, args: argparse.Namespace
) -> None:
    presenter.refresh(db, device, now)
    db.commit()
    rows = queue.history(db, device.id, limit=20)
    if not rows:
        line("nothing has been queued for this robot")
        return
    line("most recent first (section 96):")
    for row in rows:
        title, summary = wording.summary_of(row.payload)
        rendered = wording.history_line(
            presentation_type=row.presentation_type,
            status=row.status,
            failure_code=row.failure_code,
            cancel_reason=row.cancel_reason,
        )
        line(f"  {rendered}")
        if summary:
            line(f"      {title or ''} / {summary}")


def command_plan(
    db: Session, device: Device, now: datetime, args: argparse.Namespace
) -> None:
    """Section 132's manual plan, printed step by step."""
    profile = db.get(Profile, device.owner_profile_id)
    line("=== section 132: the whole plan, with no hardware ===")
    whose = profile.preferred_name if profile is not None else "nobody"
    line(f"robot {device.hardware_id}, set up for {whose}")

    line()
    line("1. report display available")
    robot = sim.SimulatedRobot(db=db, device=device)
    robot.connect(now)
    db.commit()
    states = capability_service.capability_map(db, device, now)
    line(f"   display: {states['display']}   text: {states['display_text']}")

    line()
    line("2. queue the idle face, and draw it")
    show_screen(robot.poll(now))
    db.commit()

    line()
    line("3. whatever is true right now -- reminders, messages, safety")
    for screen in robot.drain(now):
        show_screen(screen)
        line("   ---")
    db.commit()

    line()
    line("4. set the private medication preview")
    row = preferences.get_or_create(db, device, now)
    preferences.update(db, row, {"medication_privacy_level": "private"}, now)
    db.commit()
    line(f"   medication preview: {row.medication_privacy_level}")

    line()
    line("5. set reduced motion, and see it in the envelope")
    preferences.update(db, row, {"reduced_motion": True}, now)
    db.commit()
    presenter.refresh(db, device, now)
    db.commit()
    pending = queue.next_for_device(db, device, now)
    if pending is not None:
        envelope = queue.envelope_for(db, device, pending, now)
        settings: Any = envelope["settings"]
        line(
            f"   reduced_motion={settings['reduced_motion']} "
            f"face_animation={settings['face_animation']}"
        )
        db.commit()
    else:
        line("   (nothing queued to carry the settings)")

    line()
    line("6. mark the display unsupported")
    robot.use(dict(sim.HEADLESS), now)
    db.commit()
    states = capability_service.capability_map(db, device, now)
    line(f"   display: {states['display']}   audio: {states['speaker']}")
    line("   a card queued now is recorded as not_supported, not dropped")

    line()
    line("7. simulate a render failure")
    robot.use(dict(sim.DISPLAY_ONLY), now)
    robot.render_outcome = "failed"
    db.commit()
    presenter.refresh(db, device, now)
    db.commit()
    robot.poll(now)
    db.commit()
    line("   see `queue` for the failed row")

    line()
    line(f"{wording.NO_HARDWARE_NOTE}")
    line("Simulator proof is not hardware proof (section 135).")


COMMANDS: dict[str, Any] = {
    "status": command_status,
    "capabilities": command_capabilities,
    "poll": command_poll,
    "queue": command_queue,
    "plan": command_plan,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--hardware-id", help="Which robot, if there are several.")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESETS),
        default="display",
        help="Which capability set to report (section 64).",
    )
    parser.add_argument(
        "--render",
        choices=("render_started", "render_completed", "failed", "unsupported"),
        default="render_started",
        help="What the robot reports after drawing (section 64).",
    )
    parser.add_argument("--times", type=int, default=1, help="How many polls.")
    parser.add_argument(
        "--offline", action="store_true", help="Pretend the robot cannot reach us."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Roll everything back on exit, leaving the database untouched.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    now = datetime.now(UTC)
    db = open_session()
    try:
        device = pick_device(db, args.hardware_id)
        COMMANDS[args.command](db, device, now, args)
        if args.dry_run:
            db.rollback()
            line()
            line("rolled back -- the database is unchanged.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
