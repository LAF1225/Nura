"""Everything the robot says, read in one pass.

PRD 11, sections 7, 8, 9, 12, 20, 28, 47, 75, 115 and 135.

Section 75 asks for reviewable robot-copy modules and warns against scattered
inline health and emergency text. The payoff is this file: because all the
prose is in ``services.robot.wording``, "nothing over-claims" is an exhaustive
check rather than a spot check.

Four rules, each a test, and each with the sentence the PRD names:

  section 8   "Help is on the way."     forbidden unless a provider confirmed
  section 9   "Fall detection active"   forbidden unless a detector reports
  section 20  the robot displayed it    forbidden without an acknowledgement
  section 115 implying physical arrival  forbidden, acknowledgement or not

The same discipline PRD 10 applied to safety wording, and PRD 10's own module
is imported rather than reimplemented so the robot cannot develop a second,
looser vocabulary for the same events.
"""

import inspect

from app.services.robot import wording


def every_string() -> list[tuple[str, str]]:
    """Every literal in the module, plus every sentence it can generate.

    Generated at the edges on purpose: a function is only safe if it is safe
    for the arguments it will actually receive, and "no alert labels, no
    calling provider, no contacts" is the configuration every deployment of
    this project is in.
    """
    found: list[tuple[str, str]] = []
    for name, value in vars(wording).items():
        if name.startswith("_"):
            continue
        if isinstance(value, str):
            found.append((name, value))
        elif isinstance(value, dict):
            for key, text in value.items():
                if isinstance(text, str):
                    found.append((f"{name}[{key}]", text))

    # Every generated sentence, at its edges.
    found.extend(
        (f"emergency_lines({case})", line)
        for case, lines in (
            (
                "nobody permitted",
                wording.emergency_lines(
                    alert_labels=(), calling_configured=False, has_contacts=True
                ),
            ),
            (
                "no contacts",
                wording.emergency_lines(
                    alert_labels=(), calling_configured=False, has_contacts=False
                ),
            ),
            (
                "one caregiver",
                wording.emergency_lines(
                    alert_labels=("Ayesha",), calling_configured=False, has_contacts=True
                ),
            ),
            (
                "calling configured",
                wording.emergency_lines(
                    alert_labels=("Ayesha",), calling_configured=True, has_contacts=True
                ),
            ),
        )
        for line in lines
    )
    found.extend(
        ("emergency_cancelled_lines", line)
        for line in wording.emergency_cancelled_lines()
    )
    found.extend(
        ("monitoring_lines", line)
        for line in wording.monitoring_lines(ends_at=None, zone="UTC")
    )
    found.extend(
        ("safety_check_lines", line)
        for line in wording.safety_check_lines(name="Ada", seconds=45)
    )
    found.extend(
        ("safety_check_lines/anonymous", line)
        for line in wording.safety_check_lines(name=None, seconds=45)
    )
    found.append(("acknowledgement_line", wording.acknowledgement_line("Ayesha")))
    found.append(("no_response_line", wording.no_response_line(45)))
    found.append(
        (
            "history_line/expired",
            wording.history_line(
                presentation_type="medication_reminder", status="expired"
            ),
        )
    )
    found.append(
        (
            "history_line/sent",
            wording.history_line(presentation_type="family_message", status="sent"),
        )
    )
    found.append(
        (
            "history_line/failed",
            wording.history_line(
                presentation_type="safety_status",
                status="failed",
                failure_code="render_failed",
            ),
        )
    )
    found.append(
        (
            "capability_sentence",
            wording.capability_sentence(key="display", state="not_verified"),
        )
    )
    return found


class TestNothingOverClaims:
    def test_nothing_says_help_is_coming(self):
        """Section 8 names this sentence and forbids it.

        No provider exists, so the emergency card reports what PRD 10 actually
        did: an in-app alert record was created, and calling is not
        configured.
        """
        forbidden = (
            "help is on the way",
            "help is coming",
            "on their way",
            "emergency services",
            "ambulance",
            "dispatched",
        )
        for name, text in every_string():
            lowered = text.lower()
            for phrase in forbidden:
                assert phrase not in lowered, f"{name}: {text!r}"

    def test_nothing_says_a_detector_is_watching(self):
        """Section 9 names this one.

        ``monitoring_lines`` cannot produce it: the only thing it says is that
        Safety Monitoring is on and until when, which is what PRD 10 knows.
        """
        forbidden = (
            "fall detection",
            "detecting",
            "detector",
            "monitoring your",
            "watching you",
            "seizure",
            "vomiting",
        )
        for name, text in every_string():
            lowered = text.lower()
            for phrase in forbidden:
                assert phrase not in lowered, f"{name}: {text!r}"

    def test_nothing_claims_the_robot_showed_spoke_or_played_anything(self):
        """Sections 20 and 141.

        There is no sentence here that says a card was displayed, a message
        was read out or a chime was played. What the app says instead for an
        offline robot is ``OFFLINE_NOTE``, and the history statuses stop at
        "sent to Nura".
        """
        forbidden = (
            "nura showed",
            "nura displayed",
            "was displayed on",
            "read aloud to",
            "spoken aloud",
            "played aloud",
            "nura said",
            "nura called",
        )
        for name, text in every_string():
            lowered = text.lower()
            for phrase in forbidden:
                assert phrase not in lowered, f"{name}: {text!r}"

    def test_nothing_promises_anything(self):
        """PRD 10 section 72 carried forward: no guarantees."""
        for name, text in every_string():
            lowered = text.lower()
            for phrase in ("guarantee", "always", "never miss", "we promise"):
                assert phrase not in lowered, f"{name}: {text!r}"

    def test_an_acknowledgement_is_not_an_arrival(self):
        """Section 115's clause, as its own test because it is easy to miss."""
        line = wording.acknowledgement_line("Ayesha")
        for phrase in ("arriv", "nearby", "on the way", "coming", "left", "visit"):
            assert phrase not in line.lower(), line


class TestWhatTheWordsHaveToSay:
    def test_sent_and_shown_are_different_words(self):
        """Section 14, in the labels rather than only in the statuses.

        A history row that said "shown" for a card the backend merely handed
        over would undo the whole acknowledgement contract at the last step.
        """
        assert wording.PRESENTATION_STATUS_LABELS["sent"] == "sent to Nura"
        assert wording.PRESENTATION_STATUS_LABELS["completed"] == "shown"
        assert wording.PRESENTATION_STATUS_LABELS["queued"] == "waiting"

    def test_not_verified_reads_as_untested_rather_than_broken(self):
        """Sections 12 and 47. It is not a promise and it is not a failure."""
        assert wording.CAPABILITY_STATE_LABELS["not_verified"] == "Not tested yet"
        assert wording.CAPABILITY_STATE_LABELS["available"] == "Working"
        assert wording.CAPABILITY_STATE_LABELS["unavailable"] == "Not fitted"
        assert wording.CAPABILITY_STATE_LABELS["not_connected"] == "Not reported"

    def test_the_hardware_note_says_the_robot_does_not_exist(self):
        """Section 135, in the place the app reads it from."""
        note = wording.NO_HARDWARE_NOTE.lower()
        assert "has not been built" in note
        assert "nothing here has run" in note

    def test_the_offline_note_is_about_the_phone_not_the_robot(self):
        """Section 20's exact replacement sentence."""
        assert wording.OFFLINE_NOTE == (
            "Robot offline — this item remains available on your phone."
        )

    def test_a_face_label_never_describes_a_feeling_about_the_person(self):
        """Section 28.

        ``concerned`` is described as attentive. The vocabulary has no label
        that a screen could reach for because a symptom was severe.
        """
        assert wording.FACE_LABELS["concerned"] == "Attentive"
        for label in wording.FACE_LABELS.values():
            assert label.lower() not in {"worried", "sad", "alarmed", "shocked"}

    def test_every_label_map_is_checked_against_its_tuple(self):
        """The drift guards, counted.

        Each label map in this module asserts itself against the value set it
        describes, which is what makes a new enum value a failing import
        rather than a missing label on a screen.
        """
        source = inspect.getsource(wording)
        assert source.count("assert set(") >= 12


class TestLengths:
    def test_every_constant_fits_the_layout_it_is_used_in(self):
        """Section 77's limits, applied to the copy rather than only to data."""
        from app.services.robot import layouts

        titles = (
            wording.OFFLINE_TITLE,
            wording.ERROR_TITLE,
            wording.PRIVACY_TITLE,
            wording.SETUP_TITLE,
            *wording.PRESENTATION_TITLES.values(),
        )
        for title in titles:
            assert len(title) <= layouts.TITLE_MAX, title

        bodies = (
            wording.OFFLINE_BODY,
            wording.ERROR_WIFI,
            wording.ERROR_GENERIC,
            wording.PRIVACY_BODY,
            wording.SLEEP_BODY,
            wording.SETUP_BODY,
            wording.USE_THE_APP,
            wording.MESSAGE_CONTINUE,
            wording.ASSISTANT_CONTINUE,
        )
        for body in bodies:
            assert len(body) <= layouts.BODY_MAX, body

    def test_every_generated_safety_line_fits_a_status_card(self):
        """The lines that matter most are the ones that must not be clipped."""
        from app.services.robot import layouts

        lines = [
            *wording.emergency_lines(
                alert_labels=("Ayesha", "Bilal"),
                calling_configured=False,
                has_contacts=True,
            ),
            *wording.emergency_cancelled_lines(),
            *wording.monitoring_lines(ends_at=None, zone="UTC"),
            *wording.safety_check_lines(name="Ada", seconds=90),
        ]
        for line in lines:
            assert len(line) <= layouts.LINE_MAX, line
