/**
 * What each part of the health record is called, and what it holds
 * (PRD 4, sections 9-16 and 30).
 *
 * These specs are the whole reason there is one list screen and one form
 * screen rather than twelve. They also put all the user-facing wording in one
 * file, which is what keeps six forms feeling like one product instead of six
 * intake questionnaires.
 *
 * Only ever one required field per section. Everything else is optional and
 * labelled as such, because a profile someone fills in gradually is worth more
 * than one they abandon at a question they cannot answer (PRD 4, section 3).
 */
import type { FieldOption, HealthRecord, RecordSection, SectionSpec } from './types';

const CONDITION_STATUSES: FieldOption[] = [
  { value: 'active', label: 'Ongoing' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'historical', label: 'Past' },
  // Kept because "they think it might be" is a real answer, and recording it
  // as ongoing would say more than anyone was told (PRD 4, section 9).
  { value: 'uncertain', label: 'Not confirmed' },
];

const MEDICATION_FORMS: FieldOption[] = [
  // An optional choice needs a way to say nothing, rather than making the
  // first option a silent default the user never picked.
  { value: '', label: 'Not specified' },
  { value: 'tablet', label: 'Tablet' },
  { value: 'capsule', label: 'Capsule' },
  { value: 'liquid', label: 'Liquid' },
  { value: 'injection', label: 'Injection' },
  { value: 'inhaler', label: 'Inhaler' },
  { value: 'cream', label: 'Cream' },
  { value: 'other', label: 'Other' },
];

const ALLERGY_TYPES: FieldOption[] = [
  { value: 'medication', label: 'Medication' },
  { value: 'food', label: 'Food' },
  { value: 'environmental', label: 'Environmental' },
  { value: 'other', label: 'Other' },
];

const ALLERGY_SEVERITIES: FieldOption[] = [
  { value: 'mild', label: 'Mild' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'severe', label: 'Severe' },
  { value: 'unknown', label: 'Not sure' },
];

const NOTE_CATEGORIES: FieldOption[] = [
  { value: 'general', label: 'General' },
  { value: 'important', label: 'Important' },
  { value: 'accessibility', label: 'Accessibility' },
  { value: 'care_instruction', label: 'Care instruction' },
  { value: 'other', label: 'Other' },
];

/** The label a choice value has, for showing a stored value back. */
export function optionLabel(options: FieldOption[], value: unknown): string | null {
  if (typeof value !== 'string') return null;
  return options.find((option) => option.value === value)?.label ?? null;
}

function text(record: HealthRecord, key: string): string | null {
  const value = record[key];
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/** "2015" or "12 March 2015" or null -- whichever precision was recorded. */
export function approximateDateLabel(
  record: HealthRecord,
  dateKey: string,
  yearKey: string
): string | null {
  const exact = text(record, dateKey);
  if (exact) {
    const parsed = new Date(`${exact}T00:00:00`);
    return Number.isNaN(parsed.getTime())
      ? exact
      : parsed.toLocaleDateString(undefined, {
          day: 'numeric',
          month: 'long',
          year: 'numeric',
        });
  }
  const year = record[yearKey];
  return typeof year === 'number' ? String(year) : null;
}

/** Joins the parts of a row's second line, skipping the ones with no value. */
function joined(parts: (string | null)[]): string | null {
  const present = parts.filter((part): part is string => Boolean(part));
  return present.length > 0 ? present.join(' · ') : null;
}

export const SECTIONS: Record<RecordSection, SectionSpec> = {
  conditions: {
    key: 'conditions',
    path: 'conditions',
    title: 'Conditions',
    singular: 'condition',
    emptyMessage: 'No conditions added yet.',
    description:
      'Anything you have been diagnosed with, or told you might have. Add as much or as little as you like.',
    titleField: 'name',
    subtitle: (record) =>
      joined([
        optionLabel(CONDITION_STATUSES, record.status),
        approximateDateLabel(record, 'diagnosed_date', 'diagnosed_year'),
      ]),
    fields: [
      {
        key: 'name',
        label: 'Condition',
        kind: 'text',
        required: true,
        placeholder: 'For example, asthma',
        maxLength: 120,
      },
      {
        key: 'status',
        label: 'Status',
        kind: 'choice',
        options: CONDITION_STATUSES,
        defaultValue: 'active',
      },
      {
        key: 'diagnosed_date',
        yearKey: 'diagnosed_year',
        label: 'When it was diagnosed',
        kind: 'approximateDate',
        hint: 'A year on its own is fine, and so is leaving this out.',
      },
      {
        key: 'diagnosing_clinician',
        label: 'Who diagnosed it (optional)',
        kind: 'text',
        maxLength: 120,
      },
      { key: 'notes', label: 'Notes (optional)', kind: 'longtext', maxLength: 2000 },
    ],
  },

  medications: {
    key: 'medications',
    path: 'medications',
    title: 'Medications',
    singular: 'medication',
    emptyMessage: 'No medications added yet.',
    // PRD 5 added reminders, so the copy points at them instead of ruling
    // them out -- while keeping the boundary clear: this list is the record,
    // and the reminders are in Care (PRD 5, section 30).
    description:
      'What you take, and what you have taken before. Add one here, then set up reminders for it in Care.',
    titleField: 'name',
    footerLink: {
      label: 'Set up reminders',
      route: '/medications/schedules',
      hint: 'Opens medication reminders, where you choose when to be reminded',
    },
    subtitle: (record) =>
      joined([
        joined([text(record, 'dose'), text(record, 'dose_unit')])?.replace(' · ', ' ') ??
          null,
        text(record, 'frequency_text'),
        record.is_active === false ? 'Not taking now' : null,
      ]),
    fields: [
      {
        key: 'name',
        label: 'Medication',
        kind: 'text',
        required: true,
        placeholder: 'For example, salbutamol',
        maxLength: 120,
      },
      { key: 'dose', label: 'Dose (optional)', kind: 'text', maxLength: 50 },
      {
        key: 'dose_unit',
        label: 'Unit (optional)',
        kind: 'text',
        placeholder: 'mg, ml, mcg',
        maxLength: 30,
      },
      {
        key: 'form',
        label: 'Form',
        kind: 'choice',
        options: MEDICATION_FORMS,
        defaultValue: '',
      },
      {
        key: 'frequency_text',
        label: 'How often (optional)',
        kind: 'text',
        placeholder: 'For example, one at night',
        hint: 'In your own words. Nura does not turn this into a schedule.',
        maxLength: 200,
      },
      {
        key: 'instructions',
        label: 'Instructions (optional)',
        kind: 'text',
        maxLength: 200,
      },
      { key: 'reason', label: 'What it is for (optional)', kind: 'text', maxLength: 200 },
      { key: 'start_date', label: 'Started (optional)', kind: 'date' },
      { key: 'end_date', label: 'Stopped (optional)', kind: 'date' },
      {
        key: 'prescribing_clinician',
        label: 'Prescribed by (optional)',
        kind: 'text',
        maxLength: 120,
      },
      {
        key: 'is_active',
        label: 'Currently taking this',
        kind: 'switch',
        defaultValue: true,
        hint: 'Turn this off to keep it as part of your history.',
      },
      { key: 'notes', label: 'Notes (optional)', kind: 'longtext', maxLength: 2000 },
    ],
  },

  allergies: {
    key: 'allergies',
    path: 'allergies',
    title: 'Allergies',
    singular: 'allergy',
    emptyMessage: 'No allergies added yet.',
    description:
      'Anything that causes you a reaction. Nura records what you say and does not work out how serious it is.',
    titleField: 'allergen',
    subtitle: (record) =>
      joined([
        optionLabel(ALLERGY_TYPES, record.allergy_type),
        text(record, 'reaction'),
        record.severity === 'unknown'
          ? null
          : optionLabel(ALLERGY_SEVERITIES, record.severity),
      ]),
    fields: [
      {
        key: 'allergen',
        label: 'Allergic to',
        kind: 'text',
        required: true,
        placeholder: 'For example, penicillin',
        maxLength: 120,
      },
      {
        key: 'allergy_type',
        label: 'Type',
        kind: 'choice',
        options: ALLERGY_TYPES,
        defaultValue: 'other',
      },
      {
        key: 'reaction',
        label: 'What happens (optional)',
        kind: 'text',
        placeholder: 'For example, a rash',
        maxLength: 200,
      },
      {
        key: 'severity',
        label: 'How bad it is',
        kind: 'choice',
        options: ALLERGY_SEVERITIES,
        defaultValue: 'unknown',
        hint: 'Your own judgement. Nura never changes this on its own.',
      },
      { key: 'notes', label: 'Notes (optional)', kind: 'longtext', maxLength: 2000 },
    ],
  },

  clinicians: {
    key: 'clinicians',
    path: 'clinicians',
    title: 'Doctors',
    singular: 'doctor',
    emptyMessage: 'No doctors added yet.',
    description: 'The people who look after your health. Only a name is needed.',
    titleField: 'name',
    subtitle: (record) =>
      joined([text(record, 'specialty'), text(record, 'clinic_name')]),
    fields: [
      {
        key: 'name',
        label: 'Name',
        kind: 'text',
        required: true,
        placeholder: 'For example, Dr Okafor',
        maxLength: 120,
      },
      { key: 'specialty', label: 'Specialty (optional)', kind: 'text', maxLength: 120 },
      { key: 'clinic_name', label: 'Clinic (optional)', kind: 'text', maxLength: 120 },
      {
        key: 'phone',
        label: 'Phone (optional)',
        kind: 'text',
        keyboardType: 'phone-pad',
        maxLength: 40,
      },
      {
        key: 'email',
        label: 'Email (optional)',
        kind: 'text',
        keyboardType: 'email-address',
        maxLength: 320,
      },
      { key: 'address', label: 'Address (optional)', kind: 'text', maxLength: 200 },
      { key: 'notes', label: 'Notes (optional)', kind: 'longtext', maxLength: 2000 },
    ],
  },

  procedures: {
    key: 'procedures',
    path: 'procedures',
    title: 'Surgeries & procedures',
    singular: 'procedure',
    emptyMessage: 'No surgeries or procedures added yet.',
    description:
      'Operations and procedures you have had. An approximate year is perfectly fine.',
    titleField: 'name',
    subtitle: (record) =>
      joined([
        approximateDateLabel(record, 'performed_date', 'performed_year'),
        text(record, 'hospital'),
      ]),
    fields: [
      {
        key: 'name',
        label: 'Procedure',
        kind: 'text',
        required: true,
        placeholder: 'For example, appendectomy',
        maxLength: 120,
      },
      {
        key: 'performed_date',
        yearKey: 'performed_year',
        label: 'When it happened',
        kind: 'approximateDate',
        hint: 'A year on its own is fine, and so is leaving this out.',
      },
      { key: 'hospital', label: 'Hospital (optional)', kind: 'text', maxLength: 120 },
      { key: 'clinician', label: 'Surgeon (optional)', kind: 'text', maxLength: 120 },
      {
        key: 'outcome_notes',
        label: 'How it went (optional)',
        kind: 'longtext',
        maxLength: 2000,
      },
      { key: 'notes', label: 'Notes (optional)', kind: 'longtext', maxLength: 2000 },
    ],
  },

  medical_notes: {
    key: 'medical_notes',
    path: 'medical-notes',
    title: 'Medical notes',
    singular: 'note',
    emptyMessage: 'No notes added yet.',
    description:
      'Anything important that does not fit anywhere else — how you prefer to be cared for, something a clinician told you, a reminder for yourself.',
    titleField: 'title',
    subtitle: (record) => {
      const body = text(record, 'body');
      const category = optionLabel(NOTE_CATEGORIES, record.category);
      const preview = body && body.length > 60 ? `${body.slice(0, 60)}…` : body;
      return joined([category === 'General' ? null : category, preview]);
    },
    fields: [
      {
        key: 'title',
        label: 'Title',
        kind: 'text',
        required: true,
        placeholder: 'For example, mobility',
        maxLength: 120,
      },
      {
        key: 'body',
        label: 'Note',
        kind: 'longtext',
        required: true,
        maxLength: 2000,
      },
      {
        key: 'category',
        label: 'Category',
        kind: 'choice',
        options: NOTE_CATEGORIES,
        defaultValue: 'general',
      },
    ],
  },
};

export const RECORD_SECTIONS: RecordSection[] = [
  'conditions',
  'medications',
  'allergies',
  'clinicians',
  'procedures',
  'medical_notes',
];

/** True for a section key the app has a screen for. */
export function isRecordSection(value: unknown): value is RecordSection {
  return typeof value === 'string' && value in SECTIONS;
}

export const BLOOD_TYPE_OPTIONS: FieldOption[] = [
  { value: 'A+', label: 'A positive' },
  { value: 'A-', label: 'A negative' },
  { value: 'B+', label: 'B positive' },
  { value: 'B-', label: 'B negative' },
  { value: 'AB+', label: 'AB positive' },
  { value: 'AB-', label: 'AB negative' },
  { value: 'O+', label: 'O positive' },
  { value: 'O-', label: 'O negative' },
  // Both are answers rather than the absence of one, so both are offered.
  { value: 'unknown', label: 'I don’t know' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

export function bloodTypeLabel(value: string | null): string | null {
  return value === null ? null : optionLabel(BLOOD_TYPE_OPTIONS, value);
}
