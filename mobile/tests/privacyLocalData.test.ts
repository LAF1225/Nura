/**
 * What Nura keeps on this phone, and that nothing is forgotten (PRD 13, s39).
 *
 * The second group is the one with teeth. PRD 13 found that sign-out cleared
 * the query cache and nothing on disk, so the inventory in `localData.ts` is
 * new -- and a new hand-written inventory of seventeen keys is exactly the kind
 * of list that goes out of date the first time somebody adds a draft. So the
 * test reads every `'nura…'` storage literal and every persisted store name out
 * of `src/` and requires each one to be classified: cleared, or deliberately
 * kept with a reason.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  ALL_LOCAL_STORES,
  CACHES,
  CONTEXT,
  DRAFTS,
  KEPT_ON_SIGN_OUT,
  NOTIFICATION_MIRRORS,
  PENDING_QUEUES,
  clearLocalData,
  personalStoreCount,
} from '../src/features/privacy/localData';

describe('the inventory', () => {
  it('has no duplicates', () => {
    const keys = ALL_LOCAL_STORES.map((store) => store.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('is the five groups and nothing else', () => {
    // So a group added without being included in `ALL_LOCAL_STORES` -- which
    // would mean it is never cleared -- fails here.
    const grouped =
      PENDING_QUEUES.length +
      CACHES.length +
      NOTIFICATION_MIRRORS.length +
      DRAFTS.length +
      CONTEXT.length;
    expect(ALL_LOCAL_STORES.length).toBe(grouped);
  });

  it('says what each store holds', () => {
    for (const store of ALL_LOCAL_STORES) {
      expect(store.holds.length).toBeGreaterThan(15);
      expect(store.key.length).toBeGreaterThan(0);
    }
  });

  it('counts the personal stores', () => {
    // The notification mirrors are the only non-personal ones, and they are
    // cleared anyway -- a mirror of somebody else's reminders would make the
    // app cancel notifications it no longer understands.
    expect(personalStoreCount()).toBe(
      ALL_LOCAL_STORES.length - NOTIFICATION_MIRRORS.length
    );
  });

  it('keeps the auth tokens out, with a reason', () => {
    // They are cleared by the auth service through secure storage rather than
    // AsyncStorage. Listing them here would mean removing them twice.
    expect(Object.keys(KEPT_ON_SIGN_OUT)).toContain('nura.auth.accessToken');
    expect(Object.keys(KEPT_ON_SIGN_OUT)).toContain('nura.auth.refreshToken');
    for (const reason of Object.values(KEPT_ON_SIGN_OUT)) {
      expect(reason.length).toBeGreaterThan(20);
    }
  });
});

describe('clearing', () => {
  beforeEach(async () => {
    await AsyncStorage.clear();
  });

  it('removes everything in the inventory', async () => {
    for (const store of ALL_LOCAL_STORES) {
      await AsyncStorage.setItem(store.key, JSON.stringify({ from: store.key }));
    }

    const removed = await clearLocalData();
    expect(removed).toBe(ALL_LOCAL_STORES.length);

    for (const store of ALL_LOCAL_STORES) {
      expect(await AsyncStorage.getItem(store.key)).toBeNull();
    }
  });

  it('removes a queued offline action, which is the point', async () => {
    // Named explicitly: before PRD 13, a second person signing in on the same
    // phone inherited the previous one's pending doses and symptom entries.
    await AsyncStorage.setItem(
      'nura.medications.pendingActions',
      JSON.stringify([{ doseId: 'dose-1', action: 'taken' }])
    );
    await AsyncStorage.setItem(
      'nura.symptoms.pendingEntries',
      JSON.stringify([{ clientEntryId: 'entry-1' }])
    );
    await AsyncStorage.setItem(
      'nura-symptom-draft',
      JSON.stringify({ name: 'Headache' })
    );

    await clearLocalData();

    expect(await AsyncStorage.getItem('nura.medications.pendingActions')).toBeNull();
    expect(await AsyncStorage.getItem('nura.symptoms.pendingEntries')).toBeNull();
    expect(await AsyncStorage.getItem('nura-symptom-draft')).toBeNull();
  });

  it('leaves a key it was not asked to clear', async () => {
    // Not `AsyncStorage.clear()`: removing another library's state on sign-out
    // is the kind of fix that works until it breaks something unrelated.
    await AsyncStorage.setItem('some-other-library', 'keep me');
    await clearLocalData();
    expect(await AsyncStorage.getItem('some-other-library')).toBe('keep me');
  });

  it('does not throw when nothing is stored', async () => {
    await expect(clearLocalData()).resolves.toBe(ALL_LOCAL_STORES.length);
  });
});

describe('the inventory cannot rot', () => {
  function sourceFiles(): string[] {
    const found: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) walk(path);
        else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
          found.push(path);
        }
      }
    };
    walk('src');
    return found;
  }

  /**
   * Every storage key and persisted store name declared in `src/`.
   *
   * Two shapes: a `'nura.…'` AsyncStorage key, and a Zustand `persist`
   * configuration's `name: 'nura-…'`. Read with a regex rather than by
   * importing, because importing the feature modules pulls in Expo native
   * code that has no implementation under Jest.
   */
  function declared(): Map<string, string[]> {
    const keys = new Map<string, string[]>();
    const record = (key: string, file: string) => {
      const files = keys.get(key) ?? [];
      files.push(file);
      keys.set(key, files);
    };
    for (const file of sourceFiles()) {
      // The inventory itself declares all of them; skip it so it cannot
      // satisfy its own check.
      if (file.endsWith(join('privacy', 'localData.ts'))) continue;
      const source = readFileSync(file, 'utf8');
      for (const match of source.matchAll(/'(nura\.[A-Za-z0-9._]+)'/g)) {
        const key = match[1];
        if (key !== undefined) record(key, file);
      }
      for (const match of source.matchAll(/name:\s*'(nura-[a-z0-9-]+)'/g)) {
        const key = match[1];
        if (key !== undefined) record(key, file);
      }
    }
    return keys;
  }

  it('finds the keys at all', () => {
    // A guard on the extraction: if these regexes stop matching, every
    // assertion below would pass against an empty map.
    const keys = declared();
    expect(keys.size).toBeGreaterThan(15);
    expect(keys.has('nura.medications.pendingActions')).toBe(true);
    expect(keys.has('nura-symptom-draft')).toBe(true);
  });

  it('every stored key is classified', () => {
    const cleared = new Set(ALL_LOCAL_STORES.map((store) => store.key));
    const kept = new Set(Object.keys(KEPT_ON_SIGN_OUT));

    const unclassified: string[] = [];
    for (const [key, files] of declared()) {
      if (!cleared.has(key) && !kept.has(key)) {
        unclassified.push(`${key} (${files[0]})`);
      }
    }
    expect(unclassified.sort()).toEqual([]);
  });

  it('every inventory key is actually declared somewhere', () => {
    // The other direction. A key left here after its feature was removed is
    // dead weight that makes the inventory harder to trust -- the mistake that
    // made `health-summary` useless in the cache list.
    const found = declared();
    const orphans = ALL_LOCAL_STORES.map((store) => store.key).filter(
      (key) => !found.has(key)
    );
    expect(orphans).toEqual([]);
  });
});
