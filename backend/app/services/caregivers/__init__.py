"""Caregivers, family communication and emergency contacts (PRD 9).

Split the way the responsibilities split, so the authorization decision lives
in exactly one file:

    permissions   who may see what -- the only module that answers that
    invitations   creating an invitation and spending its token
    relationships the primary user's caregiver list: roles, permissions, revoke
    care_view     what a caregiver is shown, deliberately less than the owner
    suggestions   what a caregiver may propose, and what approving it does
    messaging     family messages and quick check-ins
    contacts      the emergency-contact chain, managed and never walked
    calls         the audio-call boundary, with nothing behind it yet
    audit         what was done -- never what was read
    wording       every sentence these features say

Nothing outside this package decides a caregiver permission, and nothing inside
it writes to a health record: a caregiver's only path to a change is a
suggestion the primary user approves.
"""
