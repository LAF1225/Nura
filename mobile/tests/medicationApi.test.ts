/**
 * The medication wire format (PRD 5, sections 51 and 53).
 *
 * The app and the backend have to agree about a dose's status, its window and
 * whether it can be snoozed, because those three decide which buttons a screen
 * offers. A parser that quietly guessed would be a screen offering the wrong
 * action, so every one of them has a checked fallback -- and the fallbacks are
 * chosen to be the *safe* answer rather than the convenient one.
 */
import {
  actionBody,
  parseActionResult,
  parseAdherence,
  parseDose,
  parseSchedule,
  parseSupply,
  parseTodayMedications,
} from '../src/features/medications/api';

const DOSE = {
  id: 'dose-1',
  profile_id: 'profile-1',
  medication_id: 'medication-1',
  medication_name: 'Metformin',
  medication_dose: '500 mg',
  schedule_id: 'schedule-1',
  scheduled_for: '2026-09-13T08:00:00Z',
  local_date: '2026-09-13',
  status: 'scheduled',
  window: 'due',
  action_at: null,
  source: null,
  skip_reason_code: null,
  skip_reason_text: null,
  snoozed_until: null,
  snooze_count: 0,
  late: false,
  can_snooze: true,
};

describe('parseDose', () => {
  it('reads a dose into the shape the screens use', () => {
    expect(parseDose(DOSE, '/doses')).toMatchObject({
      id: 'dose-1',
      medicationName: 'Metformin',
      medicationDose: '500 mg',
      scheduledFor: '2026-09-13T08:00:00Z',
      localDate: '2026-09-13',
      status: 'scheduled',
      window: 'due',
      canSnooze: true,
      syncStatus: 'synced',
    });
  });

  it('keeps a dose whose schedule has been deleted', () => {
    // PRD 5, section 39: the schedule goes, the history stays.
    expect(parseDose({ ...DOSE, schedule_id: null }, '/doses').scheduleId).toBeNull();
  });

  it('never reads an unknown status as something actionable', () => {
    const parsed = parseDose({ ...DOSE, status: 'invented' }, '/doses');
    expect(parsed.status).toBe('scheduled');
  });

  it('never reads an unknown window as "due"', () => {
    // "Upcoming" is the answer that asks least of the user, so it is the one
    // an unrecognised value falls back to.
    expect(parseDose({ ...DOSE, window: 'sometime' }, '/doses').window).toBe('upcoming');
  });

  it('treats a missing can_snooze as "no"', () => {
    const { can_snooze: _dropped, ...without } = DOSE;
    expect(parseDose(without, '/doses').canSnooze).toBe(false);
  });

  it('refuses a body with no id rather than rendering a blank row', () => {
    expect(() => parseDose({ ...DOSE, id: '' }, '/doses')).toThrow();
  });

  it('reads a skip reason back exactly, and drops one it does not know', () => {
    expect(
      parseDose({ ...DOSE, skip_reason_code: 'ran_out' }, '/doses').skipReasonCode
    ).toBe('ran_out');
    expect(
      parseDose({ ...DOSE, skip_reason_code: 'because' }, '/doses').skipReasonCode
    ).toBeNull();
  });

  it('reads the source, so history can say where a confirmation came from', () => {
    expect(parseDose({ ...DOSE, source: 'robot_voice' }, '/doses').source).toBe(
      'robot_voice'
    );
  });
});

describe('parseSchedule', () => {
  const SCHEDULE = {
    id: 'schedule-1',
    profile_id: 'profile-1',
    medication_id: 'medication-1',
    medication_name: 'Metformin',
    medication_dose: '500 mg',
    schedule_type: 'specific_days',
    timezone: 'Europe/London',
    start_date: '2026-09-13',
    end_date: null,
    is_active: true,
    paused_at: null,
    times: [
      { id: 't1', time_of_day: '09:00:00', weekday: 0 },
      { id: 't2', time_of_day: '09:00:00', weekday: 2 },
    ],
  };

  it('keeps the time zone the schedule was made in', () => {
    // The whole daylight-saving policy rests on this travelling with the
    // schedule rather than being assumed from the phone (PRD 5, section 12).
    expect(parseSchedule(SCHEDULE, '/schedules').timezone).toBe('Europe/London');
  });

  it('reads the weekday rows', () => {
    expect(parseSchedule(SCHEDULE, '/schedules').times).toEqual([
      { id: 't1', timeOfDay: '09:00:00', weekday: 0 },
      { id: 't2', timeOfDay: '09:00:00', weekday: 2 },
    ]);
  });

  it('treats a paused schedule as paused', () => {
    const paused = parseSchedule(
      { ...SCHEDULE, is_active: false, paused_at: '2026-09-13T10:00:00Z' },
      '/schedules'
    );
    expect(paused.isActive).toBe(false);
    expect(paused.pausedAt).toBe('2026-09-13T10:00:00Z');
  });
});

describe('parseActionResult', () => {
  it('carries whether anything actually changed', () => {
    const result = parseActionResult(
      { dose: DOSE, applied: false, supply_remaining: 9, low_supply: true },
      '/taken'
    );
    // `applied: false` is how a re-sent action, or a robot agreeing with the
    // person, comes back (PRD 5, sections 48 and 49).
    expect(result.applied).toBe(false);
    expect(result.supplyRemaining).toBe(9);
    expect(result.lowSupply).toBe(true);
  });

  it('treats an absent supply figure as "not tracked"', () => {
    const result = parseActionResult({ dose: DOSE, applied: true }, '/taken');
    expect(result.supplyRemaining).toBeNull();
    expect(result.lowSupply).toBe(false);
  });
});

describe('parseAdherence', () => {
  it('keeps a null percentage null rather than turning it into zero', () => {
    const parsed = parseAdherence(
      {
        from_date: '2026-09-07',
        to_date: '2026-09-13',
        taken: 0,
        skipped: 0,
        missed: 0,
        total: 0,
        percent: null,
      },
      '/adherence'
    );
    // "0%" for a week with nothing scheduled would say something about the
    // person that the data does not (PRD 5, section 27).
    expect(parsed.percent).toBeNull();
    expect(parsed.total).toBe(0);
  });
});

describe('parseSupply', () => {
  it('reads the user’s own numbers', () => {
    expect(
      parseSupply(
        {
          profile_id: 'profile-1',
          medication_id: 'medication-1',
          medication_name: 'Metformin',
          tracking_enabled: true,
          remaining_doses: 4,
          refill_threshold_doses: 5,
          last_refill_date: '2026-08-24',
          low: true,
        },
        '/supply'
      )
    ).toEqual({
      medicationId: 'medication-1',
      medicationName: 'Metformin',
      trackingEnabled: true,
      remainingDoses: 4,
      refillThresholdDoses: 5,
      lastRefillDate: '2026-08-24',
      low: true,
    });
  });

  it('distinguishes "no count" from zero', () => {
    const parsed = parseSupply(
      {
        profile_id: 'profile-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        tracking_enabled: false,
        remaining_doses: null,
        refill_threshold_doses: null,
        last_refill_date: null,
        low: false,
      },
      '/supply'
    );
    expect(parsed.remainingDoses).toBeNull();
  });
});

describe('parseTodayMedications', () => {
  it('reads the block Today carries', () => {
    const parsed = parseTodayMedications({
      next_due: {
        dose_id: 'dose-1',
        medication_id: 'medication-1',
        medication_name: 'Metformin',
        medication_dose: '500 mg',
        scheduled_for: '2026-09-13T08:00:00Z',
        status: 'scheduled',
        window: 'overdue',
        can_snooze: true,
      },
      due_today_count: 3,
      overdue_count: 1,
      remaining_today_count: 2,
      low_supply: [
        {
          medication_id: 'medication-1',
          medication_name: 'Metformin',
          remaining_doses: 4,
        },
      ],
      has_schedules: true,
    });

    expect(parsed?.nextDue?.medicationName).toBe('Metformin');
    expect(parsed?.nextDue?.window).toBe('overdue');
    expect(parsed?.overdueCount).toBe(1);
    expect(parsed?.lowSupply).toHaveLength(1);
    expect(parsed?.hasSchedules).toBe(true);
  });

  it('is null for an account with no profile yet', () => {
    expect(parseTodayMedications(null)).toBeNull();
    expect(parseTodayMedications(undefined)).toBeNull();
  });

  it('says there are no schedules rather than guessing', () => {
    const parsed = parseTodayMedications({
      next_due: null,
      due_today_count: 0,
      overdue_count: 0,
      remaining_today_count: 0,
      low_supply: [],
      has_schedules: false,
    });
    expect(parsed?.hasSchedules).toBe(false);
    expect(parsed?.nextDue).toBeNull();
  });
});

describe('actionBody', () => {
  it('sends only the minutes for a snooze', () => {
    expect(actionBody({ action: 'snooze', minutes: 30 })).toEqual({ minutes: 30 });
  });

  it('sends the reason and the time for a skip', () => {
    expect(
      actionBody({
        action: 'skip',
        reasonCode: 'ran_out',
        reasonText: 'Pharmacy shut',
        actionAt: '2026-09-13T08:05:00Z',
      })
    ).toEqual({
      reason_code: 'ran_out',
      reason_text: 'Pharmacy shut',
      action_at: '2026-09-13T08:05:00Z',
    });
  });

  it('never sends a status or a source', () => {
    // A dose moves by *doing* something to it; how it arrived is the server's
    // own observation (PRD 5, sections 17 and 46).
    for (const body of [
      actionBody({ action: 'taken' }),
      actionBody({ action: 'skip' }),
      actionBody({ action: 'snooze', minutes: 10 }),
    ]) {
      expect(body).not.toHaveProperty('status');
      expect(body).not.toHaveProperty('source');
    }
  });
});
