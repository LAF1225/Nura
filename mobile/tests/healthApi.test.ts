/**
 * The health API layer (PRD 4, sections 26, 32, 33 and 51).
 *
 * What the app sends, what it makes of what comes back, and -- the part worth
 * guarding -- that a record's fields survive the trip even when the parser has
 * never heard of them, because the section spec is what decides which fields a
 * screen reads.
 */
import {
  createRecord,
  deleteRecord,
  fetchRecords,
  parseHealthSetup,
  parseHealthSummary,
  parseRecord,
  updateHealthSetup,
  updateRecord,
} from '../src/features/health/api';
import { SECTIONS } from '../src/features/health/sections';

const PROFILE = 'profile-1';

const SUMMARY = {
  profile_id: PROFILE,
  status: 'in_progress',
  step: 'allergies',
  blood_type: 'O+',
  sections: [
    {
      key: 'conditions',
      title: 'Conditions',
      count: 2,
      complete: true,
      updated_at: '2026-09-21T08:00:00Z',
    },
    {
      key: 'blood_type',
      title: 'Blood type',
      count: 1,
      complete: true,
      updated_at: null,
    },
  ],
  completed_sections: 2,
  total_sections: 7,
  percent: 28,
  active_conditions: 1,
  active_medications: 3,
};

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

interface Call {
  url: string;
  init: RequestInit;
}

const originalFetch = globalThis.fetch;

function stubFetch(body: unknown, status = 200): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return jsonResponse(body, status);
  }) as unknown as typeof fetch;
  return calls;
}

afterEach(() => {
  globalThis.fetch = originalFetch;
});

describe('parseHealthSummary', () => {
  it('maps the wire body onto the overview model', () => {
    const summary = parseHealthSummary(SUMMARY);
    expect(summary.profileId).toBe(PROFILE);
    expect(summary.status).toBe('in_progress');
    expect(summary.step).toBe('allergies');
    expect(summary.bloodType).toBe('O+');
    expect(summary.percent).toBe(28);
    expect(summary.activeConditions).toBe(1);
    expect(summary.activeMedications).toBe(3);
    expect(summary.sections.map((section) => section.key)).toEqual([
      'conditions',
      'blood_type',
    ]);
  });

  it('treats an unrecognised status or blood type as not set', () => {
    const summary = parseHealthSummary({
      ...SUMMARY,
      status: 'nearly',
      blood_type: 'Q+',
      step: 'horoscope',
    });
    expect(summary.status).toBe('not_started');
    expect(summary.bloodType).toBeNull();
    expect(summary.step).toBeNull();
  });

  it('drops a section this build has no screen for', () => {
    const summary = parseHealthSummary({
      ...SUMMARY,
      sections: [
        ...SUMMARY.sections,
        { key: 'astrology', title: 'Astrology', count: 1, complete: true },
      ],
    });
    expect(summary.sections.map((section) => section.key)).not.toContain('astrology');
  });

  it('survives an empty profile', () => {
    const summary = parseHealthSummary({
      profile_id: PROFILE,
      status: 'not_started',
      step: null,
      blood_type: null,
      sections: [],
      completed_sections: 0,
      total_sections: 7,
      percent: 0,
      active_conditions: 0,
      active_medications: 0,
    });
    expect(summary.percent).toBe(0);
    expect(summary.sections).toEqual([]);
  });
});

describe('parseHealthSetup', () => {
  it('maps the setup state', () => {
    const setup = parseHealthSetup({
      profile_id: PROFILE,
      status: 'complete',
      step: null,
      blood_type: 'prefer_not_to_say',
    });
    expect(setup).toEqual({
      profileId: PROFILE,
      status: 'complete',
      step: null,
      bloodType: 'prefer_not_to_say',
    });
  });
});

describe('parseRecord', () => {
  it('keeps every field the server sent, however specific', () => {
    const record = parseRecord(
      {
        id: 'c1',
        profile_id: PROFILE,
        created_at: '2026-09-21T08:00:00Z',
        updated_at: '2026-09-21T08:00:00Z',
        name: 'Asthma',
        status: 'active',
        diagnosed_year: 2015,
        diagnosed_date: null,
        source: 'user',
      },
      '/conditions'
    );

    expect(record.id).toBe('c1');
    expect(record.profileId).toBe(PROFILE);
    // The section spec reads these by name, so they must arrive untouched.
    expect(record.name).toBe('Asthma');
    expect(record.diagnosed_year).toBe(2015);
    expect(record.diagnosed_date).toBeNull();
  });
});

describe('requests', () => {
  it('reads a section from the profile it belongs to', async () => {
    const calls = stubFetch([]);
    await fetchRecords(PROFILE, SECTIONS.medical_notes);
    expect(calls[0]?.url).toContain(`/api/v1/profiles/${PROFILE}/medical-notes`);
  });

  it('creates a record with POST', async () => {
    const calls = stubFetch(
      {
        id: 'c1',
        profile_id: PROFILE,
        created_at: 'x',
        updated_at: 'x',
        name: 'Asthma',
      },
      201
    );

    await createRecord(PROFILE, SECTIONS.conditions, { name: 'Asthma' });
    expect(calls[0]?.init.method).toBe('POST');
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ name: 'Asthma' });
  });

  it('changes a record with PATCH, and never touches the others', async () => {
    const calls = stubFetch({
      id: 'c1',
      profile_id: PROFILE,
      created_at: 'x',
      updated_at: 'x',
      name: 'Eczema',
    });

    await updateRecord(PROFILE, SECTIONS.conditions, 'c1', { name: 'Eczema' });
    expect(calls[0]?.init.method).toBe('PATCH');
    expect(calls[0]?.url).toContain('/conditions/c1');
  });

  it('removes a record with DELETE', async () => {
    const calls = stubFetch(null, 204);
    await deleteRecord(PROFILE, SECTIONS.allergies, 'a1');
    expect(calls[0]?.init.method).toBe('DELETE');
    expect(calls[0]?.url).toContain('/allergies/a1');
  });

  it('sends only the parts of setup that were named', async () => {
    const calls = stubFetch({
      profile_id: PROFILE,
      status: 'in_progress',
      step: null,
      blood_type: 'O+',
    });

    await updateHealthSetup(PROFILE, { bloodType: 'O+' });
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ blood_type: 'O+' });
  });

  it('can clear the resume point with an explicit null', async () => {
    const calls = stubFetch({
      profile_id: PROFILE,
      status: 'complete',
      step: null,
      blood_type: null,
    });

    await updateHealthSetup(PROFILE, { status: 'complete', step: null });
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({
      status: 'complete',
      step: null,
    });
  });

  it('does not send a provenance the server would ignore', async () => {
    // `source` is the server's to set (PRD 4, section 32), so nothing in the
    // app's request layer offers a way to supply one.
    const calls = stubFetch(
      { id: 'c1', profile_id: PROFILE, created_at: 'x', updated_at: 'x', name: 'X' },
      201
    );
    await createRecord(PROFILE, SECTIONS.conditions, { name: 'X' });
    expect(JSON.parse(String(calls[0]?.init.body))).not.toHaveProperty('source');
  });
});
