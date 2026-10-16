/**
 * Safety monitoring, SOS and escalation, as the app sees them (PRD 10).
 *
 * Three shapes in here carry a rule rather than only data.
 *
 * **`capabilities` is the source of truth for what the UI may offer** (section
 * 64). No screen decides for itself whether calling exists; it reads the state
 * the server computed from the providers it actually has. A Call control
 * cannot exist for a call that cannot happen, because the screen never knows
 * enough to draw one.
 *
 * **Every label comes from the server** (section 120). `eventLabel`,
 * `resolutionLabel`, `line` -- all rendered by
 * `services/safety/wording.py`, so the sentences a reviewer has to read live
 * in one file rather than two. The app's own `copy.ts` holds only the text no
 * server response could supply: button labels, screen titles, the confirm
 * dialogs.
 *
 * **`line` on an attempt is the whole display** (section 42). A screen that
 * built its own sentence from `channel` and `status` would be a second place
 * "Ayesha has been contacted" could be written.
 */

export type MonitoringStatus = 'active' | 'ended' | 'cancelled' | 'expired' | 'error';

export type DurationMode =
  '30_minutes' | '1_hour' | 'until_bedtime' | 'until_turned_off' | 'custom';

export type ResponseTimeout = 15 | 30 | 45 | 60 | 90;

export type SafetyEventType =
  | 'manual_sos'
  | 'possible_fall'
  | 'possible_prolonged_immobility'
  | 'possible_vomiting'
  | 'possible_seizure_like_activity'
  | 'possible_distress'
  | 'call_for_help'
  | 'test_event';

export type SafetyEventStatus =
  | 'checking_user'
  | 'second_prompt'
  | 'escalating'
  | 'escalated'
  | 'resolved'
  | 'cancelled';

export type UserResponse = 'im_okay' | 'need_help' | 'false_alarm';

export type EventResolution =
  | 'user_confirmed_ok'
  | 'help_requested'
  | 'no_response_escalated'
  | 'false_alarm'
  | 'cancelled_by_user'
  | 'resolved_after_contact'
  | 'test_event'
  | 'system_error';

export type FalsePositiveReason =
  'normal_movement' | 'sensor_error' | 'user_testing' | 'other';

export type EscalationChannel = 'in_app' | 'push' | 'sms_future' | 'voice_call_future';

export type EscalationAttemptStatus =
  'pending' | 'attempted' | 'delivered' | 'failed' | 'skipped' | 'not_configured';

export type EscalationOutcome =
  | 'complete'
  | 'partial'
  | 'failed'
  | 'no_contacts'
  | 'providers_not_configured'
  | 'cancelled';

export type CapabilityKey =
  | 'manual_sos'
  | 'in_app_safety_checks'
  | 'caregiver_in_app_alerts'
  | 'push_delivery'
  | 'sms_delivery'
  | 'audio_calling'
  | 'robot_detection';

export type CapabilityState =
  'available' | 'not_configured' | 'not_connected' | 'unavailable';

export interface MonitoringSession {
  id: string;
  status: MonitoringStatus;
  startedAt: string;
  endsAt: string | null;
  durationMode: DurationMode;
  timezone: string;
  responseTimeoutSeconds: number;
  secondPromptEnabled: boolean;
  secondPromptTimeoutSeconds: number;
}

export interface Capability {
  key: CapabilityKey;
  state: CapabilityState;
  label: string;
  stateLabel: string;
}

export interface EscalationAttempt {
  id: string;
  recipientLabel: string;
  isCaregiver: boolean;
  priority: number;
  channel: EscalationChannel;
  status: EscalationAttemptStatus;
  failureCode: string | null;
  attemptedAt: string | null;
  /** The sentence to show (section 42). Rendered by the server. */
  line: string;
}

export interface SafetyEvent {
  id: string;
  eventType: SafetyEventType;
  /** Always begins "Possible" for anything a sensor observed (section 16). */
  eventLabel: string;
  triggeredAt: string;
  status: SafetyEventStatus;
  resolution: EventResolution | null;
  resolutionLabel: string | null;
  escalationOutcome: EscalationOutcome | null;
  escalationOutcomeLabel: string | null;
  userResponse: UserResponse | null;
  falsePositive: boolean | null;
}

export interface SafetyEventDetail extends SafetyEvent {
  description: string;
  noResponseSeconds: number | null;
  noResponseLabel: string | null;
  responseDeadlineAt: string | null;
  secondPromptDeadlineAt: string | null;
  escalationStartedAt: string | null;
  resolvedAt: string | null;
  falsePositiveReason: FalsePositiveReason | null;
  attempts: EscalationAttempt[];
  alertCount: number;
}

export interface SafetyStatus {
  monitoring: MonitoringSession | null;
  monitoringSentence: string;
  activeEvent: SafetyEventDetail | null;
  /** Section 43. Derived from the active event on the server, never stored. */
  emergencyMode: boolean;
  capabilities: Capability[];
  emergencyContactCount: number;
  /** Section 73's warning, or null when there is nobody to warn about. */
  noContactsWarning: string | null;
  /** Section 74's warning, or null when some provider exists. */
  noProvidersWarning: string | null;
  /** Section 66's sentence, present whenever nothing is watching. */
  detectionNotice: string | null;
  checkPrompt: string;
}

export interface Capabilities {
  capabilities: Capability[];
  externalDeliveryAvailable: boolean;
  warning: string | null;
}

export interface MonitoringStartInput {
  durationMode: Exclude<DurationMode, 'custom'> | 'custom';
  timezone: string;
  responseTimeoutSeconds: ResponseTimeout;
  secondPromptEnabled: boolean;
  customMinutes?: number;
}

export interface SafetyAlert {
  id: string;
  safetyEventId: string;
  eventType: SafetyEventType;
  eventLabel: string;
  triggeredAt: string;
  createdAt: string;
  readAt: string | null;
  acknowledgedAt: string | null;
  eventStatus: SafetyEventStatus;
  eventResolution: EventResolution | null;
  escalationOutcome: EscalationOutcome | null;
  /** Section 37's sentence, rendered once on the server. */
  sentence: string;
}

export interface SafetyAlertList {
  alerts: SafetyAlert[];
  unreadCount: number;
}
