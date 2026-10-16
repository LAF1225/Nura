"""The sentences the Privacy & Security screens say (PRD 13, sections 5-10, 36-38).

One file, for the reason every earlier stage has one: a claim about what Nura
can reach is a truthfulness claim, and a truthfulness claim that exists in two
places eventually disagrees with itself. Three tests read this module whole --
one asserting nothing here promises a capability, one asserting nothing reads
as medical advice, and one asserting every "not configured" sentence names
*this build* rather than the world.

**Nothing in here is a fact of its own.** Every capability sentence is chosen
from a state that came from PRD 10's, PRD 11's or PRD 12's capability map, and
``summary.py`` is what does the choosing. A sentence that hard-coded "your
robot's microphone is off" would be section 6's exact prohibition: claiming a
physical state nobody asked the hardware about.
"""

from __future__ import annotations

# --- the hub ----------------------------------------------------------------

HUB_TITLE = "Privacy & Security"

HUB_INTRO = "What Nura stores, who can see it, and what you can take away or remove."

#: Section 4's sections, as a person reads them. The screen builds its rows
#: from this, so the order on screen and the order here cannot drift.
SECTION_TITLES: dict[str, str] = {
    "privacy_mode": "Privacy Mode",
    "camera_microphone": "Camera & microphone",
    "memory": "What Nura remembers",
    "conversations": "Conversation history",
    "caregivers": "Caregiver access",
    "safety": "Safety Monitoring",
    "robot": "Nura Device privacy",
    "export": "Export your data",
    "deletion": "Delete your data",
    "security": "Security status",
}

SECTION_SUBTITLES: dict[str, str] = {
    "privacy_mode": "Quieter prompts, fewer previews",
    "camera_microphone": "What Nura can and cannot hear or see",
    "memory": "Review, edit and remove what Nura keeps",
    "conversations": "Read, delete one, or delete all",
    "caregivers": "Who can see what, and what they cannot",
    "safety": "What Safety Monitoring can actually do",
    "robot": "What appears on Nura's own screen",
    "export": "A private copy of everything in this profile",
    "deletion": "Remove this profile's data from Nura",
    "security": "How this build protects what you store",
}

# --- privacy mode (section 5) -----------------------------------------------

PRIVACY_MODE_ON = (
    "Privacy Mode is on. Nura will not start conversations, will not suggest "
    "things to remember, and keeps previews short."
)
PRIVACY_MODE_OFF = (
    "Privacy Mode is off. Nura may start a conversation or suggest something to remember."
)

#: Section 5's last line, and the one that keeps the feature honest. Privacy
#: Mode changes what Nura *does*; it cannot switch off hardware that is not
#: connected to anything.
PRIVACY_MODE_LIMIT = (
    "Privacy Mode changes how Nura behaves in the app. It is not a hardware "
    "switch, and it does not claim to turn off a microphone or a camera."
)

# --- camera and microphone (section 6) --------------------------------------

#: Section 6 wants the capability shown truthfully. The strongest truthful
#: sentence available is that no feature in this build listens or watches at
#: all -- which is why the row says what Nura has never asked for rather than
#: what it has turned off.
NO_MICROPHONE_FEATURE = (
    "Nura does not listen. There is no voice input anywhere in the app, so it "
    "has never asked for microphone access."
)
NO_CAMERA_FEATURE = (
    "Nura does not watch. The only camera use is choosing or taking a photo "
    "for a symptom, which happens in your phone's own picker."
)
PHOTO_PERMISSION_NOTE = (
    "Choosing a symptom photo asks your phone for permission at the moment you "
    "choose it, and Nura keeps the photo in private storage."
)

# --- memory and conversations (section 7) -----------------------------------

MEMORY_NOTE = (
    "Nura only remembers what you confirmed. You can read every item, change "
    "one, or remove it."
)
CONVERSATIONS_NOTE = (
    "Deleting conversations does not touch your health record or what Nura "
    "remembers. Those are removed separately."
)
DELETE_ALL_CONVERSATIONS_WARNING = (
    "This removes every conversation with Nura on this profile, including the "
    "messages inside them. What Nura remembers and your health record stay."
)

# --- caregivers (section 8) --------------------------------------------------

CAREGIVER_REVIEW_NOTE = (
    "Each person sees only the categories you granted. Changing or removing "
    "access takes effect immediately."
)
NO_CAREGIVERS = "Nobody else has access to this profile."

# --- deletion (sections 21, 22 and 44) --------------------------------------

DELETION_TITLE = "Delete this profile's data"

DELETION_WARNING = (
    "This cannot be undone. Everything recorded on this profile is removed "
    "from Nura: the health record, medications, symptoms, appointments and "
    "reports, conversations and what Nura remembers, caregivers and their "
    "access, safety history, tasks, reminders, alarms and routines, and every "
    "photo and document stored for it."
)

DELETION_KEEPS = (
    "Your sign-in stays, so you can still open Nura. Any other profile on this "
    "account is untouched. A robot you have paired stays yours and goes back to "
    "being set up for nobody."
)

#: Section 44's documented limitation, said where it applies rather than only
#: in a document. Nura never sees a password -- sign-in is a verified token from
#: the identity provider -- so there is nothing to re-check at this moment.
DELETION_REAUTH_LIMITATION = (
    "Nura cannot ask you for your password again: it never receives one. "
    "Anyone holding this phone while you are signed in can complete this, which "
    "is why it asks you to type the phrase exactly."
)

DELETION_CONFIRM_PROMPT = "Type the phrase below to confirm."

# --- export (sections 17-19) -------------------------------------------------

EXPORT_TITLE = "Export your data"

EXPORT_NOTE = (
    "A single private file holding everything recorded on this profile, plus "
    "your symptom photos and report documents."
)

#: Section 18: temporary, and the screen says so before the request rather
#: than after.
EXPORT_PRIVACY_NOTE = (
    "The file stays private to you and is not emailed anywhere. Nura keeps it "
    "for a day so you can download it, then deletes it."
)

EXPORT_SECRETS_NOTE = (
    "It contains no passwords, sign-in tokens, invitation links or device secrets."
)

EXPORT_READY = "Ready to download"
EXPORT_FAILED = "That export did not finish"
EXPORT_EXPIRED = "Expired — ask for a new one"

EXPORT_STATUS_LABELS: dict[str, str] = {
    "requested": "Requested",
    "generating": "Preparing",
    "ready": EXPORT_READY,
    "failed": EXPORT_FAILED,
    "expired": EXPORT_EXPIRED,
}

# --- security status (section 4) --------------------------------------------

#: Section 4's last row. Statements about how this build behaves, each one
#: true of the code as written and each one checkable -- the security
#: regression suite is what checks them.
SECURITY_STATEMENTS: tuple[str, ...] = (
    "Your sign-in is verified on Nura's server, never trusted from the app.",
    "Every request checks that this profile is yours. An id that is not yours "
    "is simply not found.",
    "A caregiver's access is a separate permission record, checked on every "
    "request. Hiding something in the app is never what protects it.",
    "Photos and documents are served only through an authenticated request. "
    "There are no shareable links to them.",
    "Your records, conversations and notes are never written into Nura's logs.",
    "Connections to Nura's server use HTTPS outside local development.",
)

#: Section 36: the developer status belongs in the docs, not on every screen.
#: This is the one sentence the hub carries, and it is about what has not been
#: tested rather than about what might be broken.
BUILD_HONESTY_NOTE = (
    "Nura has not yet been tested on a physical phone or a physical robot. "
    "Where something has not been verified, the app says so rather than "
    "assuming it works."
)
