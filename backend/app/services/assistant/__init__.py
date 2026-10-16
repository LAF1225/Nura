"""The Nura assistant (PRD 8).

Laid out as section 9 describes it, one file per responsibility:

    provider.py            the model boundary -- shapes, errors, the factory
    anthropic_provider.py  the one adapter that imports a provider SDK
    prompts.py             every instruction Nura is given, versioned
    policy.py              the guardrails that do not depend on the model
    context.py             what goes in the prompt before any tool runs
    tools.py               what Nura may read, and the one thing it may propose
    memory.py              durable preferences, and noticing one
    preferences.py         personality, voice, verbosity, mode
    conversations.py       threads and the messages in them
    proactivity.py         what Nura brings up first, from app data only
    limits.py              how often one person may ask
    service.py             the single path a message takes

Nothing outside this package imports ``provider``: section 9 asks for a
dedicated service boundary, and ``service.NuraAssistantService`` is it.
"""
