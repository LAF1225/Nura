/**
 * What the privacy layer returns (PRD 13, sections 4-10, 17-22, 43, 44).
 *
 * Capability states are reused from the features that own them rather than
 * redeclared here: a privacy screen describing the robot or the external
 * providers must use the same vocabulary as the Nura Device and daily-life
 * screens, or the two would eventually disagree about what `not_verified`
 * means.
 */

/** Where one export stands. `expired` is derived by the server on every read. */
export type ExportStatus = 'requested' | 'generating' | 'ready' | 'failed' | 'expired';

/** One capability row, from whichever map it came from. */
export interface CapabilityLine {
  key: string;
  label: string;
  /** The machine value, so a row can be styled without parsing the words. */
  state: string;
  /** The words. Never assembled by the client (sections 9 and 10). */
  stateLabel: string;
}

/** One person with access, as the review screen shows them. */
export interface CaregiverAccess {
  relationshipId: string;
  name: string;
  role: string;
  /** The categories the server says they can see. */
  granted: string[];
  acceptedAt: string | null;
}

/** One export. Never carries a storage key (section 18). */
export interface DataExport {
  id: string;
  status: ExportStatus;
  statusLabel: string;
  requestedAt: string;
  generatedAt: string | null;
  expiresAt: string | null;
  byteSize: number | null;
  fileCount: number;
  schemaVersion: number;
  includedCategories: string[];
  excludedCategories: string[];
  failureReason: string | null;
  /** The server's answer, with the expiry already compared. */
  downloadable: boolean;
}

export interface ExportList {
  exports: DataExport[];
  note: string;
  privacyNote: string;
  secretsNote: string;
  /** What the archive would contain, so a screen can say so beforehand. */
  sections: string[];
}

/** Everything the Privacy & Security hub shows, in one read. */
export interface PrivacySummary {
  profileId: string;

  assistantMode: string;
  privacyMode: boolean;
  privacyModeNote: string;
  privacyModeLimit: string;

  microphoneNote: string;
  cameraNote: string;
  photoPermissionNote: string;
  robotInputCapabilities: CapabilityLine[];

  memoryCount: number;
  activeMemoryCount: number;
  conversationCount: number;

  caregivers: CaregiverAccess[];

  safetyMonitoringActive: boolean;
  safetyCapabilities: CapabilityLine[];

  robotLinked: boolean;
  robotCapabilities: CapabilityLine[];
  /** Label and value pairs, read from the robot's own preferences. */
  robotPreviews: [string, string][];

  externalCapabilities: CapabilityLine[];

  latestExport: DataExport | null;
  exportNote: string;
  exportPrivacyNote: string;

  deletionWarning: string;
  deletionKeeps: string;
  deletionReauthLimitation: string;

  dataCategories: string[];
  securityStatements: string[];
  buildHonestyNote: string;
}

/** What a delete would remove, counted before anything is removed. */
export interface DeletionInventory {
  profileId: string;
  profileName: string;
  rows: Record<string, number>;
  rowTotal: number;
  fileCount: number;
  caregiverCount: number;
  deviceCount: number;
  otherProfileCount: number;

  title: string;
  warning: string;
  keeps: string;
  reauthLimitation: string;
  confirmPrompt: string;
  /** What the confirm request must send back, exactly. */
  confirmationPhrase: string;
}

/** What was removed. */
export interface DeletionResult {
  profileId: string;
  rowsDeleted: number;
  filesDeleted: number;
  /** Files the row pointed at and storage did not have. Reported, not hidden. */
  filesMissing: number;
  caregiversRevoked: number;
  devicesUnlinked: number;
  completedAt: string;
  otherProfilesRemaining: number;
}

export interface ConversationsDeleted {
  deleted: number;
  note: string;
}
