/**
 * The robot's display and companion behaviour, as the app sees it (PRD 11).
 *
 * Three shapes in here carry a rule rather than only data.
 *
 * **`capabilities` is the only thing that says what the robot can do**
 * (sections 10 and 47). No screen decides for itself that audio is available;
 * it reads the state the device reported and the booleans the server derived
 * from it. A volume control cannot exist for a speaker that has never been
 * wired, because the screen never knows enough to draw one.
 *
 * **`state` and `reportedState` are both here, and they differ** (section
 * 124). `reportedState` is what the robot said; `state` is what this build is
 * willing to act on. They part company when `stale` is true -- a display
 * proven by a firmware that is no longer running reads as `not_verified` --
 * and a settings screen must use `state`.
 *
 * **`line` on a presentation is the whole display** (section 96). The sentence
 * is rendered by `services/robot/wording.py`, so "sent to Nura" and "shown"
 * cannot come apart in a client that assembled its own. Section 14 is the
 * whole reason those are different words.
 */

export type CapabilityKey =
  | 'display'
  | 'display_text'
  | 'display_animation'
  | 'speaker'
  | 'tts'
  | 'audio_playback'
  | 'microphone'
  | 'wake_word'
  | 'camera'
  | 'camera_detection'
  | 'buttons'
  | 'touch';

/**
 * Section 10's four states, and section 91 makes the third mandatory.
 *
 * `not_verified` means the firmware has the driver and nothing physical has
 * been proven. It is not a promise and it is not a failure, which is why the
 * app never collapses it into a boolean.
 */
export type CapabilityState =
  'available' | 'unavailable' | 'not_verified' | 'not_connected';

export type CapabilitySource = 'device_report' | 'self_test' | 'default';

export interface Capability {
  key: CapabilityKey;
  state: CapabilityState;
  reportedState: CapabilityState;
  label: string;
  stateLabel: string;
  source: CapabilitySource;
  reportedAt: string | null;
  firmwareVersion: string | null;
  stale: boolean;
}

export interface Capabilities {
  deviceId: string;
  capabilities: Capability[];
  /** All derived server-side from the same states (section 47). */
  displayAvailable: boolean;
  textAvailable: boolean;
  animationAvailable: boolean;
  audioAvailable: boolean;
  speechAvailable: boolean;
  inputAvailable: boolean;
  /** Section 135's sentence, written once, on the server. */
  hardwareNote: string;
}

export type MedicationPrivacyLevel = 'full' | 'name_only' | 'private';

export type SleepScreenMode = 'dim' | 'sleeping_face' | 'blank';

export interface PresentationPreferences {
  deviceId: string;
  brightness: number;
  volume: number;
  /** Null means "follow my accessibility setting" (sections 30 and 105). */
  reducedMotion: boolean | null;
  /** What that resolves to right now, computed by the server. */
  effectiveReducedMotion: boolean;
  medicationPrivacyLevel: MedicationPrivacyLevel;
  readMedicationsAloud: boolean;
  readMessagesAloud: boolean;
  readAssistantAloud: boolean;
  sleepScreenMode: SleepScreenMode;
  faceAnimationEnabled: boolean;
  familyMessageDisplayEnabled: boolean;
  updatedAt: string;
}

export interface PresentationPreferencesInput {
  brightness?: number;
  volume?: number;
  /**
   * `null` is a meaningful value and not "leave unchanged": it means go back
   * to following the account's accessibility preference. The client sends it
   * explicitly, which is why this is `boolean | null` rather than optional
   * with undefined doing double duty.
   */
  reducedMotion?: boolean | null;
  medicationPrivacyLevel?: MedicationPrivacyLevel;
  readMedicationsAloud?: boolean;
  readMessagesAloud?: boolean;
  readAssistantAloud?: boolean;
  sleepScreenMode?: SleepScreenMode;
  faceAnimationEnabled?: boolean;
  familyMessageDisplayEnabled?: boolean;
}

export type PresentationType =
  | 'face_state'
  | 'info_card'
  | 'medication_reminder'
  | 'appointment_reminder'
  | 'family_message'
  | 'assistant_response'
  | 'safety_check'
  | 'safety_status'
  | 'emergency_status'
  | 'system_status'
  | 'setup_code';

/**
 * Section 14's statuses.
 *
 * `sent` and `displayed` are different facts: the backend handing a command
 * over is not the robot showing it, and only a device acknowledgement moves a
 * row past `sent`. Nothing in the app may treat them as the same.
 */
export type PresentationStatus =
  | 'queued'
  | 'sent'
  | 'acknowledged'
  | 'displayed'
  | 'completed'
  | 'expired'
  | 'failed'
  | 'cancelled'
  | 'not_supported';

export type PresentationLayout =
  | 'FACE'
  | 'TITLE_BODY'
  | 'TITLE_VALUE'
  | 'REMINDER'
  | 'MESSAGE'
  | 'STATUS'
  | 'EMERGENCY'
  | 'PAIRING_CODE';

export type PresentationSource =
  | 'medication'
  | 'appointment'
  | 'family_message'
  | 'assistant'
  | 'safety'
  | 'system'
  | 'user';

export type AckState =
  'received' | 'render_started' | 'render_completed' | 'failed' | 'unsupported';

export type PresentationMode =
  | 'companion'
  | 'information'
  | 'focus'
  | 'sleep'
  | 'privacy'
  | 'safety'
  | 'emergency'
  | 'offline'
  | 'setup'
  | 'error';

export type FaceState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'happy'
  | 'concerned'
  | 'sleeping'
  | 'privacy'
  | 'offline';

export interface Presentation {
  id: string;
  presentationType: PresentationType;
  status: PresentationStatus;
  layout: PresentationLayout;
  source: PresentationSource;
  priority: number;
  /** From the stored payload, already privacy-filtered (section 22). */
  title: string | null;
  summary: string | null;
  sensitive: boolean;
  createdAt: string;
  availableAt: string;
  expiresAt: string | null;
  sentAt: string | null;
  displayedAt: string | null;
  completedAt: string | null;
  ackState: AckState | null;
  failureCode: string | null;
  cancelReason: string | null;
  /** The rendered sentence for this row's state (section 96). */
  line: string;
}

export interface RobotStatus {
  deviceId: string;
  displayName: string;
  connectionStatus: 'unknown' | 'online' | 'offline';
  lastSeenAt: string | null;
  /** Derived on every read and never stored (section 4). */
  mode: PresentationMode;
  modeLabel: string;
  face: FaceState | null;
  queueDepth: number;
  /**
   * What the robot said it drew. Null in every deployment today, because no
   * physical acknowledgement has ever reached the backend.
   */
  current: Presentation | null;
  setupComplete: boolean;
  /** Section 20's sentence, for a robot that is not online. */
  offlineNote: string | null;
}
