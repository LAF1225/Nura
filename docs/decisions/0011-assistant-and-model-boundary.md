# 0011 — The Nura assistant and the model boundary

**Status:** Accepted · PRD 8

## Context

PRD 8 puts a language model inside a health app. That changes the nature of
every question the previous PRDs answered: what Nura may say is no longer a
matter of which sentences were written, because the sentences are generated;
what data leaves the system is no longer a matter of which screens exist,
because a prompt can carry anything; and what Nura can *do* is no longer fixed
by the routes, because a model can ask for a tool.

Seven decisions shaped the answers.

## Decision 1 — one method at the model boundary, and one file that imports an SDK

`AIModelProvider.complete(request) -> reply`. `anthropic_provider.py` is the
only module in the backend that imports a provider SDK, and nothing outside
`services/assistant/` imports `provider` at all.

The shapes are smaller than any provider's API on purpose. A `Turn` is a role
plus text plus tool calls or results; a `ProviderReply` is text, tool calls and
why it stopped. Images in conversation, citations, server-side tools and
prefill have no representation, because a shape nothing fills is a shape the
next provider has to emulate for no reason.

The cost is that using a provider-specific feature later means widening the
interface deliberately rather than reaching for it. That is the point: PRD 8
section 10 asks for the provider to be changeable, and an abstraction that
leaks the first provider's feature set is not one.

## Decision 2 — the deterministic layer is the guarantee; the prompt is not

`policy.py` runs on the user's own words, before and after the model. It
short-circuits the emergency phrase without a provider call, decides serious
mode, and *places* the section 73 sentences around a reply rather than asking
the model for them.

PRD 8 section 74 says not to rely entirely on model judgement. The stronger
reason is testability: with the sentences placed, the section 72 guardrail
tests can script a deliberately unhelpful reply — a bare sentence with no
caveat — and still assert the guarantee. A guardrail test that passes because
the canned reply happened to contain the right words is testing the canned
reply.

The patterns are high-precision and low-recall. "Should I stop taking my
tablets?" fires; a vaguer version does not. Section 38 warns against treating
every health question as an emergency, so broadening them is a trade rather
than a free improvement.

## Decision 3 — nothing scrubs the model's output, and the docs say so

There is no filter that removes a diagnosis from a reply.

A regular expression catching most ways of saying "you have migraine" would let
the rest through while making everyone believe none got through. A guarantee
that half works is worse than one that is honestly absent, because it is the
one people plan around. What keeps Nura from diagnosing is the prompt and the
structure; `assistant-safety.md` has a section headed **What is not enforced**
that says exactly this, next to the things that *are* guaranteed.

The alternative considered — refusing to ship without an output filter — would
have meant either shipping the false guarantee or not shipping PRD 8.

## Decision 4 — context is counts, and everything else is a tool

The prompt carries a date and three numbers: how many active medications, open
symptoms and upcoming appointments exist. No name, no condition, no note, no
title.

PRD 8 section 11 lists possible context sources and section 12 asks for
minimal, purpose-specific context; section 51 says to use explicit retrieval
rather than unrestricted access. Reading those together, the only defensible
default is that nothing about the record is volunteered. Somebody who asks Nura
about the weather has not had their prescriptions sent anywhere, and a test
asserts it by planting four records and checking none of their names appears.

Counts rather than nothing, because without them the model cannot tell whether
a tool call is worth making, so it either always calls or never does. Three
numbers buy the judgement that saves a round trip on every message.

## Decision 5 — the model can propose one change, and a person makes it

`add_appointment_question` checks what can be checked, returns a pending action
and writes nothing. The write happens on a separate request, from a Confirm the
user pressed, re-resolving the appointment through the profile-scoped lookup.

PRD 8 section 14 asks for confirmation on write actions and section 15 lists
what must never be reachable. Both are satisfied structurally rather than by
care: the destructive tools do not exist, and the one constructive tool does
not write.

Making the tool write directly and showing an undo was considered and rejected.
An undo is a promise about a *reversible* change, and PRD 8's whole posture on
health data is that Nura does not change it quietly (section 14: "do not
silently change health data").

## Decision 6 — memory is deterministic, narrow, and always agreed to

`memory.detect_suggestion` is a table of patterns for the shapes section 93
lists. It proposes; the user presses Remember; the app posts a memory like any
other.

A second model call asking "was that a durable preference?" would cost a
request per message and answer "sometimes yes" on "I'm tired today" — precisely
the statement section 42 warns about. Deterministic detection misses cases; the
memory screen catches them, because a user can always add one by hand. Missing
a preference costs a small convenience. Saving the wrong thing costs trust in
what Nura knows about somebody.

The category set has nothing clinical in it, and there is no foreign key from
any assistant table into the health record — so section 40's line between
memory and health data is structural, and section 61's promise that deleting a
conversation reaches nothing else is checked by looking at the foreign keys
rather than by trying it.

## Decision 7 — three-step controls instead of sliders

Section 62 draws sliders; section 23 allows 0–100 *or* Low / Medium / High and
asks for one consistent UI. Every personality dial, the proactivity level and
the verbosity setting use the same three- or four-step control.

The reason is section 83 rather than taste. A three-way control has 48dp
targets, announces its options and its selection to a screen reader, works with
a shaking hand and reads the same at every type size. A 101-point slider does
none of those, and the extra precision would not change a word of the prompt it
feeds — the prompt has one sentence per named level.

The shipped defaults are exactly the Gentle preset's values, so a profile that
has never opened the Personality screen is on one of the four buttons rather
than on an unnamed combination no button corresponds to.

## Consequences

- The model is a deployment decision. Changing provider means writing a sibling
  of `anthropic_provider.py` and changing `AI_PROVIDER`.
- The whole test suite runs with no API key and no network, against
  `ScriptedProvider` (section 101). Nothing costs money to test.
- **The Anthropic adapter is unverified.** No request has reached Anthropic
  from this repository. Its request and reply shapes are tested offline; the
  round trip is not.
- The prompt layer has never been evaluated against a real model. The
  deterministic layer is provider-independent and would behave identically
  against any.
- A future robot is a source of messages rather than a parallel system:
  `conversation_messages.source` is already there, and `mobile_text` is the
  only value a client may send.
