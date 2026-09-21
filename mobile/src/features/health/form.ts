/**
 * Turning a section spec into a form, and a form back into a request
 * (PRD 4, sections 30, 31 and 54).
 *
 * All pure. The form screen holds the values and renders the fields; every
 * decision about what a value *means* -- what a new record starts with, when a
 * field is wrong, what actually gets sent -- is made here, where it can be
 * tested without mounting anything.
 *
 * The interesting part is date precision. A user who knows only the year must
 * be able to say so, so each approximate date carries a third, UI-only value
 * saying which kind of answer they gave (PRD 4, section 31).
 */
import type { FieldSpec, FormValues, HealthRecord, SectionSpec } from './types';

/** How an approximate date was answered. Never sent to the server. */
export type DatePrecision = 'exact' | 'year' | 'unknown';

/** The UI-only key holding the precision for an approximate date field. */
export function precisionKey(field: FieldSpec): string {
  return `${field.key}__precision`;
}

const EARLIEST_YEAR = 1900;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function asString(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return '';
}

/**
 * What the form starts with: an existing record's values, or the spec's
 * defaults for a new one.
 */
export function initialValues(
  spec: SectionSpec,
  record?: HealthRecord | null
): FormValues {
  const values: FormValues = {};

  for (const field of spec.fields) {
    if (field.kind === 'switch') {
      const stored = record?.[field.key];
      values[field.key] =
        typeof stored === 'boolean' ? stored : (field.defaultValue ?? true) === true;
      continue;
    }

    if (field.kind === 'approximateDate') {
      const yearKey = field.yearKey ?? `${field.key}_year`;
      const exact = asString(record?.[field.key]);
      const year = asString(record?.[yearKey]);
      values[field.key] = exact;
      values[yearKey] = year;
      values[precisionKey(field)] = exact ? 'exact' : year ? 'year' : 'unknown';
      continue;
    }

    const stored = record ? asString(record[field.key]) : '';
    values[field.key] =
      stored || (typeof field.defaultValue === 'string' ? field.defaultValue : '');
  }

  return values;
}

/** Trimmed text, or null -- an emptied field means "no value", not `""`. */
function textOrNull(value: unknown): string | null {
  const text = typeof value === 'string' ? value.trim() : '';
  return text.length > 0 ? text : null;
}

/**
 * The request body for these values.
 *
 * Every field the section declares is present, so a PATCH that clears a field
 * genuinely clears it rather than leaving the old value behind.
 */
export function buildPayload(
  spec: SectionSpec,
  values: FormValues
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};

  for (const field of spec.fields) {
    if (field.kind === 'switch') {
      payload[field.key] = values[field.key] === true;
      continue;
    }

    if (field.kind === 'approximateDate') {
      const yearKey = field.yearKey ?? `${field.key}_year`;
      const precision = values[precisionKey(field)];

      if (precision === 'exact') {
        payload[field.key] = textOrNull(values[field.key]);
        payload[yearKey] = null;
      } else if (precision === 'year') {
        const year = textOrNull(values[yearKey]);
        payload[field.key] = null;
        payload[yearKey] = year === null ? null : Number(year);
      } else {
        // "I don't remember" is an answer, and it stays one. Neither field is
        // filled in with a guess (PRD 4, section 31).
        payload[field.key] = null;
        payload[yearKey] = null;
      }
      continue;
    }

    payload[field.key] = textOrNull(values[field.key]);
  }

  return payload;
}

/** Field key -> what is wrong with it. Empty when the form can be sent. */
export type FieldErrors = Record<string, string>;

function validYear(value: string): boolean {
  if (!/^\d{4}$/.test(value)) return false;
  const year = Number(value);
  return year >= EARLIEST_YEAR && year <= new Date().getFullYear();
}

function validDate(value: string): boolean {
  if (!DATE_PATTERN.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return false;
  // Round-trips, so 2026-02-31 is caught rather than rolling into March.
  return (
    value ===
    `${parsed.getFullYear()}-${`${parsed.getMonth() + 1}`.padStart(2, '0')}-${`${parsed.getDate()}`.padStart(2, '0')}`
  );
}

/**
 * What is wrong with this form, in wording that can be shown to someone.
 *
 * Deliberately forgiving. Only a genuinely required field, a date that is not
 * a date, and a year that cannot be right are refused -- a health profile
 * should not argue with the person filling it in (PRD 4, sections 3 and 30).
 */
export function validate(spec: SectionSpec, values: FormValues): FieldErrors {
  const errors: FieldErrors = {};

  for (const field of spec.fields) {
    const raw = values[field.key];
    const text = typeof raw === 'string' ? raw.trim() : '';

    if (field.required && text.length === 0) {
      errors[field.key] = `Enter ${article(field.label)}.`;
      continue;
    }

    if (field.maxLength && text.length > field.maxLength) {
      errors[field.key] = `Keep this under ${field.maxLength} characters.`;
      continue;
    }

    if (field.kind === 'date' && text.length > 0 && !validDate(text)) {
      errors[field.key] = 'Use the format YYYY-MM-DD.';
      continue;
    }

    if (field.kind === 'approximateDate') {
      const yearKey = field.yearKey ?? `${field.key}_year`;
      const precision = values[precisionKey(field)];
      const year = typeof values[yearKey] === 'string' ? values[yearKey].trim() : '';

      if (precision === 'exact' && text.length > 0 && !validDate(text)) {
        errors[field.key] = 'Use the format YYYY-MM-DD.';
      }
      if (precision === 'year' && year.length > 0 && !validYear(year)) {
        errors[yearKey] = `Enter a year between ${EARLIEST_YEAR} and now.`;
      }
      continue;
    }

    if (
      field.keyboardType === 'email-address' &&
      text.length > 0 &&
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)
    ) {
      errors[field.key] = 'Enter a valid email address.';
    }
  }

  return errors;
}

/** "Enter a condition" / "Enter an allergy" -- reads better than "Enter Condition". */
function article(label: string): string {
  const cleaned = label.replace(/\s*\(optional\)$/, '').toLowerCase();
  return /^[aeiou]/.test(cleaned) ? `an ${cleaned}` : `a ${cleaned}`;
}

/** True when nothing is wrong. */
export function isValid(errors: FieldErrors): boolean {
  return Object.keys(errors).length === 0;
}
