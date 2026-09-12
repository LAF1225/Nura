/**
 * Secure session storage (PRD 1, sections 15 and 49).
 *
 * The reason this adapter exists is that SecureStore rejects values over 2048
 * bytes while a Supabase session is routinely larger, so the chunking is the
 * part worth testing: a long session must survive a round trip, and a shorter
 * one written afterwards must not leave a stale tail behind.
 */
import * as SecureStore from 'expo-secure-store';

import { secureSessionStorage } from '../src/services/auth/secureSessionStorage';

/** In-memory stand-in for the device keychain. */
const store = new Map<string, string>();

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mocked = SecureStore as jest.Mocked<typeof SecureStore>;

beforeEach(() => {
  store.clear();
  mocked.getItemAsync.mockImplementation(async (key: string) => store.get(key) ?? null);
  mocked.setItemAsync.mockImplementation(async (key: string, value: string) => {
    // The real SecureStore refuses oversized values; enforce that here so a
    // regression in chunking shows up as a failure rather than passing.
    if (value.length > 2048) {
      throw new Error('Value too large for SecureStore');
    }
    store.set(key, value);
  });
  mocked.deleteItemAsync.mockImplementation(async (key: string) => {
    store.delete(key);
  });
});

const SESSION_KEY = 'sb-abcdefgh-auth-token';

it('round-trips a session far larger than the SecureStore limit', async () => {
  const session = JSON.stringify({ access_token: 'a'.repeat(5000) });

  await secureSessionStorage.setItem(SESSION_KEY, session);

  expect(await secureSessionStorage.getItem(SESSION_KEY)).toBe(session);
  // Proof it really was split rather than squeezed into one entry.
  expect(store.size).toBeGreaterThan(2);
});

it('returns null for a key that was never written', async () => {
  expect(await secureSessionStorage.getItem('nothing-here')).toBeNull();
});

it('leaves no stale chunks when a shorter value replaces a longer one', async () => {
  await secureSessionStorage.setItem(SESSION_KEY, 'x'.repeat(6000));
  const chunkCount = store.size;

  await secureSessionStorage.setItem(SESSION_KEY, 'short');

  expect(await secureSessionStorage.getItem(SESSION_KEY)).toBe('short');
  expect(store.size).toBeLessThan(chunkCount);
});

it('clears every chunk on removal', async () => {
  await secureSessionStorage.setItem(SESSION_KEY, 'y'.repeat(4000));

  await secureSessionStorage.removeItem(SESSION_KEY);

  expect(store.size).toBe(0);
  expect(await secureSessionStorage.getItem(SESSION_KEY)).toBeNull();
});

it('discards a partially-written value rather than returning a corrupt session', async () => {
  await secureSessionStorage.setItem(SESSION_KEY, 'z'.repeat(4000));
  // Simulate storage losing one chunk underneath us.
  store.delete(`${SESSION_KEY}.1`);

  expect(await secureSessionStorage.getItem(SESSION_KEY)).toBeNull();
  // And it tidies up after itself.
  expect(store.size).toBe(0);
});

it('reports a storage failure as "signed out" instead of throwing', async () => {
  mocked.getItemAsync.mockRejectedValueOnce(new Error('keychain unavailable'));

  await expect(secureSessionStorage.getItem(SESSION_KEY)).resolves.toBeNull();
});

it('sanitises keys that SecureStore would reject', async () => {
  // Supabase keys can contain characters outside SecureStore's allowed set.
  await secureSessionStorage.setItem('sb:weird/key@v1', 'value');

  for (const key of store.keys()) {
    expect(key).toMatch(/^[A-Za-z0-9._-]+$/);
  }
  expect(await secureSessionStorage.getItem('sb:weird/key@v1')).toBe('value');
});
