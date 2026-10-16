"""Audio calling: the boundary, and an honest admission that nothing is behind it.

PRD 9, sections 38, 39, 40, 41, 76 and 92.

**No call has ever been placed, and nothing here simulates one.** Section 38 is
unusually direct about this: prioritise the abstraction, the permission flow, the
initiation UI and the state model, implement real audio only if it is reliable
now, and otherwise *document it as partially implemented and do not simulate
successful calls*. There is no WebRTC stack in this project, no signalling
server, no TURN credentials and no vendor account. So:

- the provider interface is real and complete,
- the state vocabulary is real,
- authorization is real -- a call needs ``communication`` on an active
  relationship, checked the same way a message does,
- and the only implementation raises ``CallingNotConfiguredError``.

That error is what the app shows. It does not ring, it does not say "connecting",
and it does not report ``active`` for a call that is not happening. A caller who
presses Call is told plainly that calling is not set up yet.

**Why an interface at all, then?** Section 39 says not to hard-wire the app to
one vendor, and the shape of the problem is already clear: a call is started,
accepted, declined or ended, and something reports what state it is in. Writing
that down now is what stops the eventual provider from being wired through six
screens -- the same reason PRD 8 put the model behind one method. It is five
methods wide and mentions no vendor concept at all: no room id, no SDP, no ICE
server, no token format.

**Security, for when there is something to secure** (section 76). The interface
hands back a ``CallSession`` holding short-lived, opaque credentials, and
``AudioCallProvider`` is the only thing that ever sees them. Nothing in it
returns a long-lived secret, nothing writes one to the database -- there is no
table for calls, because nothing has ever happened that would need recording --
and the app is given a session it cannot reuse. A deployment that wires up a
vendor must keep its API key server-side, exactly as the model provider does.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.models.enums import AUDIO_CALL_STATES
from app.services.errors import DomainError

logger = logging.getLogger(__name__)


class CallError(DomainError):
    """A call could not be started or changed."""

    code = "call_error"


class CallingNotConfiguredError(CallError):
    """No audio-calling provider is configured for this deployment.

    503 rather than 501 or 400: it is a deployment fact, not the caller's
    mistake, and it is the same answer the API gives when authentication is
    unconfigured.
    """

    status_code = 503
    code = "calling_not_configured"


class CallNotFoundError(CallError):
    status_code = 404
    code = "call_not_found"


@dataclass(frozen=True)
class CallSession:
    """A call in progress, as the app needs to see it.

    ``credential`` is whatever the provider needs the client to present, opaque
    to everything above this module and short-lived by contract (section 76).
    It is never stored and never logged.
    """

    call_id: str
    state: str
    #: Opaque, short-lived, single-call. Never written to a database.
    credential: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        assert self.state in AUDIO_CALL_STATES, self.state


class AudioCallProvider(ABC):
    """Somewhere a call can happen (PRD 9, section 39).

    Five methods, which is section 39's own list. Deliberately no vendor
    concepts: a provider that needs a room, a channel or an SDP offer builds one
    from the relationship id it is given and keeps it to itself.
    """

    @abstractmethod
    def start(
        self, *, relationship_id: uuid.UUID, caller_account_id: uuid.UUID
    ) -> CallSession:
        """Places a call and returns it in ``ringing`` or ``connecting``."""

    @abstractmethod
    def accept(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        """Answers a ringing call."""

    @abstractmethod
    def decline(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        """Refuses a ringing call. Ends in ``ended``."""

    @abstractmethod
    def end(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        """Hangs up."""

    @abstractmethod
    def state(self, *, call_id: str) -> CallSession:
        """Where the call is now."""


class UnconfiguredCallProvider(AudioCallProvider):
    """What every deployment has today: nothing, said clearly.

    Every method raises. That is the point -- section 38 forbids simulating a
    successful call, and a stub that returned ``active`` would do exactly that.
    The route turns this into a 503 with the code ``calling_not_configured``, and
    the app shows a sentence saying calling is not available yet instead of a
    call screen.
    """

    def _refuse(self) -> CallSession:
        logger.info("calls: refused -- no provider is configured")
        raise CallingNotConfiguredError("Audio calling is not set up on this server yet.")

    def start(
        self, *, relationship_id: uuid.UUID, caller_account_id: uuid.UUID
    ) -> CallSession:
        return self._refuse()

    def accept(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        return self._refuse()

    def decline(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        return self._refuse()

    def end(self, *, call_id: str, account_id: uuid.UUID) -> CallSession:
        return self._refuse()

    def state(self, *, call_id: str) -> CallSession:
        return self._refuse()


def build_provider(settings: Settings) -> AudioCallProvider:
    """The provider this deployment uses.

    One branch, and it is the honest one. A future WebRTC or vendor
    implementation is a second class and a second branch here; nothing above this
    function changes.
    """
    name = settings.audio_call_provider
    if name in (None, "", "none"):
        return UnconfiguredCallProvider()
    # An unknown name is a misconfiguration, and refusing loudly is better than
    # falling back to something that cannot do what the name promised.
    raise CallingNotConfiguredError(f"Unknown audio call provider: {name}")


_override: AudioCallProvider | None = None


def set_provider(provider: AudioCallProvider | None) -> None:
    """Replaces the provider. Tests only, the same way the model provider is."""
    global _override
    _override = provider
    get_provider.cache_clear()


@lru_cache
def get_provider() -> AudioCallProvider:
    if _override is not None:
        return _override
    return build_provider(get_settings())


def calling_available() -> bool:
    """Whether any provider is configured.

    The app asks so it can decide whether to show a Call control at all, rather
    than showing one that always fails. The server still refuses the route --
    section 62's rule that the server stays authoritative applies to this as
    much as to a permission.
    """
    return not isinstance(get_provider(), UnconfiguredCallProvider)
