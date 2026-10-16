"""What this build can actually do, computed rather than assumed.

PRD 10, sections 35, 64, 65, 66, 71, 72 and 106.

Section 64 gives the reason in one line: *this prevents misleading UI*. The
screens are driven by the map this module returns, so a Call control cannot
exist for a call that cannot happen, and a monitoring screen cannot imply a
detector that was never written.

**Every value is derived from the thing itself.** ``push_delivery`` asks the
notification provider, ``audio_calling`` asks PRD 9's call provider,
``robot_detection`` asks the detector registry. None of them is a constant and
none is a setting somebody could flip without wiring something behind it --
which matters, because a capability flag that can be turned on independently of
the capability is how a system ends up telling somebody they are protected when
they are not (section 72).

**``not_configured`` and ``not_connected`` are different facts.** Nobody wired
a provider, versus there is one and it cannot be reached right now. A robot
that has never existed reports ``not_connected``, because section 66's honest
sentence is "not connected yet" -- "not configured" would suggest a setting
somebody could change.

**The three that are ``available`` are the three that work.** A manual SOS
records an event; an in-app safety check prompts the user and takes their
answer; a caregiver with ``safety_alerts`` gets an alert record. Each of those
happens entirely inside this system, which is exactly why they work -- and why
nothing else does.
"""

import logging
from dataclasses import dataclass

from app.models.enums import (
    SAFETY_CAPABILITY_KEYS,
    SAFETY_CAPABILITY_STATES,
    SAFETY_ESCALATION_CHANNELS_AVAILABLE,
)
from app.services.caregivers import calls as audio_calls
from app.services.safety import detectors, providers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Capability:
    """One capability and where it stands."""

    key: str
    state: str

    def __post_init__(self) -> None:
        assert self.key in SAFETY_CAPABILITY_KEYS, self.key
        assert self.state in SAFETY_CAPABILITY_STATES, self.state


def capability_map() -> dict[str, str]:
    """Every capability with its current state (section 106).

    Returns all of ``SAFETY_CAPABILITY_KEYS`` in their fixed order, for the
    reason the caregiver permission map returns all eight categories: a client
    that only sees the keys that happen to be present is a client that silently
    stops asking about one somebody added.
    """
    return {
        # These three are this system talking to itself, which is why they are
        # the three that work.
        "manual_sos": "available",
        "in_app_safety_checks": "available",
        "caregiver_in_app_alerts": (
            "available"
            if "in_app" in SAFETY_ESCALATION_CHANNELS_AVAILABLE
            else "not_configured"
        ),
        # These three need somebody outside this system, and nobody is there.
        "push_delivery": (
            "available" if providers.push_configured() else "not_configured"
        ),
        "sms_delivery": "available" if providers.sms_configured() else "not_configured",
        "audio_calling": (
            "available"
            if audio_calls.calling_available() or providers.emergency_calling_configured()
            else "not_configured"
        ),
        # And this one needs hardware that has never been built.
        "robot_detection": (
            "available" if detectors.detection_available() else "not_connected"
        ),
    }


def capabilities() -> tuple[Capability, ...]:
    """The map as a tuple of validated pairs, in the fixed key order."""
    current = capability_map()
    return tuple(
        Capability(key=key, state=current[key]) for key in SAFETY_CAPABILITY_KEYS
    )


def external_delivery_available() -> bool:
    """Whether Nura could reach anybody outside the app at all.

    False in every deployment today, and it is what section 74's warning is
    driven by: the app shows that warning because this returns False, not
    because somebody wrote the warning into a screen.
    """
    return (
        providers.push_configured()
        or providers.sms_configured()
        or providers.emergency_calling_configured()
        or audio_calls.calling_available()
    )


def available_channels() -> tuple[str, ...]:
    """The channels escalation may actually try (section 34).

    ``in_app`` always; the rest only when a provider exists. The escalation
    policy walks this rather than the full channel list, which is what keeps
    section 34's "only report a channel as available when a real provider
    exists" true of behaviour and not only of the status display.
    """
    channels = ["in_app"]
    if providers.push_configured():
        channels.append("push")
    if providers.sms_configured():
        channels.append("sms_future")
    if providers.emergency_calling_configured():
        channels.append("voice_call_future")
    return tuple(channels)
