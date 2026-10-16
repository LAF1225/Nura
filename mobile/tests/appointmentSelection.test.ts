/**
 * The report selection store (PRD 7, sections 25, 32 and 53).
 *
 * The store is what makes "go back and change it" work across four screens, and
 * what survives the app closing. These tests drive it directly, which is how the
 * rules stay readable:
 *
 *   - **null medication ids mean "the active ones"**, so unticking one has to turn
 *     the implicit list into an explicit one first, or the server would still
 *     include it;
 *   - **attaching a medical note switches its section on**, or a ticked note would
 *     quietly not appear;
 *   - **starting on the same appointment resumes**, and starting on a different one
 *     replaces.
 */
import {
  defaultInclude,
  emptySelection,
  isMedicationSelected,
  selectedSectionCount,
  useReportSelectionStore,
} from '../src/features/appointments/selectionStore';

function store() {
  return useReportSelectionStore.getState();
}

beforeEach(() => {
  useReportSelectionStore.setState({
    appointmentId: null,
    preset: 'since_last_visit',
    customStart: null,
    customEnd: null,
    selection: emptySelection(),
  });
});

describe('the default selection', () => {
  it('has every section on except medical notes', () => {
    const include = defaultInclude();

    expect(include.questions).toBe(true);
    expect(include.medications).toBe(true);
    expect(include.adherence).toBe(true);
    expect(include.daily_checkins).toBe(true);
    expect(include.conditions).toBe(true);
    // Notes are long-form and often about something else entirely.
    expect(include.medical_notes).toBe(false);
  });

  it('matches what the server defaults to, key for key', () => {
    // The backend's `snapshot.default_include` is the other half of this pair.
    expect(Object.keys(defaultInclude()).sort()).toEqual([
      'adherence',
      'allergies',
      'blood_type',
      'conditions',
      'daily_checkins',
      'medical_notes',
      'medications',
      'procedures',
      'questions',
    ]);
  });

  it('starts with no symptoms, no notes and no appendix', () => {
    const selection = emptySelection();
    expect(selection.symptomEpisodeIds).toEqual([]);
    expect(selection.symptomNoteEntryIds).toEqual([]);
    expect(selection.medicationIds).toBeNull();
    expect(selection.includeAppendix).toBe(false);
    expect(selection.includeSkipReasonNotes).toBe(false);
    expect(selection.focus).toBeNull();
  });
});

describe('starting and resuming', () => {
  it('takes the server’s default selection on a first visit', () => {
    store().start('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1', 'episode-2'],
    });

    expect(store().appointmentId).toBe('appointment-1');
    expect(store().selection.symptomEpisodeIds).toEqual(['episode-1', 'episode-2']);
  });

  it('resumes rather than resetting when called again for the same appointment', () => {
    store().start('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1', 'episode-2'],
    });
    store().toggleSymptom('episode-2');
    store().start('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1', 'episode-2'],
    });

    // The user's choice survives, which is what makes Back work (section 32).
    expect(store().selection.symptomEpisodeIds).toEqual(['episode-1']);
  });

  it('replaces the selection when a different appointment is started', () => {
    store().start('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1'],
    });
    store().start('appointment-2', emptySelection());

    expect(store().appointmentId).toBe('appointment-2');
    expect(store().selection.symptomEpisodeIds).toEqual([]);
  });

  it('loads an existing report’s selection so it can be regenerated from it', () => {
    store().load('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-9'],
      includeAppendix: true,
    });

    expect(store().selection.symptomEpisodeIds).toEqual(['episode-9']);
    expect(store().selection.includeAppendix).toBe(true);
  });
});

describe('choosing what goes in', () => {
  beforeEach(() => store().start('appointment-1', emptySelection()));

  it('turns a section on and off', () => {
    expect(store().selection.include.questions).toBe(true);
    store().toggleSection('questions');
    expect(store().selection.include.questions).toBe(false);
    store().toggleSection('questions');
    expect(store().selection.include.questions).toBe(true);
  });

  it('ticks and unticks one symptom at a time', () => {
    store().toggleSymptom('episode-1');
    store().toggleSymptom('episode-2');
    expect(store().selection.symptomEpisodeIds).toEqual(['episode-1', 'episode-2']);

    store().toggleSymptom('episode-1');
    expect(store().selection.symptomEpisodeIds).toEqual(['episode-2']);
  });

  it('replaces the whole symptom list when asked', () => {
    store().setSymptoms(['episode-3', 'episode-4']);
    expect(store().selection.symptomEpisodeIds).toEqual(['episode-3', 'episode-4']);
  });

  it('ticks a symptom note', () => {
    store().toggleSymptomNote('entry-1');
    expect(store().selection.symptomNoteEntryIds).toEqual(['entry-1']);
    store().toggleSymptomNote('entry-1');
    expect(store().selection.symptomNoteEntryIds).toEqual([]);
  });

  it('turns "all active medications" into an explicit list when one is unticked', () => {
    const all = ['medication-1', 'medication-2'];
    expect(store().selection.medicationIds).toBeNull();
    expect(isMedicationSelected(store().selection, 'medication-1')).toBe(true);

    store().toggleMedication('medication-1', all);

    expect(store().selection.medicationIds).toEqual(['medication-2']);
    expect(isMedicationSelected(store().selection, 'medication-1')).toBe(false);
    expect(isMedicationSelected(store().selection, 'medication-2')).toBe(true);
  });

  it('puts an unticked medication back', () => {
    const all = ['medication-1', 'medication-2'];
    store().toggleMedication('medication-1', all);
    store().toggleMedication('medication-1', all);
    expect(store().selection.medicationIds).toEqual(['medication-2', 'medication-1']);
  });

  it('ticks a check-in note by its date', () => {
    store().toggleCheckinNote('2026-09-25');
    expect(store().selection.checkinNoteDates).toEqual(['2026-09-25']);
  });

  it('switches the notes section on when a note is attached', () => {
    expect(store().selection.include.medical_notes).toBe(false);
    store().toggleMedicalNote('note-1');

    expect(store().selection.medicalNoteIds).toEqual(['note-1']);
    // Otherwise a ticked note would quietly not appear in the report.
    expect(store().selection.include.medical_notes).toBe(true);
  });

  it('turns the appendix on and off', () => {
    store().setAppendix(true);
    expect(store().selection.includeAppendix).toBe(true);
    store().setAppendix(false);
    expect(store().selection.includeAppendix).toBe(false);
  });

  it('keeps skip-reason notes off unless asked for', () => {
    expect(store().selection.includeSkipReasonNotes).toBe(false);
    store().setSkipReasonNotes(true);
    expect(store().selection.includeSkipReasonNotes).toBe(true);
  });

  it('treats an empty reason for the visit as no reason', () => {
    store().setFocus('  ');
    expect(store().selection.focus).toBeNull();
    store().setFocus('Headaches since the new tablet');
    expect(store().selection.focus).toBe('Headaches since the new tablet');
  });

  it('counts how many sections are on', () => {
    expect(selectedSectionCount(store().selection)).toBe(8);
    store().toggleSection('questions');
    expect(selectedSectionCount(store().selection)).toBe(7);
  });
});

describe('the period', () => {
  beforeEach(() => store().start('appointment-1', emptySelection()));

  it('starts at "since my last visit", which is PRD 7 section 14’s preference', () => {
    expect(store().preset).toBe('since_last_visit');
  });

  it('remembers a chosen preset', () => {
    store().setPreset('7_days');
    expect(store().preset).toBe('7_days');
  });

  it('a custom range sets the preset with it', () => {
    store().setCustomRange('2026-09-01', '2026-09-28');
    expect(store().preset).toBe('custom');
    expect(store().customStart).toBe('2026-09-01');
    expect(store().customEnd).toBe('2026-09-28');
  });
});

describe('clearing', () => {
  it('leaves nothing behind', () => {
    store().start('appointment-1', {
      ...emptySelection(),
      symptomEpisodeIds: ['episode-1'],
    });
    store().setAppendix(true);
    store().clear();

    expect(store().appointmentId).toBeNull();
    expect(store().selection.symptomEpisodeIds).toEqual([]);
    expect(store().selection.includeAppendix).toBe(false);
    expect(store().preset).toBe('since_last_visit');
  });
});
