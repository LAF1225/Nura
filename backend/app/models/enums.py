"""Domain value sets (PRD 1, sections 17, 20, 31 and 34).

Defined once and reused by the models (as database CHECK constraints) and by
the API schemas (as validation), so the database and the API can never drift
apart on what counts as a valid value.

These are plain tuples rather than PostgreSQL ENUM types on purpose: adding a
value to a native enum needs a migration with ``ALTER TYPE``, whereas a CHECK
constraint is straightforward to replace and easy to read in psql.
"""

#: Who the account holder is setting Nura up for (PRD 1, section 17).
SETUP_MODES = ("self", "assisted")

#: Onboarding state machine (PRD 1, section 31). Order matters: it defines
#: both progression and where a partially-onboarded user resumes.
#:
#: PRD 1 ends at ``ready_for_pairing``. PRD 2 adds ``robot_connected``, reached
#: once a robot the account owns has been claimed and seen online. It is not
#: ``onboarding_complete``: detailed setup in later PRDs still follows
#: (PRD 2, section 41).
ONBOARDING_STATUSES = (
    "not_started",
    "authenticated",
    "setup_mode_selected",
    "basic_profile_complete",
    "preferences_complete",
    "consent_complete",
    "ready_for_pairing",
    "robot_connected",
    "onboarding_complete",
)

#: The last status PRD 1 is responsible for reaching.
ONBOARDING_FINAL_STATUS_PRD1 = "ready_for_pairing"

#: Whether a robot is linked to an account (PRD 2, section 31). The PRD's
#: "claim pending" stage is an unconsumed provisioning session rather than a
#: device row, so a device row only exists once a robot has actually reached
#: the backend. ``unclaimed`` is reserved for a future ownership release.
DEVICE_PROVISIONING_STATUSES = ("unclaimed", "claimed")

#: Derived from heartbeats on every read, never stored (PRD 2, section 34).
DEVICE_CONNECTION_STATUSES = ("unknown", "online", "offline")

#: How an account relates to a profile (PRD 1, section 34). Still deliberately
#: just these two, and PRD 9 did not add a third.
#:
#: A caregiver is **not** an ``account_profile_roles`` row. Every profile-scoped
#: route in PRD 0-8 authorizes through this join (``deps.get_owned_profile``),
#: so adding ``caregiver`` here would have silently handed caregivers the whole
#: health record, every symptom photo and every doctor report on the day PRD 9
#: shipped. Caregiver access is a separate relationship with its own per-category
#: permissions and its own narrower routes -- see
#: ``CAREGIVER_PERMISSION_KEYS`` and ``docs/architecture/caregiver-and-family.md``.
PROFILE_ROLES = ("self", "setup_helper")

#: Privacy-conscious alternative to a date of birth (PRD 1, section 20).
AGE_RANGES = (
    "under_18",
    "18_29",
    "30_44",
    "45_59",
    "60_74",
    "75_plus",
    "prefer_not_to_say",
)

#: How someone says they are feeling in the daily check-in (PRD 3, sections 10
#: and 14). Three plain options and nothing else: this is a wellbeing prompt,
#: not symptom tracking, and no clinical meaning is attached to any of them.
WELLBEING_LEVELS = ("good", "okay", "not_great")

#: --- the health record (PRD 4) ---------------------------------------------

#: Where a health record came from (PRD 4, section 32). Everything written in
#: PRD 4 is \`user\`: there is no caregiver or import path yet, and the API sets
#: this itself rather than trusting a client, so a record can never claim a
#: provenance it does not have.
RECORD_SOURCES = ("user", "caregiver", "clinician_import", "system_import")

#: Where a condition stands (PRD 4, section 9). \`uncertain\` is deliberately
#: present: people are often told "possibly X", and forcing that into
#: "active" would overstate it.
CONDITION_STATUSES = ("active", "resolved", "historical", "uncertain")

#: How a medication is taken (PRD 4, section 10).
MEDICATION_FORMS = (
    "tablet",
    "capsule",
    "liquid",
    "injection",
    "inhaler",
    "cream",
    "other",
)

#: What someone is allergic to (PRD 4, section 12).
ALLERGY_TYPES = ("medication", "food", "environmental", "other")

#: How bad a reaction is -- as the *user* described it. Nura never infers this
#: (PRD 4, section 12).
ALLERGY_SEVERITIES = ("mild", "moderate", "severe", "unknown")

#: What a medical note is for (PRD 4, section 16).
MEDICAL_NOTE_CATEGORIES = (
    "general",
    "important",
    "accessibility",
    "care_instruction",
    "other",
)

#: Blood groups, plus the two answers that are not a group (PRD 4, section 15).
#: "I don't know" and "I'd rather not say" are real answers, and storing them
#: is better than leaving the field empty and guessing which was meant.
BLOOD_TYPES = (
    "A+",
    "A-",
    "B+",
    "B-",
    "AB+",
    "AB-",
    "O+",
    "O-",
    "unknown",
    "prefer_not_to_say",
)

#: Progress through the gradual health setup (PRD 4, section 18). Unlike the
#: onboarding state machine, this one is not a gate: nothing in the app is
#: blocked by an incomplete health profile.
HEALTH_PROFILE_STATUSES = ("not_started", "in_progress", "complete")

#: The sections of the health profile, in the order setup offers them
#: (PRD 4, sections 7 and 17). Used for the resume point and for the
#: completeness figure, so the two can never disagree about what counts.
HEALTH_SECTIONS = (
    "conditions",
    "medications",
    "allergies",
    "clinicians",
    "procedures",
    "blood_type",
    "medical_notes",
)

#: --- medication scheduling (PRD 5) -----------------------------------------

#: How a schedule repeats (PRD 5, section 9). Deliberately only two: "every
#: day" and "on these weekdays". Several times a day is not a third type -- it
#: is several time rows on one schedule -- and a date range is a start and an
#: end on any schedule, not a shape of its own. Tapering, sliding scales and
#: every-N-hours are out of scope (PRD 5, section 10).
SCHEDULE_TYPES = ("daily", "specific_days")

#: Where a dose stands (PRD 5, section 21). ``scheduled`` and ``snoozed`` are
#: waiting; ``taken`` and ``skipped`` are what the person recorded; ``missed``
#: is what the grace period concluded when nobody recorded anything; and
#: ``cancelled`` is a future dose withdrawn because the schedule changed. Only
#: ``cancelled`` is excluded from adherence (section 27).
DOSE_STATUSES = ("scheduled", "snoozed", "taken", "skipped", "missed", "cancelled")

#: Who recorded a dose action (PRD 5, section 17). ``app`` is the only one PRD
#: 5 produces through the app; ``robot_voice`` is produced by the future robot
#: hook, which is real and authenticated but has no hardware behind it yet
#: (sections 45 and 47). ``caregiver`` and ``system`` are reserved for later
#: PRDs and nothing writes them.
DOSE_SOURCES = ("app", "robot_voice", "caregiver", "system")

#: Why a dose was skipped (PRD 5, section 20). Recorded exactly as chosen and
#: never interpreted: Nura does not conclude anything medical from "feeling
#: unwell", and does not escalate on it (section 19).
SKIP_REASON_CODES = (
    "none",
    "feeling_unwell",
    "ran_out",
    "clinician_advised",
    "too_late",
    "other",
)

#: Where a dose sits relative to now (PRD 5, section 54). Derived on every
#: read from ``scheduled_for`` and the grace period -- never stored, for the
#: same reason a robot's connection status is never stored: a value that means
#: "right now" is wrong the moment it is written.
DOSE_WINDOWS = ("upcoming", "due", "overdue", "completed")


#: --- symptoms (PRD 6) ------------------------------------------------------

#: Where a symptom episode stands (PRD 6, section 10). ``recurring`` is an
#: episode of something that has happened before -- active, with a link back to
#: the bout it follows -- so a symptom returning never merges two separate
#: events into one (section 38). Nothing infers ``resolved``: only the user
#: saying so sets it.
SYMPTOM_EPISODE_STATUSES = ("active", "resolved", "recurring", "historical")

#: The two statuses that mean "this is going on now". Used by the active list,
#: the Today card and the summary, so they can never disagree.
SYMPTOM_ACTIVE_STATUSES = ("active", "recurring")

#: How the symptom has changed since last time (PRD 6, section 23). ``unsure``
#: is a real answer and is stored as one rather than left blank, because "I
#: don't know" and "I didn't say" are different things.
SYMPTOM_CHANGE_STATES = ("improving", "same", "worsening", "unsure")

#: How a symptom record was captured (PRD 6, section 57). PRD 6's production
#: flows write only the first two: the manual form and the in-app guided
#: conversation. The other three are reserved so a later PRD adds a writer
#: rather than re-deciding the vocabulary, and nothing writes them today --
#: in particular there is no speech recognition anywhere in this system.
SYMPTOM_SOURCES = (
    "manual_app",
    "guided_app",
    "robot_voice_future",
    "caregiver_future",
    "import_future",
)

#: The sources PRD 6 will actually accept from a client. A request claiming to
#: be a future robot's voice is refused rather than stored (section 57).
SYMPTOM_SOURCES_ALLOWED = ("manual_app", "guided_app")

#: Image types a symptom photo may be (PRD 6, section 34). Checked against the
#: bytes as well as the declared type, so a mislabelled upload is refused.
#: Nothing looks *at* these images: PRD 6 section 32 rules out any analysis.
SYMPTOM_PHOTO_CONTENT_TYPES = ("image/jpeg", "image/png", "image/heic", "image/heif")

#: --- appointments and doctor reports (PRD 7) --------------------------------

#: What kind of appointment it is (PRD 7, section 6). Chosen by the user from a
#: short list, because a free-text "type" is a filter nobody can build on --
#: and ``other`` is there so the list never has to be argued about.
APPOINTMENT_TYPES = (
    "primary_care",
    "specialist",
    "therapy",
    "physiotherapy",
    "dentist",
    "lab",
    "imaging",
    "other",
)

#: Where an appointment stands (PRD 7, section 7). ``missed`` is only ever set
#: by the user saying so: nothing concludes from a passing timestamp that
#: somebody did not attend, because the commonest reason an appointment is not
#: marked completed is that nobody opened the app (section 7).
APPOINTMENT_STATUSES = ("scheduled", "completed", "cancelled", "missed")

#: The one status that means "still ahead of us". A tuple rather than a bare
#: string so the upcoming list, the Today card and Important Today cannot
#: disagree about what counts as upcoming.
APPOINTMENT_OPEN_STATUSES = ("scheduled",)

#: How far preparation has got (PRD 7, sections 6 and 10). Maintained by the
#: server from what actually exists -- questions, and a generated report -- so
#: it can never claim a report that is not there. See
#: ``services.appointments.appointments.preparation_state``.
APPOINTMENT_PREPARATION_STATUSES = ("not_started", "in_progress", "complete")

#: Where a generated report stands (PRD 7, section 30). ``pending`` exists for
#: the moment between the snapshot being written and the PDF being stored; a
#: row that never gets past it is ``failed``, and neither is ever offered for
#: export.
REPORT_STATUSES = ("pending", "ready", "failed")

#: The sections a user may put in a report (PRD 7, section 25). Symptoms are
#: not here: they are selected individually by episode, because PRD 7 section
#: 15 forbids Nura deciding which symptom matters more -- and a single
#: "symptoms" switch would make that decision on the user's behalf.
REPORT_SECTIONS = (
    "conditions",
    "allergies",
    "procedures",
    "blood_type",
    "medications",
    "adherence",
    "daily_checkins",
    "medical_notes",
    "questions",
)

#: How the report period was chosen (PRD 7, section 14). Stored alongside the
#: dates so a report can say *why* it covers what it covers, and so
#: "since my last visit" falling back to 30 days is visible rather than silent.
REPORT_PERIOD_PRESETS = ("since_last_visit", "7_days", "30_days", "90_days", "custom")

#: --- the Nura assistant (PRD 8) ---------------------------------------------

#: Who said a line in a conversation (PRD 8, section 7). ``system`` and
#: ``tool`` rows are stored because a conversation nobody can replay exactly is
#: not a record of anything -- but they never leave the server (section 7).
CONVERSATION_MESSAGE_ROLES = ("user", "assistant", "system", "tool")

#: The two roles the app is ever shown (PRD 8, section 7). Filtering here
#: rather than at each route means a new reader cannot forget the rule.
CONVERSATION_VISIBLE_ROLES = ("user", "assistant")

#: What kind of line it is. ``notice`` is Nura saying something the product
#: decided rather than the model -- "emergency escalation is not set up yet"
#: (section 39) -- and is stored as its own type so it is never mistaken for
#: generated text.
CONVERSATION_MESSAGE_TYPES = ("text", "tool_call", "tool_result", "notice")

#: Where a message came in from (PRD 8, section 71). PRD 8 produces only the
#: first: there is no speech recognition in this app and no robot microphone.
#: The rest are reserved so a later PRD adds a writer rather than reopening
#: the vocabulary -- the same approach PRD 6 took for symptom sources.
CONVERSATION_MESSAGE_SOURCES = (
    "mobile_text",
    "mobile_voice",
    "robot_voice_future",
    "system_proactive",
)

#: The only source PRD 8 accepts from a client (section 71). A request
#: claiming to be a robot's voice is refused rather than stored.
CONVERSATION_MESSAGE_SOURCES_ALLOWED = ("mobile_text",)

#: What Nura remembers, by kind (PRD 8, section 41). Note what is *not* here:
#: there is no "health" category, because section 40 is explicit that medical
#: records are structured health data and not memory.
ASSISTANT_MEMORY_CATEGORIES = (
    "preferences",
    "communication",
    "routine",
    "personal_context",
    "assistant_behavior",
)

#: How a memory came to exist (PRD 8, sections 42 and 46). Both need the user
#: to say yes: ``conversation`` means Nura suggested it and they pressed
#: Remember, never that it saved something quietly.
ASSISTANT_MEMORY_SOURCES = ("user", "conversation")

#: Tone presets (PRD 8, section 22). Tone only: section 24 forbids any of them
#: changing what Nura will and will not say about health.
PERSONALITY_PRESETS = ("gentle", "friendly", "focused", "professional")

#: The scale every personality dial uses (PRD 8, section 23). Three named
#: steps rather than 0-100, and the same three for all five dials, because
#: section 23 asks for one consistent UI and a three-way choice is something a
#: screen reader can announce and a shaking hand can hit -- which a 101-point
#: slider is not (section 83).
PERSONALITY_LEVELS = ("low", "medium", "high")

#: The five dials themselves (PRD 8, section 23), in the order the screen
#: shows them.
PERSONALITY_TRAITS = (
    "warmth",
    "humour",
    "talkativeness",
    "proactivity",
    "reminder_firmness",
)

#: How much Nura says (PRD 8, section 30). Affects length only -- section 30
#: is explicit that it must never remove safety information, which is why
#: verbosity is applied to the tone instructions and never to the guardrails.
VERBOSITY_LEVELS = ("concise", "balanced", "detailed")

#: How fast a spoken reply is read out (PRD 8, section 29). Stored now, used
#: when there is something to speak with.
SPEAKING_SPEEDS = ("slow", "normal", "fast")

#: The curated voice set (PRD 8, section 28). Named for how they sound rather
#: than for a gender, because section 28 rules out tying personality to gender
#: stereotypes and a name like "female voice 2" does exactly that.
ASSISTANT_VOICES = ("calm", "clear", "warm", "bright")

#: How much Nura speaks first (PRD 8, section 34).
PROACTIVITY_LEVELS = ("off", "low", "medium", "high")

#: The modes PRD 8 implements (section 65). ``safety`` and ``emergency`` are
#: named in the PRD as future modes and are deliberately absent: a mode the
#: app can select but nothing acts on would be a promise Nura cannot keep.
ASSISTANT_MODES = ("normal", "focus", "sleep", "privacy")

#: How one reply was handled (PRD 8, sections 37, 39 and 80; PRD 10, section
#: 43). Derived per message from deterministic checks, recorded on the message
#: so a conversation can be read back as it was answered, and never stored as a
#: setting -- serious mode is something a moment is, not something a user is.
#:
#: ``emergency_active`` is PRD 10's addition and the only one of the four that
#: depends on something outside the message: a safety event that is live right
#: now. PRD 8 deliberately left it out, on the grounds that a mode nothing acts
#: on is a promise Nura cannot keep; PRD 10 section 43 builds the thing that
#: acts on it, so the value arrives with its behaviour rather than ahead of it.
SAFETY_MODES = ("normal", "serious", "emergency_unconfigured", "emergency_active")

#: The proactive prompts Nura can raise in the app (PRD 8, section 35). Every
#: one of them is a fact the app already holds; there is no entry here for
#: anything Nura would have to conclude (section 35).
ASSISTANT_PROMPT_KINDS = (
    "appointment_preparation",
    "daily_checkin",
    "medication_supply",
)

#: Appearance options, already established in PRD 0.
THEMES = ("system", "light", "dark")


def sql_in_list(values: tuple[str, ...]) -> str:
    """Renders a tuple as a SQL ``IN`` list for use in a CHECK constraint."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"({quoted})"


#: --- caregivers and family communication (PRD 9) -----------------------------

#: What a caregiver is *called* (PRD 9, section 5). Descriptive only: section 10
#: is explicit that a role grants nothing, and section 54 that changing one must
#: not widen access. Nothing in the authorization path reads this column -- it is
#: there so a list of three caregivers is legible, and that is all.
CAREGIVER_ROLES = (
    "primary_caregiver",
    "family",
    "caregiver",
    "emergency_contact",
    "other",
)

#: Where a caregiver relationship stands (PRD 9, section 5). ``pending`` is an
#: invitation that has been created and not yet answered: PRD 9 section 79
#: allows the invitation to live inside the relationship row, and it does, so
#: accepting is a status change rather than a copy between two tables.
CAREGIVER_RELATIONSHIP_STATUSES = (
    "pending",
    "active",
    "declined",
    "revoked",
    "expired",
)

#: The one status that grants anything. A tuple of one, so the permission check,
#: the caregiver list and the supported-profile list cannot disagree about what
#: "still a caregiver" means (sections 9 and 52).
CAREGIVER_ACTIVE_STATUSES = ("active",)

#: The categories a caregiver can be granted, one at a time (PRD 9, section 6).
#: Section 7 forbids a single "can see everything" flag, and there is no column
#: anywhere that could act as one.
CAREGIVER_PERMISSION_KEYS = (
    "medications",
    "appointments",
    "symptoms",
    "reports",
    "safety_alerts",
    "communication",
    "routines",
    "general_health_summary",
)

#: Permissions that exist but have nothing behind them yet.
#:
#: **Empty, as of PRD 12.** The history is worth keeping, because the shape of
#: this tuple is how this codebase has told the truth about a half-built
#: permission twice now:
#:
#: ``safety_alerts`` left it in PRD 10. PRD 9 section 94 said the key could
#: exist before its event source did and warned against fabricating one; PRD 10
#: built the source, so the permission began unlocking real in-app safety
#: alerts and a caregiver's view of the events they cover (PRD 10, sections 31,
#: 50 and 83).
#:
#: ``routines`` leaves it in PRD 12. Through PRD 0-11 there was no routine
#: record anywhere, so granting the permission was stored faithfully and
#: unlocked nothing, and the caregiver screens said so. PRD 12 section 12
#: builds routines, runs and steps, section 16 gives a caregiver with this key
#: the right to view and *suggest*, and section 42 is the hard edge: the
#: permission reaches routines and nothing else -- not tasks, not alarms, not
#: general reminders.
#:
#: An empty tuple is not a thing to delete. The next PRD that reserves a
#: permission before its data exists puts the key here, and every screen that
#: reads ``CareScope.usable`` keeps working.
CAREGIVER_PERMISSIONS_WITHOUT_A_SOURCE: tuple[str, ...] = ()

#: What a suggestion is about (PRD 9, sections 22 and 100).
CAREGIVER_SUGGESTION_CATEGORIES = ("medications", "appointments", "routines")

#: The changes a caregiver may propose (PRD 9, section 85).
#:
#: This tuple is the whole list, and what is absent is the point: section 85
#: forbids ``change_medication_dose``, ``delete_condition`` and
#: ``change_diagnosis``, and the way to guarantee a caregiver cannot propose one
#: is not to validate the request but to have no action type that could carry it.
#: ``services.caregivers.suggestions.ACTIONS`` has one entry per name here and
#: nothing else can be stored, because the CHECK constraint is built from this.
#:
#: The last three arrived with PRD 12, which is the "new action type in one
#: place" this comment used to promise. PRD 9 section 85 named ``add_routine``
#: and ``change_routine`` and they were left out because there was nothing to
#: add a routine to; PRD 12 section 16 asks for exactly these three, and each
#: one approves through the ordinary routine service (PRD 12, section 17).
#:
#: What is still absent matters as much. There is no ``add_task``, no
#: ``create_reminder`` and no ``set_alarm``: PRD 12 section 42 keeps general
#: tasks, alarms and reminders private to the primary user, and the way to be
#: sure a caregiver cannot reach into somebody's task list is for there to be
#: no action type that could carry the request.
CAREGIVER_SUGGESTION_ACTION_TYPES = (
    "change_medication_reminder_time",
    "pause_medication_reminder",
    "resume_medication_reminder",
    "add_appointment",
    "change_appointment_time",
    "add_routine",
    "change_routine_time",
    "pause_routine",
)

#: What kind of thing a suggestion points at (PRD 9, section 22). ``appointment``
#: appears without a target id on ``add_appointment``, because the thing being
#: proposed does not exist yet -- and so does ``routine`` on ``add_routine``,
#: for the same reason (PRD 12, section 16).
CAREGIVER_SUGGESTION_TARGET_TYPES = (
    "medication_schedule",
    "appointment",
    "routine",
)

#: Where a suggestion stands (PRD 9, section 22). ``cancelled`` is the caregiver
#: withdrawing their own suggestion; ``expired`` is reserved and nothing sets it,
#: because PRD 9 names no expiry period for a suggestion and a silently
#: disappearing care request is worse than an old one.
CAREGIVER_SUGGESTION_STATUSES = (
    "pending",
    "approved",
    "declined",
    "expired",
    "cancelled",
)

#: The statuses that still need the primary user to do something.
CAREGIVER_SUGGESTION_OPEN_STATUSES = ("pending",)

#: What kind of line a family message is (PRD 9, section 31).
FAMILY_MESSAGE_TYPES = ("text", "photo", "check_in", "system")

#: The types a client may actually send. ``photo`` is reserved: PRD 9 section 33
#: makes photo messages optional and requires private storage, signed access and
#: size limits if they are built -- the private-storage half already exists from
#: PRD 6, the upload route and picker flow do not, and a half-built attachment
#: is worse than none. ``system`` is written by the server only, for the lines
#: nobody typed (section 31).
FAMILY_MESSAGE_TYPES_ALLOWED = ("text", "check_in")

#: The quick check-ins a *primary user* may send (PRD 9, section 35).
#:
#: Stored as a code with the sentence rendered from it, for the PRD 7 reason:
#: one module writes the prose, so the wording can be fixed or translated
#: without rewriting rows -- and a check-in is never free text that could carry
#: something the sender did not mean to put in a care thread.
FAMILY_CHECK_IN_CODES_FROM_USER = ("im_okay", "not_great", "please_call_me", "need_help")

#: The quick check-ins a *caregiver* may send (PRD 9, section 36). A different
#: list, because "I'm okay" is not a thing a caregiver sends and section 36 asks
#: only for the asking kind. Section 36 also rules out making these compulsory:
#: nothing anywhere requires a reply, and no absence of one is recorded.
FAMILY_CHECK_IN_CODES_FROM_CAREGIVER = ("how_are_you", "thinking_of_you")

#: Every check-in code, for the CHECK constraint.
FAMILY_CHECK_IN_CODES = (
    FAMILY_CHECK_IN_CODES_FROM_USER + FAMILY_CHECK_IN_CODES_FROM_CAREGIVER
)

#: The caregiver actions worth keeping a record of (PRD 9, section 50).
#:
#: Note what is not here: there is no event for *reading* anything. Section 49
#: says not to notify the user every time a caregiver views a permitted category
#: and section 50 says not to build a feed of read operations -- a care app that
#: logs every glance is the surveillance experience section 2 rules out.
CAREGIVER_AUDIT_EVENT_TYPES = (
    "invited",
    "accepted",
    "declined",
    "permission_changed",
    "role_changed",
    "suggestion_created",
    "suggestion_approved",
    "suggestion_declined",
    "suggestion_cancelled",
    "relationship_revoked",
    "emergency_contact_added",
    "emergency_contact_updated",
    "emergency_contact_removed",
    "emergency_contact_priority_changed",
)

#: Who did the thing an audit row records. The actor is always an account, but
#: which *side* they were acting from is worth keeping: "the primary user
#: changed a permission" and "a caregiver withdrew a suggestion" are different
#: events even when the row otherwise looks the same.
CAREGIVER_AUDIT_ACTOR_KINDS = ("primary_user", "caregiver", "system")

#: Where an audio call is (PRD 9, section 40). Reported by an
#: ``AudioCallProvider``; nothing stores one, because no call has ever been
#: placed -- see ``services.caregivers.calls``.
AUDIO_CALL_STATES = ("idle", "ringing", "connecting", "active", "ended", "failed")

#: What a *caregiver* can be notified about, per supported person (PRD 9,
#: section 48). ``safety_alerts`` is here and defaults to off, because section 48
#: says not to activate safety alerts until PRD 10 exists.
CAREGIVER_NOTIFICATION_KEYS = (
    "messages",
    "appointment_updates",
    "suggestion_outcomes",
    "safety_alerts",
)

#: What a *primary user* can be notified about (PRD 9, section 48). Section 48
#: also requires an approval request to stay visible in the app even when every
#: one of these is off, which is why none of them gates the pending-suggestion
#: list.
CARE_NOTIFICATION_KEYS = (
    "caregiver_messages",
    "suggestion_requests",
    "appointment_suggestions",
    "routine_suggestions",
)

#: --- safety monitoring and SOS (PRD 10) --------------------------------------

#: Where a monitoring session stands (PRD 10, section 9). ``expired`` is the
#: duration running out and ``ended`` is somebody stopping it -- different
#: facts, and section 61 forbids quietly extending one into the other.
#: ``error`` exists so a session can never be left claiming to watch over
#: somebody when the thing watching has failed (section 127).
SAFETY_MONITORING_STATUSES = ("active", "ended", "cancelled", "expired", "error")

#: The one status that means somebody is being watched over. A tuple of one, so
#: the status endpoint, the passive-trigger gate and the worker cannot disagree
#: about what "monitoring is on" means (sections 22 and 61).
SAFETY_MONITORING_ACTIVE_STATUSES = ("active",)

#: How long monitoring was asked for (PRD 10, section 5). Locked presets, plus
#: ``custom``: section 5 says not to invent a hidden monitoring period, and the
#: way to be sure is that every session records which of these the person
#: chose, not merely when it happens to end.
SAFETY_MONITORING_DURATION_MODES = (
    "30_minutes",
    "1_hour",
    "until_bedtime",
    "until_turned_off",
    "custom",
)

#: The one mode with no end (section 5). Named rather than inferred from a null
#: ``ends_at``, because "runs until turned off" and "we failed to work out when
#: this ends" must never look the same.
SAFETY_MONITORING_OPEN_ENDED_MODES = ("until_turned_off",)

#: What started a session (PRD 10, section 10). Only the first is accepted
#: today; the rest are reserved so a later PRD adds a writer rather than
#: reopening the vocabulary -- the approach PRD 6 took to symptom sources.
#:
#: ``caregiver_future`` is reserved and deliberately not allowed: section 10
#: says caregivers must not silently activate monitoring for somebody, and
#: section 58 repeats it for the caregiver assistant.
SAFETY_MONITORING_SOURCES = (
    "mobile_app",
    "assistant_future",
    "robot_future",
    "caregiver_future",
)

#: The sources PRD 10 will actually accept. A request claiming to be anything
#: else is refused rather than stored.
SAFETY_MONITORING_SOURCES_ALLOWED = ("mobile_app",)

#: Why a session is no longer active (PRD 10, sections 61 and 62).
#: ``superseded`` is a second session starting while one was running, which the
#: service turns into one session rather than two overlapping ones.
SAFETY_MONITORING_END_REASONS = (
    "stopped_by_user",
    "duration_reached",
    "superseded",
    "system_error",
)

#: How long the user has to answer a safety check, in seconds (section 7).
#: A fixed list rather than a free number: these are the options the screen
#: offers, and a session storing 7 seconds would be a session nobody chose.
SAFETY_RESPONSE_TIMEOUT_SECONDS = (15, 30, 45, 60, 90)

#: Section 7's default.
DEFAULT_SAFETY_RESPONSE_TIMEOUT_SECONDS = 45

#: The second prompt's own, shorter wait (section 8). Section 8 asks for the
#: exact timing to be documented, so it is a named constant rather than a
#: fraction computed at the call site: **20 seconds, always**, whatever the
#: first timeout was. The first wait is for somebody who may be busy; the
#: second is for somebody who has already not answered once.
SECOND_PROMPT_TIMEOUT_SECONDS = 20

#: What happened, in words that describe rather than diagnose (section 16).
#:
#: **The word ``possible`` is mandatory on every sensor-observed category** and
#: it is enforced here rather than hoped for: section 16 requires it, section 52
#: forbids definitive labels like "seizure detected", and the test for it reads
#: this tuple and asserts that every type a detector may emit starts with
#: ``possible_``. Nura may say what it noticed. It may never say what it means.
SAFETY_EVENT_TYPES = (
    "manual_sos",
    "possible_fall",
    "possible_prolonged_immobility",
    "possible_vomiting",
    "possible_seizure_like_activity",
    "possible_distress",
    "call_for_help",
    "test_event",
)

#: The passive ones -- something observed rather than something asked for.
#: These need monitoring to be active (section 22): Nura does not watch while
#: Safety Monitoring is off, so an event arriving then is refused rather than
#: quietly processed.
SAFETY_EVENT_TYPES_REQUIRING_MONITORING = (
    "possible_fall",
    "possible_prolonged_immobility",
    "possible_vomiting",
    "possible_seizure_like_activity",
    "possible_distress",
)

#: The ones that skip the countdown entirely (sections 12, 14 and 26). Somebody
#: asking for help is not a signal that needs confirming.
SAFETY_EVENT_TYPES_IMMEDIATE = ("manual_sos", "call_for_help")

#: What an authenticated *user* may create from the app (sections 12 and 14).
#: ``test_event`` is absent on purpose: section 18 forbids a production-visible
#: fake emergency control, and the simulation harness is a script and a test
#: fixture rather than a route anybody's phone can reach.
SAFETY_EVENT_TYPES_FROM_USER = ("manual_sos", "call_for_help")

#: Where the trigger came from (section 17). Everything ``_future`` is reserved
#: and refused: there is no robot sensor, camera or microphone anywhere in this
#: system, and a stored event claiming one would be a lie about provenance.
SAFETY_TRIGGER_SOURCES = (
    "mobile_manual",
    "mobile_voice",
    "robot_sensor_future",
    "robot_camera_future",
    "robot_audio_future",
    "developer_simulation",
)

#: What a client may claim. ``developer_simulation`` is here because the
#: device-trigger contract is how the harness exercises it -- and section 17
#: says it must never appear in production UI, which is a statement about the
#: app, enforced by the app having no control that sends it and by the backend
#: refusing it outside development.
SAFETY_TRIGGER_SOURCES_ALLOWED = ("mobile_manual", "developer_simulation")

#: Where a safety event is, right now (PRD 10, section 11).
#:
#: The PRD's state machine names both a lifecycle and an outcome; they are kept
#: apart here. ``status`` is where the event *is* and is what the locking in
#: section 78 transitions; how escalation *went* is
#: ``SAFETY_ESCALATION_OUTCOMES`` on the same row. Folding the two together
#: would mean a row that cannot say "escalation finished partially and then the
#: user said they were fine", which section 126 requires it to be able to say.
SAFETY_EVENT_STATUSES = (
    "checking_user",
    "second_prompt",
    "escalating",
    "escalated",
    "resolved",
    "cancelled",
)

#: Statuses where something is still happening and the app shows it. A second
#: SOS while one of these is live folds into the existing event rather than
#: starting a parallel one (section 77).
SAFETY_EVENT_LIVE_STATUSES = (
    "checking_user",
    "second_prompt",
    "escalating",
    "escalated",
)

#: Statuses where a deadline is ticking and the user can still answer.
SAFETY_EVENT_AWAITING_RESPONSE_STATUSES = ("checking_user", "second_prompt")

#: The statuses that put the app into emergency mode (section 43). Escalation
#: has begun; non-essential UI goes away until the event is resolved.
SAFETY_EVENT_EMERGENCY_STATUSES = ("escalating", "escalated")

#: What the user said (sections 23, 24 and 25). Two answers and a third that is
#: not an answer to "are you okay" at all -- ``false_alarm`` is the optional
#: dismissal in section 23, which resolves the event the same way ``im_okay``
#: does and additionally labels it.
SAFETY_USER_RESPONSES = ("im_okay", "need_help", "false_alarm")

#: How an event finished (section 46). ``resolved_after_contact`` is the one
#: nothing sets automatically: it means a person established the user was all
#: right, and no code in this system can know that.
SAFETY_EVENT_RESOLUTIONS = (
    "user_confirmed_ok",
    "help_requested",
    "no_response_escalated",
    "false_alarm",
    "cancelled_by_user",
    "resolved_after_contact",
    "test_event",
    "system_error",
)

#: Why it was a false alarm, if the user says (section 47). Optional, stored as
#: a code, and section 48 is explicit that none of this trains anything.
SAFETY_FALSE_POSITIVE_REASONS = (
    "normal_movement",
    "sensor_error",
    "user_testing",
    "other",
)

#: The ways an escalation could reach somebody (section 34). Three of the four
#: are named for a future that does not exist yet, and the suffix says so.
SAFETY_ESCALATION_CHANNELS = ("in_app", "push", "sms_future", "voice_call_future")

#: The channels that actually work in this build (sections 34 and 35). Exactly
#: one: an in-app alert record. Section 34 says only to report a channel as
#: available when a real provider exists, so this tuple is what the capability
#: endpoint is built from -- not a guess, and not a configuration flag somebody
#: could set without wiring a provider behind it.
SAFETY_ESCALATION_CHANNELS_AVAILABLE = ("in_app",)

#: What became of one attempt to reach one recipient (section 33).
#:
#: ``attempted`` and ``delivered`` are deliberately different: section 38 says
#: an alert record is not proof that anybody saw it, and nothing in this system
#: may move an attempt to ``delivered`` without a provider confirming it.
#: ``not_configured`` is the honest answer for a channel with nothing behind it,
#: and it is a first-class outcome rather than a failure -- a build that cannot
#: send an SMS has not failed to send one.
SAFETY_ESCALATION_ATTEMPT_STATUSES = (
    "pending",
    "attempted",
    "delivered",
    "failed",
    "skipped",
    "not_configured",
)

#: How the whole escalation went (section 41). Reported to the user as facts
#: (section 42): "an in-app alert was created for Ayesha; calling is not
#: configured", never "Ayesha has been contacted".
SAFETY_ESCALATION_OUTCOMES = (
    "complete",
    "partial",
    "failed",
    "no_contacts",
    "providers_not_configured",
    "cancelled",
)

#: What the app is told this build can actually do (sections 64, 65 and 106).
#: The UI is driven by this rather than by what the screens were written to
#: assume, which is what stops a Call button existing for a call that cannot
#: happen.
SAFETY_CAPABILITY_KEYS = (
    "manual_sos",
    "in_app_safety_checks",
    "caregiver_in_app_alerts",
    "push_delivery",
    "sms_delivery",
    "audio_calling",
    "robot_detection",
)

#: ``not_configured`` means nobody wired a provider; ``not_connected`` means
#: there is one and it is not reachable right now. A robot that has never
#: existed is ``not_connected`` rather than ``unavailable``, because the honest
#: statement is "not connected yet" (section 66).
SAFETY_CAPABILITY_STATES = ("available", "not_configured", "not_connected", "unavailable")

#: What is worth recording (PRD 10, section 89), and nothing beyond it.
#:
#: Section 90 keeps this minimal: no health record, no symptom history, no
#: message text. Every row here is the shape of what happened -- a transition, a
#: channel, an outcome -- and ``services.safety.audit`` is the only writer.
SAFETY_AUDIT_EVENT_TYPES = (
    "monitoring_started",
    "monitoring_stopped",
    "monitoring_expired",
    "trigger_received",
    "user_prompted",
    "second_prompt_sent",
    "user_responded_ok",
    "user_requested_help",
    "response_timeout",
    "escalation_started",
    "escalation_finished",
    "alert_created",
    "alert_acknowledged",
    "provider_attempted",
    "provider_confirmed",
    "provider_failed",
    "event_cancelled",
    "event_resolved",
    "false_alarm_marked",
)

#: Who caused an audit row. ``device`` is a robot acting on its own token and
#: ``system`` is the maintenance worker -- a timeout has no person behind it,
#: and recording one would be the first untrue thing in the trail.
SAFETY_AUDIT_ACTOR_KINDS = ("primary_user", "caregiver", "device", "system")


#: --- robot display and companion experience (PRD 11) -------------------------

#: The wire version of the presentation envelope (section 116). Bumped when a
#: field changes meaning, not when one is added: a device that does not
#: recognise the version refuses the envelope rather than guessing at it.
ROBOT_PRESENTATION_PROTOCOL_VERSION = 1

#: What the robot is *being* at a moment (section 4), mapped onto the mode
#: system PRD 8 already has rather than competing with it.
#:
#: ``ASSISTANT_MODES`` is the user's setting -- normal, focus, sleep, privacy --
#: and four of these are that setting seen from the robot's side
#: (``normal`` becomes ``companion``). The other six are not settings at all:
#: they are facts about the moment, derived on every read by
#: ``services.robot.modes``. Nothing stores a robot mode, for the same reason
#: PRD 10 does not store emergency mode -- a column meaning "right now" is
#: wrong the moment it is written.
ROBOT_PRESENTATION_MODES = (
    "companion",
    "information",
    "focus",
    "sleep",
    "privacy",
    "safety",
    "emergency",
    "offline",
    "setup",
    "error",
)

#: The whole face vocabulary (section 27). Nine, and deliberately not more:
#: section 28 forbids expression that implies medical judgement, so there is no
#: ``worried``, no ``alarmed`` and no ``sad`` for a screen to reach for when a
#: symptom is severe. Serious moments use ``information`` mode instead.
ROBOT_FACE_STATES = (
    "idle",
    "listening",
    "thinking",
    "speaking",
    "happy",
    "concerned",
    "sleeping",
    "privacy",
    "offline",
)

#: What one queued presentation is for (PRD 11, section 15).
#:
#: The last four are PRD 12's (section 30), and they go through this same queue
#: because section 30 says not to create a second robot transport. Every layer
#: that knows a type name was updated with them: the priority table below, the
#: expiry table in ``services.robot.queue``, the titles in
#: ``services.robot.wording``, the simulator, the firmware's
#: ``presentation_protocol.h``, and the app's own parser.
ROBOT_PRESENTATION_TYPES = (
    "face_state",
    "info_card",
    "medication_reminder",
    "appointment_reminder",
    "family_message",
    "assistant_response",
    "safety_check",
    "safety_status",
    "emergency_status",
    "system_status",
    "setup_code",
    "task_reminder",
    "general_reminder",
    "alarm",
    "routine",
)

#: Where one presentation stands (section 14).
#:
#: ``sent`` means the backend handed the envelope over. ``displayed`` means the
#: device said it rendered it, and **nothing but a device acknowledgement
#: writes it** -- section 14 is explicit that returning a command is not
#: rendering it, and section 141 asks for the same thing again at completion
#: time. ``not_supported`` is a real outcome rather than a failure: a robot
#: with no screen has not failed to show a card.
ROBOT_PRESENTATION_STATUSES = (
    "queued",
    "sent",
    "acknowledged",
    "displayed",
    "completed",
    "expired",
    "failed",
    "cancelled",
    "not_supported",
)

#: Still the device's business: not finished, not given up on (section 18).
#: The queue selects within these and a duplicate build folds into one of them.
ROBOT_PRESENTATION_OPEN_STATUSES = ("queued", "sent", "acknowledged", "displayed")

#: Nothing more will happen to these.
ROBOT_PRESENTATION_TERMINAL_STATUSES = (
    "completed",
    "expired",
    "failed",
    "cancelled",
    "not_supported",
)

#: Which presentation wins when two are waiting (section 16), lowest first.
#:
#: Section 16 fixes the order of nine of the eleven types and asks only that
#: the ordering be deterministic. It is a table rather than a rule because a
#: rule would eventually be read differently by the queue and by a screen.
#:
#: The two types section 16 does not rank sit between ``safety_status`` and
#: ``medication_reminder``: a pairing code and "Nura needs attention" are both
#: about whether the robot is usable at all, so neither belongs under a
#: reminder -- and neither may outrank anything to do with safety.
#: PRD 12's four sit between the reminders PRD 11 already ranked, in the order
#: section 18 gives Today: an appointment, then a task, then a routine, then a
#: general reminder. An ``alarm`` is the one that moves up -- section 4 defines
#: it as a time-critical alert whose whole purpose is to get attention at a
#: specific time -- but it still sits *below* medication and far below anything
#: to do with safety, because section 64 asks for an emergency to preempt an
#: alarm and this is the comparison that makes it so.
ROBOT_PRESENTATION_PRIORITIES = (
    ("emergency_status", 10),
    ("safety_check", 20),
    ("safety_status", 30),
    ("setup_code", 35),
    ("system_status", 38),
    ("medication_reminder", 40),
    ("alarm", 45),
    ("appointment_reminder", 50),
    ("task_reminder", 54),
    ("routine", 56),
    ("general_reminder", 58),
    ("family_message", 60),
    ("assistant_response", 70),
    ("info_card", 80),
    ("face_state", 90),
)

#: Every type is ranked exactly once. Adding a type without a priority would
#: otherwise make the queue's ordering depend on insertion order.
assert {name for name, _ in ROBOT_PRESENTATION_PRIORITIES} == set(
    ROBOT_PRESENTATION_TYPES
)

#: The ranks, for the CHECK constraint on ``device_presentations.priority``.
#: Derived from the table above so the two can never disagree (section 120).
ROBOT_PRESENTATION_PRIORITY_BANDS = tuple(
    sorted({rank for _, rank in ROBOT_PRESENTATION_PRIORITIES})
)

#: The rank anything to do with a live safety event carries or beats. Used by
#: the preemption rule, so section 72's "personality cannot override safety"
#: is one comparison rather than a list of special cases.
ROBOT_SAFETY_PRIORITY_CEILING = 30

#: The layouts a device knows how to draw (section 37). A payload names one of
#: these; there is no free-form markup, which is section 111.
ROBOT_PRESENTATION_LAYOUTS = (
    "FACE",
    "TITLE_BODY",
    "TITLE_VALUE",
    "REMINDER",
    "MESSAGE",
    "STATUS",
    "EMERGENCY",
    "PAIRING_CODE",
)

#: Which part of the product asked for a presentation (PRD 11, section 50).
#:
#: ``daily_life`` is PRD 12's, and it covers all four of its card types rather
#: than splitting into four sources. The distinction this column draws is
#: *which part of the product*, and tasks, reminders, alarms and routines are
#: one part -- the presentation type already says which of the four a row is.
ROBOT_PRESENTATION_SOURCES = (
    "medication",
    "appointment",
    "family_message",
    "assistant",
    "safety",
    "system",
    "user",
    "daily_life",
)

#: What a device says happened (section 19). ``render_completed`` is the only
#: one that can mean a person saw something, and only the device can say it.
ROBOT_ACK_STATES = (
    "received",
    "render_started",
    "render_completed",
    "failed",
    "unsupported",
)

#: Why a presentation was withdrawn rather than shown. Separate from
#: ``failure_code`` on purpose, the way PRD 10 keeps an event's status separate
#: from how its escalation went: "the dose was taken" and "the renderer broke"
#: are different facts and a single column would blur them.
ROBOT_PRESENTATION_CANCEL_REASONS = (
    "preempted",
    "source_resolved",
    "source_cancelled",
    "superseded",
    "preference_changed",
    "capability_withdrawn",
    "device_unlinked",
)

#: Stable codes a device or the backend may record against a presentation.
#: Never a device's own error text, which could quote a payload back
#: (section 67).
ROBOT_PRESENTATION_FAILURE_CODES = (
    "render_failed",
    "unsupported_layout",
    "unsupported_capability",
    "unsupported_protocol_version",
    "no_display",
    "device_error",
)

#: What the robot can actually do (section 10). Twelve keys rather than one
#: ``robot_ready`` boolean, which section 10 rules out explicitly: a speaker
#: that was never wired and a microphone nobody has tested are different
#: facts, and a single flag is how a settings screen comes to offer both.
ROBOT_CAPABILITY_KEYS = (
    "display",
    "display_text",
    "display_animation",
    "speaker",
    "tts",
    "audio_playback",
    "microphone",
    "wake_word",
    "camera",
    "camera_detection",
    "buttons",
    "touch",
)

#: Section 10's four states, and section 91 makes the third mandatory.
#:
#: ``not_verified`` means the firmware has the driver but nothing physical has
#: been proven -- section 12's "compilation is not proof of physical function".
#: **Only a device report can produce it.** The backend cannot write
#: ``not_verified`` on its own, because the backend has no way to know that a
#: driver compiled; what it knows is whether a device has told it anything,
#: and the answer to that is ``not_connected``.
ROBOT_CAPABILITY_STATES = ("available", "unavailable", "not_verified", "not_connected")

#: Where a capability state came from. ``default`` is "nobody has said", and it
#: is the only one the backend writes by itself.
ROBOT_CAPABILITY_SOURCES = ("device_report", "self_test", "default")

#: What a card may offer (section 85). Physical buttons are not required in
#: PRD 11, and section 86 says a device reporting no input must not be sent
#: action-heavy cards -- so these are a *request* for input, honoured only
#: when the device has said it has some.
ROBOT_PRESENTATION_ACTIONS = (
    "dismiss",
    "taken",
    "snooze",
    "skip",
    "open_app",
    "acknowledge",
)

#: How much of a medication reminder the robot may show (section 22). The
#: robot's screen is in a room other people walk through, which is the whole
#: reason this exists.
ROBOT_MEDICATION_PRIVACY_LEVELS = ("full", "name_only", "private")

#: The same three levels, for daily-life content (PRD 12, section 32).
#:
#: Reused rather than redefined, which is what section 32's "add or reuse"
#: should mean: "Full / Title only / Private reminder" is the same question
#: asked about a task instead of a tablet, and two vocabularies for one idea is
#: how a settings screen ends up with two answers. A separate *preference*
#: column still exists, because somebody may well want their medication hidden
#: and their shopping list shown.
ROBOT_PRIVACY_LEVELS = ROBOT_MEDICATION_PRIVACY_LEVELS

#: What the screen does while the robot is asleep (section 31).
ROBOT_SLEEP_SCREEN_MODES = ("dim", "sleeping_face", "blank")

#: Chime categories (section 81). Defined so the presentation payload can name
#: one; no audio has ever been played by this project.
ROBOT_CHIME_KINDS = ("reminder", "message", "safety", "success", "error")


#: --- daily life: tasks, reminders, alarms and routines (PRD 12) --------------

#: Where a task stands (PRD 12, section 5).
#:
#: Four, and each is a different thing somebody meant. ``completed`` is done;
#: ``archived`` is "finished with this, keep it out of the way"; ``cancelled``
#: is "this is not happening after all". All three keep the row, because
#: section 6 asks for completion to preserve history -- a list somebody can
#: tidy without losing what they actually did is most of what makes one
#: trustworthy.
TASK_STATUSES = ("open", "completed", "archived", "cancelled")

#: The one status that still wants something from somebody.
TASK_OPEN_STATUSES = ("open",)

#: Two levels, and deliberately not four (PRD 12, section 5). Section 3 rules
#: out an overbuilt productivity suite, and a priority scheme with more rungs
#: than anybody can hold in their head is the first thing that turns a calm
#: list into one.
TASK_PRIORITIES = ("normal", "important")

#: Who put a daily-life item there (PRD 12, section 43).
#:
#: ``caregiver_suggestion`` is what an approved routine suggestion carries, so
#: section 43's "approved caregiver suggestions remain attributable" is a
#: column rather than a convention. ``import_future`` is reserved for an
#: external calendar nobody has connected -- see ``EXTERNAL_CAPABILITY_KEYS``
#: -- and nothing anywhere writes it.
DAILY_LIFE_SOURCES = ("user", "assistant", "caregiver_suggestion", "import_future")

#: The source a client may claim. The other three are set by the server from
#: *how* the write arrived -- the assistant's own tool path, a suggestion
#: approval -- so provenance is never something a request body asserts.
DAILY_LIFE_SOURCES_ALLOWED = ("user",)

#: How a general reminder repeats (PRD 12, section 7).
#:
#: Exactly the five patterns the section lists, and no recurrence grammar.
#: Section 7 says to add arbitrary recurrence only if it is thoroughly tested,
#: and an RRULE parser beside a medication engine that already works is a way
#: to break the medication engine.
REMINDER_RECURRENCES = ("one_time", "daily", "selected_days", "weekly", "monthly")

#: The recurrences that need at least one weekday to mean anything.
REMINDER_RECURRENCES_WITH_WEEKDAYS = ("selected_days", "weekly")

#: The recurrences that repeat. ``one_time`` produces one occurrence and then
#: the series is ``completed``.
REMINDER_REPEATING_RECURRENCES = ("daily", "selected_days", "weekly", "monthly")

#: Where a reminder *series* stands, as opposed to one of its occurrences.
REMINDER_STATUSES = ("active", "paused", "completed", "cancelled")

#: Series that still generate occurrences.
REMINDER_ACTIVE_STATUSES = ("active",)

#: What happened at one concrete occurrence (PRD 12, section 8).
#:
#: ``completed`` rather than ``taken``, and section 8 says why outright: do not
#: reuse medication semantics. They are different acts. A tablet that was taken
#: is a fact about somebody's health that an adherence figure counts; a
#: reminder that was dealt with is not, and nothing in this codebase scores it.
REMINDER_OCCURRENCE_STATUSES = (
    "scheduled",
    "completed",
    "dismissed",
    "snoozed",
    "missed",
    "cancelled",
)

#: Occurrences still waiting for something.
REMINDER_OCCURRENCE_OPEN_STATUSES = ("scheduled", "snoozed")

#: How an alarm repeats (PRD 12, section 10). No weekly and no monthly: an
#: alarm is a time of day on certain days, and section 10 rules out sleep-cycle
#: logic and anything else clever.
ALARM_RECURRENCES = ("one_time", "daily", "selected_days")

#: The sounds an alarm may name (PRD 12, section 10).
#:
#: Named rather than free text, so a key means the same thing on both platforms
#: and on the robot. Kept short because **no sound has ever been played by this
#: project**: the app has never run on a phone, and the robot's speaker reports
#: ``not_connected``. A key here is a choice somebody stored, never a sound
#: anybody heard (section 11).
ALARM_SOUND_KEYS = ("default", "gentle", "chime", "bell")

#: How a routine repeats (PRD 12, section 12). The same two shapes a medication
#: schedule has, for the reason section 35 gives: the recurrence and
#: time-zone discipline is PRD 5's, reused rather than decided a second time.
ROUTINE_SCHEDULE_TYPES = ("daily", "selected_days")

#: Where a routine stands. ``paused`` is section 13's pause switch and keeps
#: every run it has already produced, exactly as a paused medication schedule
#: does.
ROUTINE_STATUSES = ("active", "paused", "archived")

#: Routines that should still be producing runs.
ROUTINE_ACTIVE_STATUSES = ("active",)

#: Where one scheduled instance of a routine stands (PRD 12, section 14).
ROUTINE_RUN_STATUSES = (
    "scheduled",
    "in_progress",
    "completed",
    "skipped",
    "missed",
    "cancelled",
)

#: Runs that are still somebody's business.
ROUTINE_RUN_OPEN_STATUSES = ("scheduled", "in_progress")

#: What a step completion records (PRD 12, section 14). ``skipped`` exists so an
#: optional step can be passed over without the run claiming it was done.
ROUTINE_STEP_STATES = ("completed", "skipped")

#: What the assistant is told it can reach (PRD 12, sections 25 and 29).
#:
#: Four features that exist and three that would need a provider, in one map,
#: because the model needs one answer to "can you do that". Section 29 says the
#: model must not improvise a capability absent from the map; the way to make
#: that checkable rather than hoped for is for the map to be exhaustive.
DAILY_LIFE_CAPABILITY_KEYS = (
    "tasks",
    "reminders",
    "alarms",
    "routines",
    "weather",
    "news",
    "external_calendar",
)

#: The three that would need an outside service (PRD 12, sections 26, 27, 28).
EXTERNAL_CAPABILITY_KEYS = ("weather", "news", "external_calendar")

#: What a capability may say (PRD 12, section 25).
#:
#: ``not_configured`` is the honest answer for every external key in this
#: build, and there is no fourth state meaning "sort of". It is the rule PRD 10
#: and PRD 11 already follow: a missing integration says so, rather than
#: returning something that looks live. ``unavailable`` is reserved for a
#: provider that exists and is failing, which no provider here can be.
DAILY_LIFE_CAPABILITY_STATES = ("available", "not_configured", "unavailable")

assert set(EXTERNAL_CAPABILITY_KEYS) <= set(DAILY_LIFE_CAPABILITY_KEYS)


# --- privacy, export and deletion (PRD 13) ----------------------------------

#: The data categories PRD 13 section 11 asks to be classified, in the order
#: the Privacy & Security screen and the export manifest both use.
#:
#: One list, read by the classification document, the export builder, the
#: deletion service and the privacy summary -- so "what categories are there"
#: has one answer rather than four that drift. ``audit`` is in it because
#: section 11 names it, even though nothing exports audit rows: a category that
#: exists and is deliberately excluded is more honest than one nobody mentions.
DATA_CATEGORIES = (
    "account",
    "health",
    "assistant",
    "caregiver",
    "safety",
    "productivity",
    "device",
    "media",
    "audit",
)

#: The categories an export archive contains (PRD 13, sections 17 and 19).
#:
#: ``audit`` is the only one of the nine left out, and the manifest says so
#: rather than pretending the category is not there. An audit row records that
#: somebody's caregiver read something: it is written by the server about third
#: parties, it is the evidence trail for the access controls themselves, and
#: handing it over in a self-service archive would export other people's
#: actions along with this person's data. Section 19 asks for
#: ``excluded_categories`` precisely so a decision like that is stated.
DATA_EXPORT_CATEGORIES = (
    "account",
    "health",
    "assistant",
    "caregiver",
    "safety",
    "productivity",
    "device",
    "media",
)

#: The JSON files inside the archive, in order, as section 17 names them.
#:
#: Separate from the categories above because the two answer different
#: questions. A category is a classification (section 11) and appears in the
#: manifest; a section is a file somebody opens. ``medications`` and
#: ``symptoms`` are both ``health`` data in one file each, which is why the
#: lists are different lengths and why neither is derived from the other.
DATA_EXPORT_SECTIONS = (
    "profile",
    "health",
    "medications",
    "symptoms",
    "appointments",
    "assistant",
    "caregivers",
    "safety",
    "daily-life",
    "devices",
)

#: Where one export stands (PRD 13, section 20).
#:
#: All five exist; this build produces three of them. ``requested`` and
#: ``generating`` belong to an asynchronous implementation, and section 48 says
#: not to add a worker that is not needed -- an archive here is kilobytes of
#: JSON built inside the request, so a row is ``ready`` or ``failed`` by the
#: time anybody can read it. Keeping the other two means a later worker needs
#: no migration, which is the approach PRD 6 took to future symptom sources.
DATA_EXPORT_STATUSES = ("requested", "generating", "ready", "failed", "expired")

#: What this build can actually store (PRD 13, section 20).
DATA_EXPORT_STATUSES_ALLOWED = ("ready", "failed", "expired")

#: An export that can still be downloaded, before its expiry is compared.
DATA_EXPORT_OPEN_STATUSES = ("ready",)

assert set(DATA_EXPORT_STATUSES_ALLOWED) <= set(DATA_EXPORT_STATUSES)
assert set(DATA_EXPORT_OPEN_STATUSES) <= set(DATA_EXPORT_STATUSES_ALLOWED)
assert set(DATA_EXPORT_CATEGORIES) <= set(DATA_CATEGORIES)
