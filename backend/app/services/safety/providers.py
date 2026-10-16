"""The boundary to anything that could reach a person, and what is behind it.

PRD 10, sections 34, 35, 36, 38, 39, 109, 110 and 124.

**What is behind it, today, is one channel: an in-app alert record.** No push
provider, no SMS provider, no calling provider. Section 35 says PRD 10 must
preserve PRD 9's honesty about that, and section 39 says never to simulate
success, so the default implementations below return ``not_configured`` with a
stable code -- ``push_not_configured``, ``sms_not_configured``,
``calling_not_configured`` -- and the escalation service records that verbatim.
Nothing in this file pretends.

**Why ``send_in_app_alert`` is on the provider interface at all.** It is the
one channel that works, and it is tempting to treat it as "not really a
delivery". But the question each of these methods answers is the same one --
*is this a real way to reach this person, and what happened when we tried?* --
and an in-app alert's honest answer is "a record now exists for them to find",
which is ``attempted`` and never ``delivered``. The row itself is written by
``services.safety.escalation``, which owns the transaction; the provider says
whether the channel is real and what became of the attempt. Keeping the in-app
channel inside the same interface means the escalation policy has no special
case, and a future deployment that routes in-app alerts through something else
changes one class.

**``delivered`` is reachable and nothing reaches it.** A provider may return it
when it has a confirmation from the thing that did the delivering. No
implementation in this file ever does, because no implementation in this file
ever delivers anything. Section 38's rule is not a comment here; it is the
absence of a code path.

**Retries are bounded** (section 124). ``MAX_RETRIES`` is two, the backoff is
fixed and recorded, and the uniqueness in ``safety_escalation_attempts`` means
a retried worker run updates the attempt it already made rather than making a
second one. Nothing here can spam a contact, and the current providers cannot
reach one at all.

**Configuration** (section 109). ``SAFETY_PUSH_PROVIDER``,
``SAFETY_SMS_PROVIDER`` and ``SAFETY_CALL_PROVIDER``. Unset means
``not_configured``; an unknown name is a misconfiguration and is refused loudly
rather than falling back to something that cannot do what the name promised.
Section 109 also says not to default production to a fake provider, which is
why ``build_notification_provider`` can return exactly one class and the
recording provider used by tests is unreachable from any setting value.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

from app.core.config import Settings, get_settings
from app.models.enums import SAFETY_ESCALATION_ATTEMPT_STATUSES
from app.services.errors import DomainError

logger = logging.getLogger(__name__)

#: How many times one attempt may be retried before it is left as it is
#: (section 124). Small on purpose: an emergency that needed a third try needed
#: a different channel.
MAX_RETRIES = 2

#: How long to wait between retries, in seconds. Fixed and doubling, recorded
#: on the attempt as ``retry_count`` so the next run can work out whether it is
#: due without holding anything in memory.
RETRY_BACKOFF_SECONDS = (30, 120)


class SafetyProviderConfigurationError(DomainError):
    """A provider name nobody implemented.

    503, the same as every other "this deployment is not set up" answer. It is
    a deployment fact, not the caller's mistake.
    """

    status_code = 503
    code = "safety_provider_not_configured"


@dataclass(frozen=True)
class AlertRecipient:
    """Who an attempt is aimed at, and nothing more about them.

    Deliberately thin. A provider is given a label to put in its own logs, an
    account id when the recipient uses Nura, and a phone number *only* when the
    channel needs one. Nothing medical, no profile id, no event detail beyond
    the summary sentence the escalation service renders from
    ``services.safety.wording`` -- section 85 keeps unrelated health data out
    of a caregiver alert, and the way to be sure is that it never gets this far.
    """

    label: str
    account_id: uuid.UUID | None = None
    phone: str | None = None


@dataclass(frozen=True)
class DeliveryOutcome:
    """What happened when one channel was tried.

    ``status`` is one of ``SAFETY_ESCALATION_ATTEMPT_STATUSES`` and is written
    straight onto the attempt row, so a provider that wanted to claim a
    delivery would have to say the word -- which is exactly the decision
    section 38 wants visible.
    """

    status: str
    provider: str | None = None
    failure_code: str | None = None
    #: Set only when a provider confirms. Nothing in this build sets it.
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        assert self.status in SAFETY_ESCALATION_ATTEMPT_STATUSES, self.status


class SafetyNotificationProvider(ABC):
    """Somewhere a safety alert can be sent (section 36).

    Three methods, one per channel, and no vendor concept in any signature: a
    provider that needs a device token, a topic or a sender id builds one from
    the recipient it is given and keeps it to itself. The same discipline the
    audio-call provider follows in PRD 9, for the same reason -- the thing that
    goes wrong when a vendor leaks into the interface is that swapping vendors
    becomes a change to the escalation policy.
    """

    #: Recorded on the attempt, so a row can say which provider handled it.
    name: str = "unconfigured"

    @abstractmethod
    def send_in_app_alert(
        self, *, recipient: AlertRecipient, summary: str
    ) -> DeliveryOutcome:
        """Reports what became of an in-app alert for this recipient."""

    @abstractmethod
    def send_push_alert(
        self, *, recipient: AlertRecipient, title: str, body: str
    ) -> DeliveryOutcome:
        """Sends a push notification. The body is deliberately empty of detail."""

    @abstractmethod
    def send_sms_alert(self, *, recipient: AlertRecipient, body: str) -> DeliveryOutcome:
        """Sends a text message to a phone number."""


class EmergencyCallProvider(ABC):
    """Somewhere an emergency call can be placed (section 36).

    Separate from PRD 9's ``AudioCallProvider``, which is a two-way call
    between a primary user and a caregiver who both have the app open. This one
    rings a phone number that may belong to somebody with no Nura account at
    all. Both are unconfigured; conflating them would mean configuring one
    silently claimed the other.
    """

    name: str = "unconfigured"

    @abstractmethod
    def start_emergency_call(
        self, *, recipient: AlertRecipient, event_id: uuid.UUID
    ) -> DeliveryOutcome:
        """Places a call. Returns ``attempted`` at best, never ``delivered``."""

    @abstractmethod
    def get_call_status(self, *, call_id: str) -> str:
        """Where that call is now."""


class InAppOnlyNotificationProvider(SafetyNotificationProvider):
    """What every deployment has: an in-app record, and nothing else.

    The in-app alert is ``attempted``, which is the strongest true statement
    available -- the record exists and the caregiver may never open it (section
    38). Push and SMS are ``not_configured``, which is a first-class outcome
    rather than a failure: a build with no push provider has not failed to send
    a push.
    """

    name = "in_app"

    def send_in_app_alert(
        self, *, recipient: AlertRecipient, summary: str
    ) -> DeliveryOutcome:
        # Not `delivered`. The row exists; nobody has read it.
        return DeliveryOutcome(status="attempted", provider=self.name)

    def send_push_alert(
        self, *, recipient: AlertRecipient, title: str, body: str
    ) -> DeliveryOutcome:
        return DeliveryOutcome(
            status="not_configured", failure_code="push_not_configured"
        )

    def send_sms_alert(self, *, recipient: AlertRecipient, body: str) -> DeliveryOutcome:
        return DeliveryOutcome(status="not_configured", failure_code="sms_not_configured")


class UnconfiguredEmergencyCallProvider(EmergencyCallProvider):
    """No calling provider, said the same way PRD 9 says it.

    The code is deliberately ``calling_not_configured``, matching
    ``services.caregivers.calls`` exactly: one code for "Nura cannot ring
    anybody", whichever feature asked.
    """

    name = "unconfigured"

    def start_emergency_call(
        self, *, recipient: AlertRecipient, event_id: uuid.UUID
    ) -> DeliveryOutcome:
        return DeliveryOutcome(
            status="not_configured", failure_code="calling_not_configured"
        )

    def get_call_status(self, *, call_id: str) -> str:
        raise SafetyProviderConfigurationError("Calling is not set up on this server.")


@dataclass
class RecordingNotificationProvider(SafetyNotificationProvider):
    """**Tests only.** Records what it was asked to send and claims nothing.

    Section 110 allows a recording provider in automated tests and requires
    that it never be represented as real production delivery. Two things make
    that true rather than promised:

    - ``build_notification_provider`` cannot return it. There is no setting
      value that reaches this class; it is installed only by
      ``set_notification_provider``, which tests call and nothing else does.
    - It returns ``attempted``, not ``delivered``, unless a test explicitly
      sets ``confirm``. A test that wants to exercise the confirmed path has to
      say so, which is the point at which somebody reviewing it would notice.
    """

    name: str = "recording"
    confirm: bool = False
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def _record(
        self, channel: str, recipient: AlertRecipient, body: str
    ) -> DeliveryOutcome:
        self.sent.append((channel, recipient.label, body))
        if self.confirm:
            return DeliveryOutcome(status="delivered", provider=self.name)
        return DeliveryOutcome(status="attempted", provider=self.name)

    def send_in_app_alert(
        self, *, recipient: AlertRecipient, summary: str
    ) -> DeliveryOutcome:
        return self._record("in_app", recipient, summary)

    def send_push_alert(
        self, *, recipient: AlertRecipient, title: str, body: str
    ) -> DeliveryOutcome:
        return self._record("push", recipient, body)

    def send_sms_alert(self, *, recipient: AlertRecipient, body: str) -> DeliveryOutcome:
        return self._record("sms_future", recipient, body)


def build_notification_provider(settings: Settings) -> SafetyNotificationProvider:
    """The notification provider this deployment uses.

    One branch, and it is the honest one. Both ``SAFETY_PUSH_PROVIDER`` and
    ``SAFETY_SMS_PROVIDER`` are unset everywhere today; a name nobody
    implemented is refused rather than quietly ignored, because a deployment
    that set ``SAFETY_SMS_PROVIDER=twilio`` and got silence would believe it had
    SMS.
    """
    for value in (settings.safety_push_provider, settings.safety_sms_provider):
        if value not in (None, "", "none"):
            raise SafetyProviderConfigurationError(
                f"Unknown safety notification provider: {value}"
            )
    return InAppOnlyNotificationProvider()


def build_call_provider(settings: Settings) -> EmergencyCallProvider:
    """The emergency-call provider this deployment uses. There is not one."""
    name = settings.safety_call_provider
    if name in (None, "", "none"):
        return UnconfiguredEmergencyCallProvider()
    raise SafetyProviderConfigurationError(f"Unknown emergency call provider: {name}")


_notification_override: SafetyNotificationProvider | None = None
_call_override: EmergencyCallProvider | None = None


def set_notification_provider(provider: SafetyNotificationProvider | None) -> None:
    """Replaces the notification provider. Tests only."""
    global _notification_override
    _notification_override = provider
    get_notification_provider.cache_clear()


def set_call_provider(provider: EmergencyCallProvider | None) -> None:
    """Replaces the call provider. Tests only."""
    global _call_override
    _call_override = provider
    get_call_provider.cache_clear()


@lru_cache
def get_notification_provider() -> SafetyNotificationProvider:
    if _notification_override is not None:
        return _notification_override
    return build_notification_provider(get_settings())


@lru_cache
def get_call_provider() -> EmergencyCallProvider:
    if _call_override is not None:
        return _call_override
    return build_call_provider(get_settings())


def push_configured() -> bool:
    """Whether a push provider exists. It does not.

    Asked by the capability map rather than assumed, so the day somebody wires
    one up the UI stops saying push is unavailable without anybody editing a
    screen.
    """
    return not isinstance(get_notification_provider(), InAppOnlyNotificationProvider)


def sms_configured() -> bool:
    """Whether an SMS provider exists. It does not."""
    return not isinstance(get_notification_provider(), InAppOnlyNotificationProvider)


def emergency_calling_configured() -> bool:
    """Whether an emergency-call provider exists. It does not."""
    return not isinstance(get_call_provider(), UnconfiguredEmergencyCallProvider)


def retry_due_after(retry_count: int) -> int | None:
    """Seconds to wait before retry number ``retry_count`` + 1, or None.

    None means no more retries: section 124 wants them bounded, and the bound
    is here rather than in the worker so there is one answer.
    """
    if retry_count >= MAX_RETRIES:
        return None
    return RETRY_BACKOFF_SECONDS[min(retry_count, len(RETRY_BACKOFF_SECONDS) - 1)]
