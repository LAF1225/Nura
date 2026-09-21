/**
 * Form values that could not be saved (PRD 4, sections 36 and 51).
 *
 * The promise: an edit that failed to save is still there when the form is
 * opened again — including after the app has been closed.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { clearDraft, loadDraft, saveDraft } from '../src/features/health/drafts';

beforeEach(async () => {
  await AsyncStorage.clear();
});

it('gives a draft back to the form it came from', async () => {
  await saveDraft('conditions', 'new', { name: 'Asthma', status: 'active' });

  await expect(loadDraft('conditions', 'new')).resolves.toEqual({
    name: 'Asthma',
    status: 'active',
  });
});

it('does not give one form another form’s draft', async () => {
  await saveDraft('conditions', 'new', { name: 'Asthma' });

  await expect(loadDraft('medications', 'new')).resolves.toBeNull();
  await expect(loadDraft('conditions', 'c1')).resolves.toBeNull();
});

it('keeps only the most recent draft', async () => {
  await saveDraft('conditions', 'new', { name: 'Asthma' });
  await saveDraft('allergies', 'new', { allergen: 'Penicillin' });

  // Deliberately one at a time: this is a safety net for the form that is
  // open, not an offline store (PRD 4, section 36).
  await expect(loadDraft('conditions', 'new')).resolves.toBeNull();
  await expect(loadDraft('allergies', 'new')).resolves.toEqual({
    allergen: 'Penicillin',
  });
});

it('clears once the values have been stored properly', async () => {
  await saveDraft('conditions', 'new', { name: 'Asthma' });
  await clearDraft();
  await expect(loadDraft('conditions', 'new')).resolves.toBeNull();
});

it('ignores a corrupted or outdated draft instead of crashing', async () => {
  await AsyncStorage.setItem('nura.health.draft', '{"not":"a draft"}');
  await expect(loadDraft('conditions', 'new')).resolves.toBeNull();

  await AsyncStorage.setItem('nura.health.draft', 'not json at all');
  await expect(loadDraft('conditions', 'new')).resolves.toBeNull();
});
