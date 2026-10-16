"""Appointments, preparation and doctor reports (PRD 7).

Split the way the workflow is:

``appointments``   the visit itself -- create, edit, cancel, complete, list.
``questions``      what the person wants to ask, in their own words.
``periods``        which stretch of time a report covers, and why.
``preparation``    reading the records back for review. No interpretation.
``suggestions``    deterministic question prompts. No model, ever.
``snapshot``       turning a selection into the finished, frozen report text.
``pdf``            turning that snapshot into a document.
``reports``        versions, private storage, and what is safe to export.
``summary``        what Today and Care need to know.

The order matters: everything above ``snapshot`` only reads, and ``snapshot``
is the one place where recorded facts become sentences. That is deliberate --
it means "does Nura say anything it should not?" has exactly one file to read
(PRD 7, sections 3, 16, 29 and 45).
"""
