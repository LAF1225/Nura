"""The outside services Nura does not have (PRD 12, sections 25-29, 73, 76).

**There is no implementation in this file, and that is the deliverable.**
Section 76 lists fake live weather, fake live news and fake external calendar
sync as things not to build, and section 12 says Nura must not pretend to reach
a service unless a real configured provider exists *and the request actually
succeeds*. The shape that keeps both true is the one PRD 10 used for push and
SMS: a setting that names a provider, a factory that refuses a name it does not
implement, and a capability map derived from whether a provider exists.

So this module answers three questions, all currently with "no":

    weather_configured()           False
    news_configured()              False
    external_calendar_configured() False

and ``build_provider`` raises for any name at all. **Refusing rather than
guessing is the point.** A deployment that sets ``WEATHER_PROVIDER=openweather``
hoping it will work gets a warning in the log and an assistant that still says
weather is not configured in this build -- never one that says it checked.
Nothing fails at startup, because nothing calls ``build_provider``: the
capability map reads the three functions below, and a name nobody implemented
is not a capability. Section 83's checkpoint -- "weather provider configured?"
-- has exactly one honest answer in this build, and this is where it comes
from.

A real provider later means: a class with a method, a branch in
``build_provider``, the credentials in ``core.config`` server-side (section
74), and nothing else -- the capability map, the assistant's tools and the
app's screens all read these three functions and will start saying
``available`` on their own.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: The provider names this build implements, per key. Empty, for every key.
#:
#: Written as a mapping rather than three ``if`` statements so that adding a
#: real provider is a one-line change in one place, and so that a reader can
#: see at a glance that all three are empty.
IMPLEMENTED: dict[str, frozenset[str]] = {
    "weather": frozenset(),
    "news": frozenset(),
    "external_calendar": frozenset(),
}


class UnknownProviderError(RuntimeError):
    """A configured provider name nothing implements.

    Raised at startup rather than at request time: a deployment that thinks it
    has weather should find out immediately, not when somebody asks about the
    weather and gets a sentence that sounds like an answer.
    """


def configured_name(key: str) -> str | None:
    """The provider name set for that key, or None."""
    settings = get_settings()
    return {
        "weather": settings.weather_provider,
        "news": settings.news_provider,
        "external_calendar": settings.external_calendar_provider,
    }[key]


def build_provider(key: str) -> object:
    """Would return a provider. Currently always refuses.

    There is no branch that could succeed, because ``IMPLEMENTED`` is empty for
    every key. The function exists so the refusal is explicit and in one place,
    and so the eventual shape of adding one is obvious.
    """
    name = configured_name(key)
    if name is None:
        raise UnknownProviderError(f"No {key} provider is configured.")
    if name not in IMPLEMENTED[key]:
        raise UnknownProviderError(
            f"{name!r} is not a {key} provider this build implements. "
            "Nura will not pretend to reach one."
        )
    # Unreachable while IMPLEMENTED is empty. Kept so a future provider has an
    # obvious place to be returned from.
    raise UnknownProviderError(f"No {key} provider is wired up.")  # pragma: no cover


def _available(key: str) -> bool:
    """Whether a provider for that key both is named and is implemented.

    Both halves matter. A name nobody implemented is not a capability, and this
    is the function the capability map and the assistant's tools read -- so a
    misconfiguration shows up as ``not_configured`` rather than as a feature
    that sometimes answers.
    """
    name = configured_name(key)
    if name is None:
        return False
    if name not in IMPLEMENTED[key]:
        logger.warning(
            "productivity: %s provider %r is configured but not implemented", key, name
        )
        return False
    return True


def weather_configured() -> bool:
    """False in every deployment (section 26)."""
    return _available("weather")


def news_configured() -> bool:
    """False in every deployment (section 27)."""
    return _available("news")


def external_calendar_configured() -> bool:
    """False in every deployment (section 28)."""
    return _available("external_calendar")


def any_external_configured() -> bool:
    """Whether Nura can reach any outside information service at all.

    What the app's own "nothing external is connected" line is driven by, so
    the sentence is a property of the deployment rather than something
    somebody remembered to write on a screen.
    """
    return weather_configured() or news_configured() or external_calendar_configured()
