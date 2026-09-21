# 0006 — The Today screen, dashboard cards and offline check-ins

**Status:** Accepted · PRD 3

## Context

Today becomes the app's landing page. It has to open quickly, survive a phone
with no signal, work with no robot attached, and keep working as five more
feature areas want a place on it. Four decisions were needed before writing it.

## Decision 1 — one aggregate endpoint, not one per feature

`GET /api/v1/today` returns the profile, the check-in state, the robot and the
card layout together.

The alternative is a request per card. That is simpler to write and worse to
use: five feature areas means five round trips on a phone network, a screen
that fills in piece by piece, and five independent chances to fail. Assembling
the day on the server also puts the decision of *what belongs on Today* in one
place rather than spread across the client.

The cost is that the endpoint grows with every PRD, and a slow query anywhere
slows the whole screen. Both are acceptable now and worth revisiting if a card
ever needs data that is genuinely expensive — at which point that one card can
have its own request without disturbing the rest.

## Decision 2 — a card registry, not a screen that knows every card

Cards are declared once in `app/services/dashboard.py`, keyed by string. The
client has a renderer per key it knows, and skips keys it does not. Adding a
card in a later PRD is three edits — server registry, key union, renderer map
— and no change to the Today screen itself.

Each card carries `available`, which is false while the feature behind it does
not exist. Such a card is listed but never shown, and the API refuses to store
a preference for it. That is what lets `medications`, `appointments`,
`symptoms`, `routines`, `hydration` and `physiotherapy` reserve their keys now
without anyone seeing an empty medication card, and it means a card cannot be
switched on by a client that has got ahead of the server.

An app older than the backend degrades rather than breaking: an unknown key is
dropped at parse time.

## Decision 3 — dashboard preferences as rows, not JSON

`dashboard_preferences` is one row per `(profile_id, card_key)`, rather than a
JSON blob on `user_settings`.

Rows won for two reasons. The preference belongs to a *profile* — in assisted
setup, the dashboard describes the cared-for person's day — and `user_settings`
is per account, so a blob would have needed a new home anyway. And a card the
user has never touched simply has no row, so it falls back to the registry
default; a blob would have to be migrated, or carefully merged, every time a
card is added.

`card_key` deliberately has **no** CHECK constraint. The set of cards grows
with every feature PRD and a constraint would mean a migration each time. The
API validates against the registry instead — the thing that actually knows
whether a card exists.

## Decision 4 — the user's local day, and the latest edit wins

A check-in belongs to a **local calendar date**, sent by the client and stored
as a plain date. Someone checking in at 11pm in Karachi means that day, not the
following one in UTC. The server accepts any date within one day of its own:
real offsets run from UTC-12 to UTC+14, so one day either way covers the world,
while stopping the "today" endpoints being used to write arbitrary history.

A check-in made with no signal is written to the device and marked as unsent on
the card, then sent when the connection returns. The endpoint is a `PUT` keyed
on `(profile_id, checkin_date)` with a unique constraint behind it, so a queued
answer that arrives late updates the same row — a duplicate daily record is not
merely avoided, it is impossible.

Conflicts are settled by **the latest explicit user edit**. The client sends
`client_updated_at`: when the user chose the answer, not when the request
arrived. If the stored row has been edited more recently, the stored row stands
and is returned unchanged with `applied: false`, and the client adopts it. The
two converge in one round trip, and an answer that sat in a queue for hours
cannot overwrite a newer one.

Deliberately *not* decided here: a general offline synchronisation engine. The
queue holds at most one entry, because there is at most one check-in per day
and only today's can be edited. When another feature needs offline writes, it
should be designed then, against its own requirements.

## Consequences

- Today opens with one request and no spinner per card.
- A later PRD adds a card without touching the Today screen or a migration.
- A user's answer is never lost, never duplicated, and never silently replaced
  by a stale one.
- The Today response will keep growing; splitting it is a deliberate future
  decision, not an accident.
