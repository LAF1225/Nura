/**
 * The health record, as the app sees it (PRD 4, sections 9-16, 22 and 31).
 *
 * Two shapes are worth reading carefully.
 *
 * `ApproximateDate` is how the app keeps a date the user only half knows.
 * "Diagnosed in 2015" is a year and stays a year; "I don't remember" stays
 * unknown. Nothing is quietly turned into the 1st of January
 * (PRD 4, section 31).
 *
 * `SectionSpec` is what makes six near-identical record screens one screen.
 * Each section declares its fields, its wording and how to summarise a record,
 * and the list and form screens read that rather than being written six times.
 */

export type HealthSection =
  | 'conditions'
  | 'medications'
  | 'allergies'
  | 'clinicians'
  | 'procedures'
  | 'blood_type'
  | 'medical_notes';

/** The six sections that are lists of records. Blood type is a single answer. */
export type RecordSection = Exclude<HealthSection, 'blood_type'>;

export type ConditionStatus = 'active' | 'resolved' | 'historical' | 'uncertain';
export type MedicationForm =
  'tablet' | 'capsule' | 'liquid' | 'injection' | 'inhaler' | 'cream' | 'other';
export type AllergyType = 'medication' | 'food' | 'environmental' | 'other';
export type AllergySeverity = 'mild' | 'moderate' | 'severe' | 'unknown';
export type NoteCategory =
  'general' | 'important' | 'accessibility' | 'care_instruction' | 'other';
export type HealthProfileStatus = 'not_started' | 'in_progress' | 'complete';

export type BloodType =
  | 'A+'
  | 'A-'
  | 'B+'
  | 'B-'
  | 'AB+'
  | 'AB-'
  | 'O+'
  | 'O-'
  | 'unknown'
  | 'prefer_not_to_say';

/**
 * A health record as the app holds it: the fields the server returned, plus
 * the two every record has.
 *
 * Deliberately loose about the rest. The screens are driven by section specs,
 * so a screen never reaches for a field the spec did not declare, and typing
 * every record shape separately would buy nothing the spec does not already
 * give.
 */
export interface HealthRecord {
  id: string;
  profileId: string;
  createdAt: string;
  updatedAt: string;
  [field: string]: string | number | boolean | null | undefined;
}

export interface HealthSectionSummary {
  key: HealthSection;
  title: string;
  count: number;
  complete: boolean;
  updatedAt: string | null;
}

export interface HealthSummary {
  profileId: string;
  status: HealthProfileStatus;
  /** Where setup should resume, or null. */
  step: HealthSection | null;
  bloodType: BloodType | null;
  sections: HealthSectionSummary[];
  completedSections: number;
  totalSections: number;
  /** Equal weight across the sections. Informational only, never a warning. */
  percent: number;
  activeConditions: number;
  activeMedications: number;
}

export interface HealthSetup {
  profileId: string;
  status: HealthProfileStatus;
  step: HealthSection | null;
  bloodType: BloodType | null;
}

// --- form description -------------------------------------------------------

export interface FieldOption {
  value: string;
  label: string;
}

export type FieldKind =
  /** One line of text. */
  | 'text'
  /** Several lines. */
  | 'longtext'
  /** One of a small fixed set. */
  | 'choice'
  /** An exact date, a year, or nothing at all (PRD 4, section 31). */
  | 'approximateDate'
  /** An exact date only, e.g. when a medication was started. */
  | 'date'
  /** A yes/no the user sets, never inferred. */
  | 'switch';

export interface FieldSpec {
  /** Wire field name. For `approximateDate` this is the *date* field. */
  key: string;
  label: string;
  kind: FieldKind;
  /** Only ever set on the one field a record cannot exist without. */
  required?: boolean;
  options?: FieldOption[];
  /** What a new record starts with. Choices and switches always set one. */
  defaultValue?: string | boolean;
  placeholder?: string;
  /** Quiet guidance under the field. */
  hint?: string;
  maxLength?: number;
  /** `approximateDate` only: the companion year field. */
  yearKey?: string;
  keyboardType?: 'default' | 'phone-pad' | 'email-address' | 'numeric';
}

export interface SectionSpec {
  key: RecordSection;
  /** The API path segment, which differs from the key only for notes. */
  path: string;
  /** Plural, as the overview and the list screen title it. */
  title: string;
  /** "condition", for "Add a condition" and "Remove this condition?". */
  singular: string;
  /** Shown when the section is empty. Never "No data". */
  emptyMessage: string;
  /** A sentence explaining what belongs here, shown above an empty list. */
  description: string;
  /** Which field is the row's heading. */
  titleField: string;
  /** The second line of a row, or null for none. */
  subtitle: (record: HealthRecord) => string | null;
  fields: FieldSpec[];
}

/** A form's working values, including the UI-only date precision keys. */
export type FormValues = Record<string, string | boolean | null>;
