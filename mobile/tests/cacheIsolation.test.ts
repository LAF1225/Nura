/**
 * Switching person or account must not reveal cached data (PRD 13, ss39, 40).
 *
 * Two kinds of test, and the second is the one that matters in a year.
 *
 * `describe('clearing')` checks the behaviour: a switch removes the previous
 * person's cached queries rather than invalidating them, because an
 * invalidated query keeps serving its old value while it refetches -- which is
 * precisely the "stale data flashes from the previous context" PRD 9 section 58
 * forbids and PRD 13 section 40 asks to be tested.
 *
 * `describe('the key list cannot rot')` checks the *list*. PRD 13 found
 * `PROFILE_SCOPED_KEY_PREFIXES` had stopped at PRD 9 while PRD 10 and PRD 12
 * added sixteen profile-scoped keys, so switching left somebody's safety
 * status and task list in the cache. Adding the keys fixes today; reading
 * every `queryKey` literal out of the feature modules and requiring each one
 * to be classified is what stops it happening again at PRD 14.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { QueryClient } from '@tanstack/react-query';

import {
  ACCOUNT_SCOPED_KEY_PREFIXES,
  PROFILE_SCOPED_KEY_PREFIXES,
  clearProfileScopedQueries,
} from '../src/features/caregivers/modeStore';

describe('clearing', () => {
  it('removes a profile-scoped query rather than invalidating it', () => {
    const client = new QueryClient();
    client.setQueryData(['today', 'profile-a'], { summary: 'theirs' });

    clearProfileScopedQueries(client);

    // Removed, so the next render is a loading state. `invalidateQueries`
    // would leave the value in place and refetch underneath it.
    expect(client.getQueryData(['today', 'profile-a'])).toBeUndefined();
  });

  it('keeps the account-level queries the switcher is built from', () => {
    const client = new QueryClient();
    client.setQueryData(['account'], { email: 'someone@example.com' });
    client.setQueryData(['caregiver-profiles'], [{ profileId: 'b' }]);

    clearProfileScopedQueries(client);

    // Dropping these would blank the screen that did the switching.
    expect(client.getQueryData(['account'])).toBeDefined();
    expect(client.getQueryData(['caregiver-profiles'])).toBeDefined();
  });

  it('clears every profile-scoped prefix, not a sample', () => {
    const client = new QueryClient();
    for (const prefix of PROFILE_SCOPED_KEY_PREFIXES) {
      client.setQueryData([prefix, 'profile-a'], { from: prefix });
    }

    clearProfileScopedQueries(client);

    const left = PROFILE_SCOPED_KEY_PREFIXES.filter(
      (prefix) => client.getQueryData([prefix, 'profile-a']) !== undefined
    );
    expect(left).toEqual([]);
  });

  it('clears PRD 10 and PRD 12 keys, which is the gap PRD 13 found', () => {
    // Named explicitly as a regression test. These sixteen were missing, so a
    // caregiver switching from one supported person to another saw the
    // previous person's safety state and task list.
    const client = new QueryClient();
    const missing = [
      'safety-status',
      'safety-capabilities',
      'safety-events',
      'safety-event',
      'safety-alerts',
      'tasks',
      'reminders',
      'reminder-occurrences',
      'alarms',
      'routines',
      'routine',
      'routine-runs',
      'routine-run',
      'daily-life',
      'external-capabilities',
      'care-routines',
    ];
    for (const prefix of missing) {
      client.setQueryData([prefix, 'profile-a'], { from: prefix });
    }

    clearProfileScopedQueries(client);

    for (const prefix of missing) {
      expect(client.getQueryData([prefix, 'profile-a'])).toBeUndefined();
    }
  });

  it('leaves the robot alone, because a robot belongs to an account', () => {
    // PRD 11's keys are scoped by device id. Switching which person is on
    // screen does not change which robot the account claimed, and the
    // documented list says so.
    const client = new QueryClient();
    client.setQueryData(['robot-status', 'device-1'], { mode: 'companion' });

    clearProfileScopedQueries(client);

    expect(client.getQueryData(['robot-status', 'device-1'])).toBeDefined();
    expect(ACCOUNT_SCOPED_KEY_PREFIXES['robot-status']).toContain('device id');
  });
});

describe('the key list cannot rot', () => {
  /** Every file that could declare a query key. */
  function sourceFiles(): string[] {
    const roots = [join('src', 'features'), join('src', 'hooks')];
    const found: string[] = [];
    for (const root of roots) {
      const walk = (dir: string) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
          const path = join(dir, entry.name);
          if (entry.isDirectory()) walk(path);
          else if (entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
            found.push(path);
          }
        }
      };
      walk(root);
    }
    return found;
  }

  /**
   * The first element of every `queryKey` array literal in the source.
   *
   * Read with a regex rather than by importing the modules, because importing
   * them pulls in Expo native modules that have no implementation under Jest.
   * The two shapes that matter are an inline `queryKey: ['x', ...]` and a key
   * builder, `export const xKey = (id: string) => ['x', id] as const`.
   */
  function declaredKeys(): Map<string, string[]> {
    const keys = new Map<string, string[]>();
    const record = (key: string, file: string) => {
      const files = keys.get(key) ?? [];
      files.push(file);
      keys.set(key, files);
    };

    for (const file of sourceFiles()) {
      const source = readFileSync(file, 'utf8');
      const patterns = [
        /queryKey:\s*\[\s*'([a-z][a-z0-9-]*)'/g,
        /(?:export\s+)?const\s+\w*Key\s*=\s*(?:\([^)]*\)\s*=>\s*)?\[\s*'([a-z][a-z0-9-]*)'/g,
      ];
      for (const pattern of patterns) {
        for (const match of source.matchAll(pattern)) {
          const key = match[1];
          if (key !== undefined) record(key, file);
        }
      }
    }
    return keys;
  }

  it('finds the keys at all', () => {
    // A guard on the extraction. If the regexes stop matching, every
    // assertion below would pass against an empty map and prove nothing --
    // the same trap the backend's route walk had.
    const keys = declaredKeys();
    expect(keys.size).toBeGreaterThan(30);
    expect(keys.has('today')).toBe(true);
    expect(keys.has('safety-status')).toBe(true);
    expect(keys.has('tasks')).toBe(true);
  });

  it('every declared key is classified', () => {
    // The load-bearing assertion. A key a later PRD adds is in neither list,
    // and this names it and the file it came from.
    const profile = new Set(PROFILE_SCOPED_KEY_PREFIXES);
    const account = new Set(Object.keys(ACCOUNT_SCOPED_KEY_PREFIXES));

    const unclassified: string[] = [];
    for (const [key, files] of declaredKeys()) {
      if (!profile.has(key) && !account.has(key)) {
        unclassified.push(`${key} (${files[0]})`);
      }
    }
    expect(unclassified.sort()).toEqual([]);
  });

  it('no key is in both lists', () => {
    const account = new Set(Object.keys(ACCOUNT_SCOPED_KEY_PREFIXES));
    const both = PROFILE_SCOPED_KEY_PREFIXES.filter((key) => account.has(key));
    expect(both).toEqual([]);
  });

  it('every account-scoped key has a stated reason', () => {
    // Section 40 is a decision per key, not a bucket to drop things in.
    for (const [key, reason] of Object.entries(ACCOUNT_SCOPED_KEY_PREFIXES)) {
      expect(reason.length).toBeGreaterThan(20);
      expect(key).not.toBe('');
    }
  });

  it('every profile-scoped key is actually declared somewhere', () => {
    // The other direction: a key left in the list after its feature was
    // removed is dead weight that makes the list harder to trust.
    const declared = declaredKeys();
    const orphans = PROFILE_SCOPED_KEY_PREFIXES.filter((key) => !declared.has(key));
    expect(orphans).toEqual([]);
  });
});
