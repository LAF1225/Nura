"""The robot presentation layer (PRD 11).

Three sentences govern everything in this package.

**The robot is additive.** No workflow in PRD 0-10 may depend on it. A
medication reminder, an appointment, a family message and an escalation all
happen exactly as they did before; queueing a card for a robot is something
that happens *afterwards*, in a try/except that cannot fail the thing it was
describing. Sections 51, 52, 53, 54, 100, 101 and 102.

**A presentation is a request, not a render.** The backend can say what it
would like shown. Only the device can say what was shown, and it says it with
an acknowledgement. There is no code path that marks a presentation
``displayed`` because a fetch returned it -- and a CHECK constraint on
``device_presentations`` means there cannot be one. Sections 14, 19 and 141.

**A capability is what the device reported, never what the firmware could
compile.** ``not_verified`` exists for the case where a driver is present and
nothing physical has been proven, and only a device can report it. Nothing in
this package infers a capability from a build flag, and nothing claims a
display, a speaker or a microphone works. Sections 10, 11, 12, 90, 91 and 92.

Where things live::

    wording.py       every sentence the robot says (section 75)
    layouts.py       the envelope, the eight layouts, the limits (sections 37, 38, 77)
    capabilities.py  what the device said it can do (sections 10-12)
    preferences.py   how this robot should behave (sections 46-49)
    queue.py         queue, priority, preemption, expiry, acknowledgement (section 73)
    modes.py         which mode the robot is in, derived (sections 4, 83, 84)
    builders/        one module per source domain (section 74)
    simulator.py     a robot that is not there (sections 62-64)

**Nothing in this package has ever driven hardware.** There is no display, no
speaker, no microphone and no acknowledgement from a physical robot. What is
verified is the contract, the queue and the simulator.
"""
