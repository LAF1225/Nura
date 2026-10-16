"""Daily life: tasks, reminders, alarms and routines (PRD 12).

Six modules, and the division is PRD 12 section 4's::

    recurrence.py    when a repeating thing happens next
    tasks.py         something to finish
    reminders.py     a message at a time, and its occurrences
    alarms.py        a time of day whose purpose is to be noticed
    routines.py      a repeated set of steps, its runs and its steps
    summary.py       the counts Today and Care read
    capabilities.py  what Nura can actually reach, truthfully
    wording.py       every sentence any of it says

Four sentences govern all of it.

**Nothing here decides daylight saving.** ``recurrence`` resolves a local date
and a wall-clock time to an instant by calling
``services.medications.doses.occurrence_instant`` -- PRD 5's function, with
PRD 5's answers to the hour that happens twice and the hour that never
happens. Section 35 says not to build a second, contradictory policy, and the
way to be sure is to have no second implementation to disagree with.

**Nothing here is clinical.** A routine may say "stretch for five minutes"
because somebody typed it or a clinician told them to. Nothing in this package
creates, suggests or adjusts a routine from a symptom, a diagnosis or a model's
inference, and nothing reads a medication schedule in order to change one
(sections 15, 23 and 24).

**The robot is additive and nothing here knows about it.** Every function
below works, and is tested, with no device row in the database. The robot
learns about a task the same way it learns about a dose: PRD 11's
``services.robot.presenter`` reads what is true and makes the queue match
(section 31).

**What is logged is that something happened, never what it was.** Section 45
allows ``task.create success`` and section 46 allows ``task_created``; a task
title is the user's own words and section 45 rules out putting it in a general
application log. Every log line in this package is an action name and, at most,
a count.
"""
