# Safety and emergency architecture

**Status: documented only. None of this is implemented, and none of it may be
implemented before the PRD that owns it.**

This exists so that the foundation does not accidentally foreclose the design,
and so nobody has to reconstruct the intent later. PRD 0 contains no event
detection, no escalation, no contacts and no calling.

## Escalation flow

The principle is that Nura asks before it escalates, and a person always gets
the chance to say "I'm fine".

```text
            Possible event detected
                      │
                      ▼
               Prompt the user
                      │
                      ▼
      Wait a user-configured period
                      │
                 Response?
                  ╱        ╲
               Yes          No
                │            │
                ▼            ▼
        Continue safely   Escalate to the emergency
                          contact priority chain
```

Events that may later qualify: falls, seizure-like activity, vomiting,
prolonged immobility, and obvious calls for help.

## The explicit override

Saying **"Nura, emergency"** must bypass the waiting period entirely and begin
escalation immediately. A person asking for help directly is not a signal that
needs confirming.

## Constraints on any future implementation

- **Describe, never diagnose.** "Nura noticed unusual movement", not "Nura
  detected a seizure." A detected event is an observation, not a finding.
- **The waiting period is the user's to set**, including how long it lasts and
  who is contacted in what order.
- **Escalation order is an explicit, ordered chain**, not a broadcast.
- **A missed response is not proof of an emergency.** The design tolerates
  false positives by asking first; it must not tolerate silently escalating
  without having asked, except for the explicit override above.
- **Detection must be separable** from general assistant functionality, so
  companion features can change without touching the safety path.
- **Camera and microphone data is not retained by default.** Any capture needs
  an explicit retention rule decided before the feature ships.
- **Offline behaviour must be deliberate.** PRD 0 only prepares for offline
  states; medication alarms and offline emergency behaviour are out of scope
  and must not be approximated.

## Caregiver access

Caregiver visibility will require an explicit, granted permission record.
An API must never return medical data merely because a client supplied a user
id — see the security posture in
[system-overview.md](system-overview.md).
