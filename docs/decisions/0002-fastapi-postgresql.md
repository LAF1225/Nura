# ADR 0002 — FastAPI and PostgreSQL for the backend

- **Status:** Accepted
- **Date:** 2026-09-12
- **Context:** PRD 0

## Context

Nura will eventually store health information, which is sensitive and
relational: users have conditions, medications, schedules, devices, caregivers
and permissions, and access to each has to be checked against who is asking.

Two consequences follow. The data model needs real constraints and
transactions, and the authorisation decisions cannot live in the client — a
phone app is not a trustworthy place to decide who may read a medical record.

## Decision

Use **FastAPI** with **PostgreSQL**, reached through **SQLAlchemy 2.0** with
migrations managed by **Alembic**.

Supporting choices:

- **Synchronous** SQLAlchemy sessions, not async.
- **psycopg 3** as the driver.
- Pydantic models for every request and response body.
- The backend is a separate service from the app. No critical health or
  permission logic is placed in the client.

### Why synchronous SQLAlchemy

This is the decision most likely to be questioned, so the reasoning is
recorded.

FastAPI runs synchronous endpoint functions in a worker threadpool, which is
sufficient for this workload: Nura's traffic is a small number of personal
devices, not a high-concurrency public API. Sync sessions are markedly easier
to read and debug — no `await` on every query, no async context-manager
plumbing, and Alembic's default environment works without an `asyncio.run`
wrapper. PRD 0 states plainly that the codebase must be understandable by a
technically capable student who may have to debug it by hand, and that argues
against async until there is a measured reason for it.

Switching later is contained: `create_engine` becomes `create_async_engine`,
`Session` becomes `AsyncSession`, and endpoints gain `await`. Because every
database access goes through the `get_db` dependency in `app/db/session.py`,
there is one seam to change rather than many.

## Consequences

**Good**

- PostgreSQL gives foreign keys, check constraints and transactions, so
  integrity rules live in the database and not only in application code. The
  `theme` column is constrained there already, as a small worked example.
- FastAPI derives OpenAPI docs from the Pydantic models, so `/docs` stays
  accurate for free, which is useful while the mobile client is being built.
- Pydantic validates every request body server-side, which PRD 0 requires.
- Alembic from the first migration means no schema change is ever applied by
  hand, and a clean database can always be rebuilt by running migrations.
- Python keeps the door open for the later AI and signal-processing work.

**Costs and risks**

- PostgreSQL is heavier to run locally than SQLite. Accepted deliberately: the
  prototype should develop against the same engine it deploys on, and UUID and
  timezone-aware timestamp behaviour differ enough between the two to make
  SQLite a misleading stand-in.
- Sync sessions will need revisiting if the backend ever becomes I/O-bound on
  outbound calls. That is a real possibility once AI services are involved, and
  the seam above is where it gets addressed.

## Database hosting

Development runs a local PostgreSQL server. The prototype is expected to use
**Supabase-hosted PostgreSQL**, which also offers managed authentication,
storage and row-level security that later PRDs may use.

Nothing in the backend knows which of these it is talking to: the only input is
`DATABASE_URL`. Moving to Supabase is a one-line change followed by
`alembic upgrade head`.

Authentication is expected to use **Supabase Auth** (PRD 1). The app records
the provider's subject as `users.auth_provider_id` rather than treating the
provider's identifier as Nura's own primary key, so the auth provider can be
replaced later without rewriting every table that references a user.

## Alternatives considered

- **Django + DRF.** Batteries included, with a mature admin and auth system.
  Rejected as too much framework for an API-only service, and its ORM and
  migration conventions are heavier to reason about than SQLAlchemy plus
  Alembic for this size of schema.
- **Node.js (NestJS or Express) + Prisma.** Would unify the language with the
  mobile app, which is genuinely attractive. Rejected because Python is the
  better home for the later AI and sensor work, and that is harder to change
  than the API layer.
- **Supabase alone, with no backend of our own.** Tempting for speed: the app
  could talk to PostgreSQL directly with row-level security. Rejected because
  it would put authorisation for health data into client-side policies. Nura
  needs server-side logic it fully controls — caregiver permission chains and
  emergency escalation are not things to express as RLS policies.
- **MongoDB.** Rejected: this data is relational, and the integrity guarantees
  are the point.
