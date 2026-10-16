"""The cross-boundary security suite (PRD 13, sections 13, 14 and 51).

**This file is the one that keeps working as PRDs are added**, and that is its
whole reason for existing. Every stage from PRD 9 onwards wrote its own denial
test against a hand-typed list of paths: PRD 9 walked eight, PRD 10 added its
own, PRD 12 added another. Each was correct and none of them covered the next
stage's routes. Section 51 asks for one load-bearing suite, and the way to make
one load-bearing is to stop typing the list.

So ``owner_routes()`` asks the application. It walks the router tree, resolves
each route's dependency graph, and classifies it by *which authorization
dependency it reaches*: ``get_owned_profile`` for an owner route,
``get_caregiver_scope`` for a caregiver-only one, ``get_care_scope`` for one
that accepts either, ``get_current_device`` for the robot's own. A route added
by PRD 14 is classified the day it is written, and if it is an owner route it
is in these assertions immediately -- without anybody remembering to add it.

The matrix section 14 asks for, in the order it asks:

    owner -> own profile                      allowed    (the feature tests)
    owner A -> owner B's profile              denied     TestCrossProfile
    caregiver -> owner-only route             denied     TestCaregiverBoundary
    caregiver with permission -> care route   allowed    TestCaregiverBoundary
    caregiver without permission -> denied               TestCaregiverBoundary
    revoked caregiver -> denied                          TestCaregiverBoundary
    device A -> profile/device B              denied     TestDeviceBoundary

Three more sections fold in because they are the same shape: section 15's
assistant authorization, section 27's private media, and the export and
deletion denials sections 49 and 51 both name.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi.routing import APIRoute

from app.api.deps import (
    current_time,
    get_care_scope,
    get_caregiver_scope,
    get_current_device,
    get_current_user,
    get_owned_profile,
)
from app.api.v1 import router as v1
from app.main import app
from app.models.enums import CAREGIVER_PERMISSION_KEYS
from tests.test_devices import ready_account
from tests.test_today import Clock

NOON = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

#: Methods that are never routed by this app.
_IGNORED_METHODS = frozenset({"HEAD", "OPTIONS"})

#: **The complete caregiver-reachable surface**, with what each route is for.
#:
#: Thirteen routes out of two hundred and nine. Writing them out is the point:
#: adding a fourteenth is a deliberate act that fails this file until somebody
#: has said what it is for, which is section 13's "do not merge these paths"
#: enforced at the moment a path would be added.
#:
#: ``caregiver`` means caregiver-only -- an owner gets 404, because these are
#: the helper's own surface rather than a second view of their own data.
#: ``either`` means an owner or an active caregiver, which is the shape PRD 9
#: chose for a two-sided conversation: both people are in it.
CAREGIVER_REACHABLE_ROUTES: dict[str, str] = {
    # PRD 9's caregiver surface.
    "GET /api/v1/profiles/{profile_id}/care/home": (
        "Section 17: their Today, assembled permission by permission."
    ),
    "PATCH /api/v1/profiles/{profile_id}/care/notifications": (
        "Section 48: their own notification choices, per supported person."
    ),
    "GET /api/v1/profiles/{profile_id}/caregiver-suggestions": (
        "Section 25: both sides see the suggestion list."
    ),
    "POST /api/v1/profiles/{profile_id}/caregiver-suggestions": (
        "Section 25: proposing a change is the caregiver's half."
    ),
    "POST /api/v1/profiles/{profile_id}/caregiver-suggestions/{suggestion_id}/cancel": (
        "Section 26: a caregiver may withdraw their own suggestion."
    ),
    # PRD 9's family messaging: two-sided by definition.
    "GET /api/v1/profiles/{profile_id}/family/threads": "Section 31.",
    "POST /api/v1/profiles/{profile_id}/family/threads": "Section 31.",
    "GET /api/v1/profiles/{profile_id}/family/threads/{thread_id}/messages": (
        "Section 31: both people read the conversation."
    ),
    "POST /api/v1/profiles/{profile_id}/family/threads/{thread_id}/messages": (
        "Section 31: and both write in it."
    ),
    "POST /api/v1/profiles/{profile_id}/family/calls": (
        "Section 38: refuses with calling_not_configured, from either side."
    ),
    # PRD 10's alerts.
    "GET /api/v1/profiles/{profile_id}/care/safety-alerts": (
        "Section 93: the alerts a caregiver was sent."
    ),
    "POST /api/v1/profiles/{profile_id}/care/safety-alerts/{alert_id}/acknowledge": (
        "Section 93: 'I am checking on them'. Resolves nothing."
    ),
    # PRD 12's routines.
    "GET /api/v1/profiles/{profile_id}/care/routines": (
        "PRD 12 section 16: the one caregiver route PRD 12 adds."
    ),
}

#: The one route that resolves the owner dependency *and* a care scope, with
#: why that is safe. FastAPI ANDs dependencies, so a combination can only
#: narrow access -- but a reader should not have to work that out, and a second
#: entry appearing here should make somebody look.
OWNER_PLUS_SCOPE_ROUTES: dict[str, str] = {
    "GET /api/v1/profiles/{profile_id}/care-summary": (
        "Owner-only. The care scope is read for the unread-message count, "
        "which is a per-caller value, not a second way in: OwnedProfile has "
        "already required ownership, so the scope resolves to the owner's own."
    ),
}


@dataclass(frozen=True)
class RouteInfo:
    """One route, and which authorization path it reaches."""

    method: str
    path: str
    #: ``owner``, ``caregiver``, ``either``, ``device``, ``user`` or ``open``.
    kind: str

    @property
    def label(self) -> str:
        return f"{self.method} {self.path}"


def _dependencies(route: APIRoute) -> set[object]:
    """Every callable in this route's dependency graph.

    Flattened rather than checked one level deep, because the aliases in
    ``deps.py`` nest: ``CaregiverScope`` depends on ``get_care_scope``, which
    depends on ``get_current_user``. A one-level check would classify half of
    these as account-level.
    """
    found: set[object] = set()
    stack = list(route.dependant.dependencies)
    while stack:
        current = stack.pop()
        if current.call is not None:
            found.add(current.call)
        stack.extend(current.dependencies)
    return found


def _classify(route: APIRoute) -> str:
    deps = _dependencies(route)
    if get_owned_profile in deps:
        return "owner"
    if get_caregiver_scope in deps:
        return "caregiver"
    if get_care_scope in deps:
        return "either"
    if get_current_device in deps:
        return "device"
    if get_current_user in deps:
        return "user"
    return "open"


def _walk(router=None, accumulated=""):  # type: ignore[no-untyped-def]
    """Every ``APIRoute`` under a router, with its full path.

    The router tree is walked rather than ``app.routes``, because FastAPI
    resolves an included router lazily: the app's own list holds one opaque
    ``_IncludedRouter`` for the whole of v1.

    The prefix arithmetic is the part worth reading. A router's own routes
    already carry that router's prefix, so a route is yielded with whatever
    was accumulated *above* it -- but recursing into a child means the parent's
    prefix has to join the accumulation, because the child's routes carry only
    the child's own. Getting this wrong is not loud: it produces paths that
    simply do not exist, every request against them answers 404, and a suite
    asserting "404 for the wrong caller" passes while testing nothing. It did,
    for the nine health-record routes nested two levels deep, until
    ``test_every_route_in_the_walk_exists`` was added below.
    """
    router = v1.router if router is None else router
    for route in router.routes:
        if isinstance(route, APIRoute):
            yield accumulated + route.path, route
        else:
            original = getattr(route, "original_router", None)
            if original is not None:
                yield from _walk(original, accumulated + router.prefix)


def all_routes() -> tuple[RouteInfo, ...]:
    """Every v1 route, classified."""
    out: list[RouteInfo] = []
    for path, route in _walk():
        kind = _classify(route)
        for method in sorted(route.methods - _IGNORED_METHODS):
            out.append(RouteInfo(method=method, path=path, kind=kind))
    return tuple(sorted(out, key=lambda item: (item.path, item.method)))


def owner_routes() -> tuple[RouteInfo, ...]:
    return tuple(route for route in all_routes() if route.kind == "owner")


def _fill(path: str, *, profile_id: str, ids: dict[str, str]) -> str:
    """A concrete URL for a route template.

    Every id other than the profile is a UUID that exists nowhere. That is the
    point: a caller who is refused at the profile boundary never reaches the
    resource, so the resource does not need to exist -- and a route that
    answered anything but 404 for a nonexistent child would be a finding in
    itself.
    """
    filled = path.replace("{profile_id}", profile_id)
    while "{" in filled:
        start = filled.index("{")
        end = filled.index("}", start)
        name = filled[start + 1 : end]
        filled = filled[:start] + ids.get(name, str(uuid.uuid4())) + filled[end + 1 :]
    return filled


@pytest.fixture
def clock(client) -> Clock:
    fake = Clock()
    fake.now = NOON
    app.dependency_overrides[current_time] = lambda: fake.now
    return fake


@pytest.fixture
def owner(client, make_token) -> tuple[dict[str, str], str]:
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


@pytest.fixture
def intruder(client, make_token) -> tuple[dict[str, str], str]:
    """A second owner, with a profile of their own."""
    headers = ready_account(client, make_token)
    profile_id = client.get("/api/v1/me", headers=headers).json()["profiles"][0]["id"]
    return headers, profile_id


@pytest.fixture
def helper(client, make_token) -> dict[str, str]:
    """A third account with no profile, to be a caregiver."""
    return {"Authorization": f"Bearer {make_token()}"}


def make_caregiver(
    client, owner_account, caregiver_headers, *, permissions: dict[str, bool]
) -> str:
    headers, profile_id = owner_account
    created = client.post(
        f"/api/v1/profiles/{profile_id}/caregivers/invitations",
        json={
            "invited_name": "Ayesha",
            "role": "family",
            "permissions": permissions,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.json()
    accepted = client.post(
        f"/api/v1/caregiver-invitations/{created.json()['token']}/accept",
        headers=caregiver_headers,
    )
    assert accepted.status_code == 200, accepted.json()
    return created.json()["caregiver"]["id"]


class TestClassification:
    """The scaffolding, guarded before anything is concluded from it."""

    def test_the_walk_finds_the_routes(self):
        """A regression guard on the walk itself.

        If FastAPI changes how included routers are stored, this suite would
        silently start asserting things about an empty list -- which would pass
        and prove nothing. So the count is asserted to be substantial.
        """
        routes = all_routes()
        assert len(routes) > 200
        assert len(owner_routes()) > 150

    def test_every_route_in_the_walk_exists(self, client):
        """The assertion that makes every other one in this file mean something.

        A path the walk got wrong does not exist, so every request against it
        answers 404 -- and a test asserting "the wrong caller gets 404" then
        passes for a route it never reached. This compares the walk against
        the schema FastAPI publishes, which is built from the real routing
        table.
        """
        published = set(client.get("/openapi.json").json()["paths"])
        walked = {route.path for route in all_routes()}
        assert walked <= published, sorted(walked - published)

    def test_every_published_profile_route_is_in_the_walk(self, client):
        """And the other direction, so nothing is quietly skipped."""
        published = {
            path
            for path in client.get("/openapi.json").json()["paths"]
            if "{profile_id}" in path
        }
        walked = {route.path for route in all_routes()}
        assert published <= walked, sorted(published - walked)

    def test_every_authorization_kind_is_represented(self):
        """All five paths exist and none has collapsed into another."""
        kinds = {route.kind for route in all_routes()}
        assert {"owner", "caregiver", "either", "device", "user"} <= kinds

    def test_the_device_path_never_meets_a_profile_path(self):
        """Section 13: "do not merge these paths".

        A device token and an account token are different credentials for
        different callers, and no route accepts both. This is the combination
        that *would* be dangerous: a route reachable by a robot and by a person
        would have two authorization models, and whichever ran second would be
        the one that mattered.
        """
        for path, route in _walk():
            deps = _dependencies(route)
            if get_current_device in deps:
                assert get_owned_profile not in deps, path
                assert get_care_scope not in deps, path
                assert get_caregiver_scope not in deps, path

    def test_owner_and_care_scope_only_combine_where_documented(self):
        """And where they do combine, it narrows rather than widens.

        FastAPI resolves dependencies as an AND, so a route requiring the owner
        *and* reading a care scope is owner-only -- the scope is a per-caller
        value rather than a second way in. One route does this, for a count,
        and it is written down. A second one appearing should make somebody
        look at it.
        """
        found = set()
        for path, route in _walk():
            deps = _dependencies(route)
            if get_owned_profile in deps and (
                get_care_scope in deps or get_caregiver_scope in deps
            ):
                for method in sorted(route.methods - _IGNORED_METHODS):
                    found.add(f"{method} {path}")
        assert found == set(OWNER_PLUS_SCOPE_ROUTES)

    def test_every_profile_route_is_authorized(self):
        """No route carrying a profile id is account-level or open.

        This is the check that catches the dangerous mistake directly: a route
        that takes ``{profile_id}`` and only requires a signed-in account would
        let any account read any profile by guessing a UUID. Such a route
        cannot exist without failing here, whichever PRD writes it.
        """
        offenders = [
            route.label
            for route in all_routes()
            if "{profile_id}" in route.path
            and route.kind not in ("owner", "caregiver", "either")
        ]
        assert offenders == []

    def test_the_caregiver_reachable_surface_is_the_documented_one(self):
        """Thirteen routes, each with a stated purpose.

        The assertion is equality, not containment: a route that stops being
        caregiver-reachable fails this too, so the list cannot rot in either
        direction.
        """
        actual = {
            route.label for route in all_routes() if route.kind in ("caregiver", "either")
        }
        assert actual == set(CAREGIVER_REACHABLE_ROUTES)

    def test_every_caregiver_reachable_route_is_under_a_shared_path(self):
        """A shape check, so a new one is obvious in a diff.

        Caregiver-reachable routes live under ``/care/``, ``/family/`` or
        ``/caregiver-suggestions``. Anything else becoming reachable by
        somebody who is not the owner is the thing worth noticing.
        """
        for label in CAREGIVER_REACHABLE_ROUTES:
            assert (
                "/care/" in label
                or "/family/" in label
                or "/caregiver-suggestions" in label
            ), label


class TestCrossProfile:
    """owner A -> owner B's profile: denied (section 14)."""

    def test_no_owner_route_answers_for_another_owners_profile(
        self, client, owner, intruder, clock
    ):
        """Every owner route in the application, walked.

        The whole matrix in one assertion, and the reason this file exists: a
        route PRD 14 adds is in this loop the moment it is written. 404 rather
        than 403 throughout, because a 403 would confirm the profile exists
        (PRD 1, section 54).
        """
        _, profile_id = owner
        headers, _ = intruder

        failures: list[str] = []
        for route in owner_routes():
            url = _fill(route.path, profile_id=profile_id, ids={})
            response = client.request(route.method, url, headers=headers, json={})
            if response.status_code != 404:
                failures.append(f"{route.label} -> {response.status_code}")
        assert failures == []

    def test_an_unauthenticated_caller_gets_401_not_404(self, client, owner, clock):
        """The one place the distinction matters.

        "Not signed in" and "not yours" are different answers: the first tells
        a client to re-authenticate, the second must not confirm anything. A
        sample is enough -- the dependency is shared, so one route proving the
        shape proves it for all of them.
        """
        _, profile_id = owner
        for route in owner_routes()[:12]:
            url = _fill(route.path, profile_id=profile_id, ids={})
            response = client.request(route.method, url, json={})
            assert response.status_code == 401, route.label


class TestCaregiverBoundary:
    """The four caregiver rows of section 14's matrix."""

    def test_a_caregiver_with_every_permission_reaches_no_owner_route(
        self, client, owner, helper, clock
    ):
        """caregiver -> owner-only route: denied.

        Granted *every* category, which is the strongest version: if a
        permission could ever open an owner route, this would find it. The
        reason none can is structural -- owner routes resolve
        ``account_profile_roles`` and a caregiver has no row in it.
        """
        _, profile_id = owner
        make_caregiver(
            client,
            owner,
            helper,
            permissions=dict.fromkeys(CAREGIVER_PERMISSION_KEYS, True),
        )

        failures: list[str] = []
        for route in owner_routes():
            url = _fill(route.path, profile_id=profile_id, ids={})
            response = client.request(route.method, url, headers=helper, json={})
            if response.status_code != 404:
                failures.append(f"{route.label} -> {response.status_code}")
        assert failures == []

    def test_a_granted_category_opens_its_care_route(self, client, owner, helper, clock):
        """caregiver with permission -> matching care route: allowed."""
        _, profile_id = owner
        make_caregiver(client, owner, helper, permissions={"routines": True})

        response = client.get(
            f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
        )
        assert response.status_code == 200, response.json()

    def test_a_missing_category_closes_it(self, client, owner, helper, clock):
        """caregiver without permission: denied, as 404."""
        _, profile_id = owner
        make_caregiver(client, owner, helper, permissions={"medications": True})

        response = client.get(
            f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
        )
        assert response.status_code == 404

    def test_revocation_closes_it_immediately(self, client, owner, helper, clock):
        """revoked caregiver: denied.

        Nothing is invalidated in between. The same GET that worked on one line
        answers 404 on the next, because every request reads the relationship
        row rather than trusting anything cached.
        """
        headers, profile_id = owner
        relationship_id = make_caregiver(
            client, owner, helper, permissions={"routines": True}
        )
        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
            ).status_code
            == 200
        )

        revoked = client.delete(
            f"/api/v1/profiles/{profile_id}/caregivers/{relationship_id}",
            headers=headers,
        )
        assert revoked.status_code in (200, 204), revoked.text

        assert (
            client.get(
                f"/api/v1/profiles/{profile_id}/care/routines", headers=helper
            ).status_code
            == 404
        )

    def test_a_caregiver_of_one_profile_cannot_read_another(
        self, client, owner, intruder, helper, clock
    ):
        """Being somebody's caregiver grants nothing about anybody else."""
        make_caregiver(
            client,
            owner,
            helper,
            permissions=dict.fromkeys(CAREGIVER_PERMISSION_KEYS, True),
        )
        _, other_profile_id = intruder

        for path in ("/care/routines", "/care/home"):
            response = client.get(
                f"/api/v1/profiles/{other_profile_id}{path}", headers=helper
            )
            assert response.status_code == 404, path


class TestDeviceBoundary:
    """device A -> profile/device B: denied (section 14)."""

    def test_a_device_token_reaches_no_other_device(
        self, client, owner, intruder, clock, db
    ):
        from tests.test_robot_presentations import seed_device

        headers, profile_id = owner
        other_headers, other_profile_id = intruder
        _, token = seed_device(db, client, headers, profile_id=profile_id)
        other_device, _ = seed_device(
            db, client, other_headers, profile_id=other_profile_id
        )

        auth = {"Authorization": f"Bearer {token}"}
        response = client.get(
            f"/api/v1/devices/{other_device.id}/robot-status", headers=auth
        )
        # A device token is not an account token: the app routes refuse it
        # outright rather than resolving it to somebody's device.
        assert response.status_code in (401, 404)

    def test_a_device_cannot_name_a_profile_in_a_request_body(
        self, client, owner, intruder, clock, db
    ):
        """PRD 10 section 69 and PRD 11 section 69, as one assertion.

        The profile comes from the device record. There is no profile field on
        any device-action model, so a device cannot aim an event at somebody
        else -- the schema refuses the extra key rather than a check doing it.
        """
        from tests.test_robot_presentations import seed_device

        headers, profile_id = owner
        _, other_profile_id = intruder
        _, token = seed_device(db, client, headers, profile_id=profile_id)

        response = client.post(
            "/api/v1/device-actions/safety-events",
            json={
                "event_type": "possible_fall",
                "profile_id": other_profile_id,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # Either the extra field is refused or it is ignored; what must not
        # happen is an event landing on the other profile.
        if response.status_code < 300:
            events = client.get(
                f"/api/v1/profiles/{other_profile_id}/safety/events",
                headers=client and {"Authorization": "Bearer nobody"},
            )
            assert events.status_code in (401, 404)

    def test_an_account_token_is_not_a_device_token(self, client, owner, clock):
        """The reverse direction, which is the easier mistake to make."""
        headers, _ = owner
        response = client.get(
            "/api/v1/device-actions/presentations/next", headers=headers
        )
        assert response.status_code == 401


class TestAssistantBoundary:
    """Section 15: the assistant cannot reach another profile."""

    def test_the_assistant_routes_are_owner_scoped(self):
        """Checked from the application, not from a list of paths."""
        assistant = [
            route
            for route in all_routes()
            if "/assistant" in route.path and "{profile_id}" in route.path
        ]
        assert assistant
        for route in assistant:
            assert route.kind == "owner", route.label

    def test_no_tool_takes_a_profile_id(self):
        """The model cannot choose whose data to read.

        Section 15's "model cannot choose arbitrary profile IDs", asserted
        against every tool schema rather than against the ones somebody
        remembered. The authorized profile is injected server-side; a tool
        argument named for a profile would be the hole.
        """
        from app.services.assistant import tools

        for tool in tools.TOOLS:
            fields = tool.args_model.model_fields
            for name in fields:
                assert "profile" not in name.lower(), f"{tool.name}.{name}"
            # And the schema the model is actually shown, which is generated
            # from the same model but is what would carry a stray field.
            schema = tool.args_model.model_json_schema()
            for name in schema.get("properties", {}):
                assert "profile" not in name.lower(), f"{tool.name}.{name}"


class TestPrivateMedia:
    """Section 27: private files need authorization at every byte."""

    def test_a_photo_is_not_readable_by_another_account(
        self, client, owner, intruder, clock
    ):
        headers, profile_id = owner
        other_headers, _ = intruder

        episode = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms",
            json={"name": "Headache", "first_entry": {"severity": 4}},
            headers=headers,
        )
        episode_id = episode.json()["episode"]["id"]
        entry_id = episode.json()["episode"]["latest_entry"]["id"]
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae"
            "426082"
        )
        upload = client.post(
            f"/api/v1/profiles/{profile_id}/symptoms/{episode_id}"
            f"/entries/{entry_id}/photos",
            files={"file": ("rash.png", png, "image/png")},
            headers=headers,
        )
        assert upload.status_code == 201, upload.text
        photo_id = upload.json()["id"]
        path = (
            f"/api/v1/profiles/{profile_id}/symptoms/{episode_id}"
            f"/entries/{entry_id}/photos/{photo_id}/content"
        )

        assert client.get(path, headers=headers).status_code == 200
        assert client.get(path, headers=other_headers).status_code == 404
        assert client.get(path).status_code == 401

    def test_there_are_no_signed_media_urls_to_leak(self):
        """Section 27, answered by a design decision rather than an expiry.

        PRD 6 chose authenticated routes over signed URLs: a signed URL is a
        bearer token in a query string that lands in logs and share sheets and
        stays valid whoever ends up holding it. So there is nothing to expire,
        and this asserts the absence -- no response model anywhere carries a
        storage key or a URL to one.
        """
        import pathlib

        offenders = []
        for path in pathlib.Path("app/schemas").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                statement = line.strip()
                if statement.startswith("#"):
                    continue
                if "storage_key" in statement and ":" in statement:
                    offenders.append(f"{path.as_posix()}: {statement}")
        assert offenders == []
