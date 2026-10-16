"""Safety monitoring, SOS and escalation (PRD 10).

Split so that the three things that must never be confused live apart:

    capabilities  what this build can actually do -- and cannot
    monitoring    the session: started explicitly, ended exactly when asked
    events        something happened; the one place an event is created
    checks        the user's answer, the deadlines, and what runs out of time
    escalation    who is reached, in what order, and what really happened
    providers     the boundary to anything outside this system
    detectors     where a future robot's observations would come in
    audit         what the system did, kept minimal
    wording       every sentence these features say

**Three sentences this package exists to keep true.**

*Nura does not diagnose.* An event type says what was observed and begins with
``possible_`` when a sensor observed it. Nothing here turns an observation into
a finding, and ``wording`` has no sentence that could (sections 3, 16 and 52).

*Nura does not watch unless asked.* A passive trigger with no active monitoring
session is refused, not quietly processed (sections 4 and 22).

*Nura never says somebody was reached unless somebody was reached.* The only
delivery channel that exists in this build is an in-app alert record, and even
that is recorded as ``attempted`` rather than ``delivered``, because a record is
not a reading (sections 35, 38 and 39).
"""
