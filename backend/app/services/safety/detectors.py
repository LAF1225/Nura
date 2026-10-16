"""Where a future robot's observations would come in, and why there are none.

PRD 10, sections 53, 54, 57, 66, 71, 92 and 117.

**There is no detector in this system, and this module has none.**
``DETECTORS`` is empty, and that emptiness is load-bearing: it is what makes
``capabilities.robot_detection`` report ``not_connected``, which is what makes
the monitoring screen say "automatic detection by the robot is not connected
yet" instead of implying something is watching (section 66). Deleting the
registry and hard-coding the capability would work until somebody wrote a
detector and forgot the screen.

**What a detector is allowed to produce.** One ``DetectedEvent``, whose
``event_type`` must be one of ``SAFETY_EVENT_TYPES_REQUIRING_MONITORING`` --
the ``possible_*`` set. A detector cannot emit ``manual_sos``: a person asking
for help is not something a sensor concludes. It cannot emit ``test_event``
either; that belongs to the harness.

**Confidence is engineering metadata** (section 54). It is a number a model
produced about its own output, it is not a probability that somebody is ill,
and nothing in this system shows it to a user or lets it change what happens.
It is carried so that a future evaluation can ask "how often was the detector
right?" without re-running anything, and it is dropped before the event is
stored -- ``safety_events`` has no confidence column, because a column is a
thing a screen eventually reads.

**No raw media** (sections 92 and 121). ``metadata`` is a small mapping of
scalars for engineering use. A detector that wanted to attach a frame, a clip
or a waveform has nowhere to put it, and that is deliberate: section 92 says
future detectors should emit events rather than continuous raw media, and the
interface is the place to make that true.

**Nothing here is clinically validated and nothing claims to be** (section
117). There is no fall model, no immobility model, no seizure-like classifier
and no vomiting detector. This file is the socket they would plug into.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import (
    SAFETY_EVENT_TYPES_REQUIRING_MONITORING,
    SAFETY_TRIGGER_SOURCES,
)

logger = logging.getLogger(__name__)

#: What a metadata value may be. Scalars only -- see the module docstring.
MetadataValue = str | int | float | bool


@dataclass(frozen=True)
class DetectedEvent:
    """One observation from a detector (section 54).

    ``observed_at`` rather than "detected_at": the thing with a time is what
    happened, not when a model got round to noticing it.
    """

    event_type: str
    observed_at: datetime
    source: str
    #: Engineering metadata. Never a diagnosis probability, never shown.
    confidence: float | None = None
    metadata: Mapping[str, MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A detector may only observe. Asking for help is a person's act, and
        # `manual_sos` has no detector path into the system.
        assert self.event_type in SAFETY_EVENT_TYPES_REQUIRING_MONITORING, self.event_type
        assert self.source in SAFETY_TRIGGER_SOURCES, self.source
        assert self.confidence is None or 0.0 <= self.confidence <= 1.0


class SafetyEventDetector(ABC):
    """Something that could notice a possible distress event (section 54).

    Three methods, and the middle one is the important one: a detector says
    whether it is *available* right now, and the capability map reads that
    rather than assuming. Section 71 wants a robot going offline to change what
    the UI claims, and this is where that comes from.
    """

    #: Stable, for logs and for the capability map.
    name: str = "detector"

    @abstractmethod
    def available(self) -> bool:
        """Whether this detector could produce anything at the moment."""

    @abstractmethod
    def drain(self) -> Sequence[DetectedEvent]:
        """Everything observed since the last call. May be empty."""


#: Every detector this build has. Empty, and that is the honest state of the
#: project: no robot exists, no sensor has ever produced a reading, and no
#: classifier has been written, let alone validated.
DETECTORS: tuple[SafetyEventDetector, ...] = ()


def available_detectors() -> tuple[SafetyEventDetector, ...]:
    """The detectors that could produce something right now. None of them."""
    return tuple(detector for detector in DETECTORS if detector.available())


def detection_available() -> bool:
    """Whether automatic detection could happen at all (sections 66 and 71)."""
    return bool(available_detectors())
