# ADR 0004 — Supabase Auth, with token verification in our own backend

Status: accepted (PRD 1)

## Context

PRD 1 requires Sign in with Apple, Sign in with Google, phone (one-time code)
and email, with real sessions, secure token storage and protected backend
routes. PRD 0 already anticipated this: "Authentication may use Supabase Auth
so infrastructure can later be replaced without rebuilding the entire
application."

Building all four providers ourselves would mean running an SMS pipeline,
implementing OAuth flows for two vendors, and storing password hashes — a large
amount of security-critical surface for a project at this stage.

## Decision

**Supabase Auth issues identities; the Nura backend verifies them and owns all
application data.**

- The mobile app talks to Supabase only for authentication.
- Every access token is sent to our own FastAPI backend as a bearer token.
- The backend verifies the signature against the project's **public JWKS
  endpoint**, then maps the token's `sub` claim to a local `users` row.
- Application data (profiles, onboarding, devices, and later health records)
  lives in our own PostgreSQL database, never in Supabase tables.

### Why JWKS rather than a shared secret

Supabase supports both asymmetric signing (a published JWKS) and a legacy
shared HS256 secret. We default to JWKS because:

- no secret has to be copied into the backend environment, or handed to anyone;
- key rotation happens without a redeploy;
- `SUPABASE_URL` is all the backend needs, and it is not sensitive.

`SUPABASE_JWT_SECRET` is still supported for older projects, but should be left
unset.

### Accounts are provisioned on first authenticated request

There is no separate "register" endpoint to keep in step with the provider.
The first request carrying a valid token creates the local account row. This
keeps exactly one source of truth for identity and removes a class of bug where
a user exists in one system but not the other.

## Consequences

**Good**

- Four providers without operating any auth infrastructure.
- Password handling is entirely out of our codebase (PRD 1, section 49).
- Replaceable: the app depends on `AuthService`, and the backend depends only
  on "a verifiable token with a `sub` claim". Swapping providers means
  reimplementing one module and one verifier.

**Costs and risks**

- A hard dependency on a third party for sign-in availability.
- Phone sign-in needs a paid SMS provider configured in Supabase, so it cannot
  be exercised on the free tier.
- The anon key ships inside the app bundle. This is by design — it grants
  nothing on its own — but it does mean our backend, not the key, is what
  protects data. Hence every protected route verifies the token and resolves
  the account itself rather than trusting anything the client sends
  (PRD 1, section 36).

## Alternatives considered

**Email/password implemented directly in FastAPI.** Fully verifiable with no
external account, and tempting for that reason alone. Rejected because it still
leaves Google, Apple and phone unsolved, and it would put password hashing,
reset-token handling and rate limiting into a codebase that has no need to own
them.

**Supabase as the database too, with row-level security.** Rejected: PRD 0
deliberately places application and health logic in our own backend, and
splitting authorisation between RLS policies and FastAPI would mean two places
to get health-data permissions right.
