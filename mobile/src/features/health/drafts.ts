/**
 * Form values that have not been saved yet (PRD 4, section 36).
 *
 * The rule this exists for: **an edit that could not be saved must not
 * silently disappear.** If a save fails, or the app is closed mid-form, the
 * values are still there when the form is opened again.
 *
 * Deliberately not an offline record store. There is one draft at a time, for
 * the form that is open; it is cleared the moment a save succeeds or the user
 * discards it. PRD 4 section 36 rules out building a synchronisation engine
 * for medical records, and this is the small honest version of the promise.
 *
 * Where it lives: AsyncStorage, in the app's private data directory. A draft
 * is medical content, so it never goes anywhere else -- not to a log, not to
 * analytics -- and it is removed as soon as it has been stored properly.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

import { createLogger } from '../../utils/logger';
import type { FormValues } from './types';

const log = createLogger('health');

const STORAGE_KEY = 'nura.health.draft';

export interface HealthDraft {
  section: string;
  /** The record being edited, or `new`. */
  recordId: string;
  values: FormValues;
  savedAt: string;
}

function draftKey(section: string, recordId: string): string {
  return `${section}:${recordId}`;
}

function isDraft(value: unknown): value is HealthDraft {
  if (value === null || typeof value !== 'object') return false;
  const draft = value as Record<string, unknown>;
  return (
    typeof draft.section === 'string' &&
    typeof draft.recordId === 'string' &&
    typeof draft.savedAt === 'string' &&
    draft.values !== null &&
    typeof draft.values === 'object'
  );
}

/** The draft for this form, if the last attempt left one behind. */
export async function loadDraft(
  section: string,
  recordId: string
): Promise<FormValues | null> {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    const parsed: unknown = JSON.parse(stored);
    if (!isDraft(parsed)) return null;
    // One draft at a time: a draft for a different form is not this form's.
    if (draftKey(parsed.section, parsed.recordId) !== draftKey(section, recordId)) {
      return null;
    }
    return parsed.values;
  } catch {
    // A draft that cannot be read is not worth failing the screen over.
    return null;
  }
}

export async function saveDraft(
  section: string,
  recordId: string,
  values: FormValues
): Promise<void> {
  try {
    const draft: HealthDraft = {
      section,
      recordId,
      values,
      savedAt: new Date().toISOString(),
    };
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    // The section, never the values.
    log.info('kept an unsaved health form on this device');
  } catch {
    // Storage being unavailable must not stop the user trying to save again.
  }
}

export async function clearDraft(): Promise<void> {
  try {
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do; the next successful save will overwrite it anyway.
  }
}
