"""One builder per source domain (PRD 11, section 74).

::

    medication.py    a dose that is due (sections 21, 22, 56)
    appointments.py  a visit that is coming (section 23)
    messages.py      an authorized family message (sections 24, 78)
    assistant.py     a reply, made concise (sections 26, 79, 80)
    safety.py        PRD 10's state, rendered truthfully (sections 8, 9, 113)
    system.py        the face, offline and setup cards (sections 34, 35, 83)

**The builders are where privacy is applied** (section 73's list). A medication
reminder is shortened to a privacy level *while the payload is built*, so there
is no later stage where the full name could be reattached -- the row in
``device_presentations`` is already the redacted one, and the history endpoint
reads that same row.

**Nothing in here is reached by the model.** Section 71 keeps the assistant
behind a bounded service: ``assistant.build`` takes a string and two booleans
and chooses the layout itself. There is no parameter through which a payload,
a layout or an action could be supplied.

**No builder is required for a workflow to work.** Sections 51-54 and 100-102:
every one of these is called from ``presenter.refresh``, which reconciles what
the robot should be showing against what is currently true. A builder that
raised, a device that is offline and a robot that was never built all leave the
underlying dose, appointment, message and escalation exactly as they were.
"""
