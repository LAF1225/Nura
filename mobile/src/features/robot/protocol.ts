/**
 * The presentation protocol's vocabulary, for the app's side (PRD 11, s116).
 *
 * The app does not speak this protocol -- only the robot and the backend do.
 * It is declared here for the reason PRD 2's `provisioning/protocol.ts` is:
 * `tests/robotPresentationProtocol.test.ts` parses the firmware header and
 * compares it with these values, so adding a layout, a face or an ack state on
 * one side and forgetting another fails on a laptop rather than on a bench
 * with a robot. The backend checks the same agreement from its side in
 * `tests/test_robot_protocol.py`.
 *
 * Keeping it in the app as well as the backend is what makes the check
 * three-way. A preview screen that drew a layout the firmware cannot render
 * would be a preview of something that will never happen (section 95).
 */

/** Bumped when a field changes meaning, not when one is added. */
export const PRESENTATION_PROTOCOL_VERSION = 1;

export const LAYOUTS = [
  'FACE',
  'TITLE_BODY',
  'TITLE_VALUE',
  'REMINDER',
  'MESSAGE',
  'STATUS',
  'EMERGENCY',
  'PAIRING_CODE',
] as const;

export const FACE_STATES = [
  'idle',
  'listening',
  'thinking',
  'speaking',
  'happy',
  'concerned',
  'sleeping',
  'privacy',
  'offline',
] as const;

export const ACK_STATES = [
  'received',
  'render_started',
  'render_completed',
  'failed',
  'unsupported',
] as const;

export const CAPABILITY_KEYS = [
  'display',
  'display_text',
  'display_animation',
  'speaker',
  'tts',
  'audio_playback',
  'microphone',
  'wake_word',
  'camera',
  'camera_detection',
  'buttons',
  'touch',
] as const;

export const CAPABILITY_STATES = [
  'available',
  'unavailable',
  'not_verified',
  'not_connected',
] as const;

/** Section 77's limits. The backend shortens to these before sending. */
export const TEXT_LIMITS = {
  title: 24,
  primary: 32,
  secondary: 48,
  body: 140,
  statusLine: 48,
  maxLines: 5,
  code: 8,
} as const;
