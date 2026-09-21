/**
 * Turning a health form into a request, and back (PRD 4, sections 30, 31, 51).
 *
 * These are the decisions the form screen delegates, so this is where the six
 * record types are actually checked: what a new record starts with, what is
 * refused, and -- the one that matters most -- that a date the user only half
 * knows stays half known.
 */
import {
  buildPayload,
  initialValues,
  isValid,
  precisionKey,
  validate,
} from '../src/features/health/form';
import { RECORD_SECTIONS, SECTIONS } from '../src/features/health/sections';
import type { FieldSpec, FormValues } from '../src/features/health/types';

const conditions = SECTIONS.conditions;
const medications = SECTIONS.medications;
const allergies = SECTIONS.allergies;
const clinicians = SECTIONS.clinicians;
const procedures = SECTIONS.procedures;
const notes = SECTIONS.medical_notes;

const diagnosedField = conditions.fields.find(
  (field) => field.key === 'diagnosed_date'
) as FieldSpec;

function withValues(base: FormValues, changes: FormValues): FormValues {
  return { ...base, ...changes };
}

describe('every section is usable', () => {
  it.each(RECORD_SECTIONS)('%s declares exactly one required field', (key) => {
    const required = SECTIONS[key].fields.filter((field) => field.required);
    // Medical notes need a title and a body; everything else needs one name.
    expect(required.length).toBeGreaterThanOrEqual(1);
    expect(required.length).toBeLessThanOrEqual(2);
  });

  it.each(RECORD_SECTIONS)('%s has a spec the form can render', (key) => {
    const spec = SECTIONS[key];
    expect(spec.emptyMessage).not.toMatch(/no data/i);
    expect(spec.fields.length).toBeGreaterThan(0);
    for (const field of spec.fields) {
      if (field.kind === 'choice') {
        expect(field.options?.length ?? 0).toBeGreaterThan(1);
        // A choice always starts somewhere the user did not have to pick.
        expect(field.defaultValue).toBeDefined();
      }
      if (field.kind === 'approximateDate') {
        expect(field.yearKey).toBeDefined();
      }
    }
  });
});

describe('initialValues', () => {
  it('starts a new record from the spec defaults', () => {
    const values = initialValues(conditions);
    expect(values.name).toBe('');
    expect(values.status).toBe('active');
    // Nothing is known about the date, and the form says so rather than
    // preselecting a precision the user did not choose.
    expect(values[precisionKey(diagnosedField)]).toBe('unknown');
  });

  it('defaults a medication to one the user is taking', () => {
    expect(initialValues(medications).is_active).toBe(true);
  });

  it('reads an existing record, including a year-only date', () => {
    const values = initialValues(conditions, {
      id: 'c1',
      profileId: 'p1',
      createdAt: 'x',
      updatedAt: 'x',
      name: 'Asthma',
      status: 'resolved',
      diagnosed_date: null,
      diagnosed_year: 2015,
    });
    expect(values.name).toBe('Asthma');
    expect(values.status).toBe('resolved');
    expect(values.diagnosed_year).toBe('2015');
    expect(values[precisionKey(diagnosedField)]).toBe('year');
  });

  it('reads an exact date as an exact date', () => {
    const values = initialValues(procedures, {
      id: 'p1',
      profileId: 'p1',
      createdAt: 'x',
      updatedAt: 'x',
      name: 'Appendectomy',
      performed_date: '2009-06-01',
      performed_year: null,
    });
    expect(values[precisionKey(procedures.fields[1] as FieldSpec)]).toBe('exact');
    expect(values.performed_date).toBe('2009-06-01');
  });
});

describe('buildPayload', () => {
  it('sends a year as a year, and no date at all', () => {
    const values = withValues(initialValues(conditions), {
      name: 'Asthma',
      diagnosed_year: '2015',
      [precisionKey(diagnosedField)]: 'year',
    });
    const payload = buildPayload(conditions, values);

    expect(payload.diagnosed_year).toBe(2015);
    // The bug PRD 4 section 31 exists to prevent.
    expect(payload.diagnosed_date).toBeNull();
  });

  it('sends nothing at all when the user does not remember', () => {
    const values = withValues(initialValues(conditions), {
      name: 'Asthma',
      diagnosed_year: '2015',
      diagnosed_date: '2015-06-01',
      [precisionKey(diagnosedField)]: 'unknown',
    });
    const payload = buildPayload(conditions, values);
    expect(payload.diagnosed_date).toBeNull();
    expect(payload.diagnosed_year).toBeNull();
  });

  it('clears the year when an exact date is given', () => {
    const values = withValues(initialValues(conditions), {
      name: 'Asthma',
      diagnosed_date: '2015-06-01',
      diagnosed_year: '2015',
      [precisionKey(diagnosedField)]: 'exact',
    });
    const payload = buildPayload(conditions, values);
    expect(payload.diagnosed_date).toBe('2015-06-01');
    expect(payload.diagnosed_year).toBeNull();
  });

  it('turns an emptied field into null rather than an empty string', () => {
    const values = withValues(initialValues(clinicians), {
      name: 'Dr Okafor',
      specialty: '   ',
    });
    expect(buildPayload(clinicians, values).specialty).toBeNull();
  });

  it('trims what the user typed', () => {
    const values = withValues(initialValues(clinicians), { name: '  Dr Okafor  ' });
    expect(buildPayload(clinicians, values).name).toBe('Dr Okafor');
  });

  it('sends every field the section declares, so a clear really clears', () => {
    const payload = buildPayload(medications, initialValues(medications));
    for (const field of medications.fields) {
      expect(payload).toHaveProperty(field.key);
    }
  });

  it('keeps a medication marked as no longer taken', () => {
    const values = withValues(initialValues(medications), {
      name: 'Amoxicillin',
      is_active: false,
    });
    expect(buildPayload(medications, values).is_active).toBe(false);
  });
});

describe('validate', () => {
  it('asks for the one required field, in plain words', () => {
    const errors = validate(conditions, initialValues(conditions));
    expect(errors.name).toBe('Enter a condition.');
    expect(isValid(errors)).toBe(false);
  });

  it.each([
    ['conditions', conditions, 'name'],
    ['medications', medications, 'name'],
    ['allergies', allergies, 'allergen'],
    ['clinicians', clinicians, 'name'],
    ['procedures', procedures, 'name'],
    ['medical_notes', notes, 'title'],
  ])('%s refuses a blank %s', (_label, spec, field) => {
    const errors = validate(spec, withValues(initialValues(spec), { [field]: '   ' }));
    expect(errors[field]).toBeDefined();
  });

  it('accepts a record with only its required field', () => {
    expect(
      isValid(
        validate(conditions, withValues(initialValues(conditions), { name: 'Asthma' }))
      )
    ).toBe(true);
    expect(
      isValid(
        validate(
          notes,
          withValues(initialValues(notes), { title: 'Mobility', body: 'Uses a stick.' })
        )
      )
    ).toBe(true);
  });

  it('refuses a date that is not a date', () => {
    const values = withValues(initialValues(medications), {
      name: 'Salbutamol',
      start_date: 'last tuesday',
    });
    expect(validate(medications, values).start_date).toBe('Use the format YYYY-MM-DD.');
  });

  it('refuses a day that does not exist', () => {
    const values = withValues(initialValues(medications), {
      name: 'Salbutamol',
      start_date: '2026-02-31',
    });
    expect(validate(medications, values).start_date).toBeDefined();
  });

  it('refuses a year that cannot be right, and accepts one that can', () => {
    const base = withValues(initialValues(conditions), {
      name: 'Asthma',
      [precisionKey(diagnosedField)]: 'year',
    });

    expect(
      validate(conditions, withValues(base, { diagnosed_year: '205' })).diagnosed_year
    ).toBeDefined();
    expect(
      validate(conditions, withValues(base, { diagnosed_year: '2199' })).diagnosed_year
    ).toBeDefined();
    expect(
      isValid(validate(conditions, withValues(base, { diagnosed_year: '2015' })))
    ).toBe(true);
  });

  it('does not ask for a date that was never claimed', () => {
    // Precision "unknown" with leftover text in the field must not block a save.
    const values = withValues(initialValues(conditions), {
      name: 'Asthma',
      diagnosed_date: 'nonsense',
      [precisionKey(diagnosedField)]: 'unknown',
    });
    expect(isValid(validate(conditions, values))).toBe(true);
  });

  it('checks an email only when one was given', () => {
    const base = withValues(initialValues(clinicians), { name: 'Dr Okafor' });
    expect(isValid(validate(clinicians, base))).toBe(true);
    expect(validate(clinicians, withValues(base, { email: 'not-an-email' })).email).toBe(
      'Enter a valid email address.'
    );
    expect(
      isValid(validate(clinicians, withValues(base, { email: 'gp@example.test' })))
    ).toBe(true);
  });

  it('leaves optional fields alone', () => {
    const values = withValues(initialValues(allergies), { allergen: 'Penicillin' });
    expect(isValid(validate(allergies, values))).toBe(true);
    // And an allergy the user has not judged stays unknown, never inferred.
    expect(buildPayload(allergies, values).severity).toBe('unknown');
  });
});
