/**
 * The appointment form's draft (PRD 7, sections 8, 42 and 53).
 *
 * Pure functions, so these tests are about the rules rather than the screen:
 * what counts as valid, what a draft becomes on the wire, and what happens to a
 * date and a time on the way there.
 *
 * Two rules are easy to get wrong and are asserted directly:
 *
 *   - **A date in the past is not an error.** People record appointments they
 *     have already been to, and PRD 7 section 41 has a list for them.
 *   - **The client id is generated with the draft, not with the request**, which
 *     is what makes a retry safe (section 53).
 */
import {
  appointmentPatch,
  appointmentPayload,
  draftFrom,
  instantFor,
  isSavable,
  newClientId,
  newDraft,
  timeFromLabel,
  validateDraft,
} from '../src/features/appointments/draft';
import { parseAppointment } from '../src/features/appointments/api';
import type { AppointmentDraft } from '../src/features/appointments/types';
import { appointmentFixture } from './helpers';

function draft(overrides: Partial<AppointmentDraft> = {}): AppointmentDraft {
  return {
    ...newDraft({ now: new Date(2026, 8, 28, 9, 0) }),
    title: 'Cardiology follow-up',
    date: '2026-10-02',
    time: '15:30',
    timezone: 'Europe/London',
    ...overrides,
  };
}

describe('a new draft', () => {
  it('starts with a client id, today, and reminders on', () => {
    const fresh = newDraft({ now: new Date(2026, 8, 28, 9, 0) });

    expect(fresh.clientAppointmentId).toMatch(/^appointment-/);
    expect(fresh.date).toBe('2026-09-28');
    expect(fresh.time).toBe('09:00');
    expect(fresh.remindersEnabled).toBe(true);
    expect(fresh.title).toBe('');
  });

  it('gives every draft its own id', () => {
    expect(newClientId()).not.toBe(newClientId());
    expect(newClientId('question')).toMatch(/^question-/);
  });
});

describe('validation', () => {
  it('needs a name, a date and a time, and nothing else', () => {
    expect(validateDraft(draft())).toEqual({});
    expect(isSavable(draft())).toBe(true);

    // Every optional field empty, and still savable (PRD 7, section 8).
    expect(
      isSavable(
        draft({
          locationName: '',
          address: '',
          phone: '',
          notes: '',
          clinicianId: null,
        })
      )
    ).toBe(true);
  });

  it('asks for a name', () => {
    expect(validateDraft(draft({ title: '   ' })).title).toBeDefined();
    expect(isSavable(draft({ title: '' }))).toBe(false);
  });

  it('refuses a malformed date or time', () => {
    expect(validateDraft(draft({ date: '2 October' })).date).toBeDefined();
    expect(validateDraft(draft({ date: '2026-13-40' })).date).toBeDefined();
    expect(validateDraft(draft({ time: '3:30 PM' })).time).toBeDefined();
    expect(validateDraft(draft({ time: '25:00' })).time).toBeDefined();
  });

  it('accepts a date in the past', () => {
    // Recording a visit already made is normal, and PRD 7 section 41 lists it.
    expect(isSavable(draft({ date: '2020-01-01' }))).toBe(true);
  });

  it('refuses a title longer than the API accepts', () => {
    expect(validateDraft(draft({ title: 'x'.repeat(200) })).title).toBeDefined();
  });
});

describe('the payload', () => {
  it('carries the client id, the zone and the trimmed optional fields', () => {
    const payload = appointmentPayload(
      draft({
        locationName: '  City Hospital  ',
        address: '   ',
        notes: ' Bring the previous scan. ',
      })
    );

    expect(payload.title).toBe('Cardiology follow-up');
    expect(payload.timezone).toBe('Europe/London');
    expect(payload.location_name).toBe('City Hospital');
    // Whitespace is not a value.
    expect(payload.address).toBeNull();
    expect(payload.notes).toBe('Bring the previous scan.');
    expect(payload.client_appointment_id).toMatch(/^appointment-/);
  });

  it('turns the date and time into an instant', () => {
    const payload = appointmentPayload(draft({ date: '2026-10-02', time: '15:30' }));
    const instant = new Date(payload.scheduled_at);

    // The instant is resolved with the device's own offset, so it is compared
    // back the same way rather than against a hard-coded UTC string.
    expect(instant.getTime()).toBe(new Date('2026-10-02T15:30:00').getTime());
  });

  it('falls back to now rather than producing an invalid instant', () => {
    expect(Number.isNaN(Date.parse(instantFor('not a date', '15:30')))).toBe(false);
  });

  it('leaves the client id out of a patch, because it cannot change', () => {
    expect(appointmentPatch(draft())).not.toHaveProperty('client_appointment_id');
    expect(appointmentPatch(draft()).title).toBe('Cardiology follow-up');
  });
});

describe('editing an existing appointment', () => {
  it('fills the draft from the stored labels rather than recomputing them', () => {
    // The server already resolved the date and time in the appointment's own
    // zone; doing it again in JavaScript is what PRD 7 section 42 is easiest to
    // get wrong in.
    const appointment = parseAppointment(appointmentFixture(), '/appointments');
    const filled = draftFrom(appointment);

    expect(filled.date).toBe('2026-10-02');
    expect(filled.time).toBe('15:30');
    expect(filled.timezone).toBe('Europe/London');
    expect(filled.title).toBe('Cardiology follow-up');
    expect(filled.clinicianId).toBe('clinicians-1');
    expect(filled.locationName).toBe('City Hospital');
  });

  it('reads a 12-hour label back to a 24-hour time', () => {
    expect(timeFromLabel('3:30 PM')).toBe('15:30');
    expect(timeFromLabel('9:05 AM')).toBe('09:05');
    expect(timeFromLabel('12:00 AM')).toBe('00:00');
    expect(timeFromLabel('12:15 PM')).toBe('12:15');
    // Anything unparseable falls back rather than producing rubbish.
    expect(timeFromLabel('half past three')).toBe('09:00');
  });
});
