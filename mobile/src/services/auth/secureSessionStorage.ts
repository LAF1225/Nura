/**
 * Storage adapter that keeps Supabase sessions in the device keychain
 * (PRD 1, sections 15 and 49).
 *
 * Supabase defaults to AsyncStorage, which is plain text on disk. Access and
 * refresh tokens must not live there, so this adapter is handed to the client
 * instead and everything goes through `expo-secure-store`.
 *
 * The wrinkle: SecureStore rejects values larger than 2048 bytes, and a
 * Supabase session (two JWTs plus the user object) routinely exceeds that. So
 * values are split across numbered chunks, with a small index entry recording
 * how many there are. Reads reassemble them; writes always clear the previous
 * chunks first, so shrinking a value cannot leave a stale tail behind.
 */
import * as SecureStore from 'expo-secure-store';

import { createLogger } from '../../utils/logger';

const log = createLogger('secure-session');

/** Comfortably under SecureStore's 2048-byte limit. */
const CHUNK_SIZE = 1500;

/** SecureStore keys allow only alphanumerics, ".", "-" and "_". */
function normaliseKey(key: string): string {
  return key.replace(/[^A-Za-z0-9._-]/g, '_');
}

function chunkKey(key: string, index: number): string {
  return `${normaliseKey(key)}.${index}`;
}

function countKey(key: string): string {
  return `${normaliseKey(key)}.count`;
}

async function readChunkCount(key: string): Promise<number> {
  const raw = await SecureStore.getItemAsync(countKey(key));
  if (raw === null) {
    return 0;
  }
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

async function clearChunks(key: string, count: number): Promise<void> {
  const deletions: Promise<void>[] = [SecureStore.deleteItemAsync(countKey(key))];
  for (let index = 0; index < count; index += 1) {
    deletions.push(SecureStore.deleteItemAsync(chunkKey(key, index)));
  }
  await Promise.all(deletions);
}

/**
 * The shape `@supabase/supabase-js` expects for a custom storage backend.
 * Errors are logged and swallowed rather than thrown: a storage failure should
 * mean "you are signed out", not an app crash.
 */
export const secureSessionStorage = {
  async getItem(key: string): Promise<string | null> {
    try {
      const count = await readChunkCount(key);
      if (count === 0) {
        return null;
      }
      const chunks = await Promise.all(
        Array.from({ length: count }, (_, index) =>
          SecureStore.getItemAsync(chunkKey(key, index))
        )
      );
      if (chunks.some((chunk) => chunk === null)) {
        // A partial write, or storage cleared underneath us. Treat the whole
        // value as absent rather than handing back a corrupt session.
        log.warn('stored session was incomplete; discarding it');
        await clearChunks(key, count);
        return null;
      }
      return chunks.join('');
    } catch (error) {
      log.error('could not read the stored session', { message: String(error) });
      return null;
    }
  },

  async setItem(key: string, value: string): Promise<void> {
    try {
      // Remove the old value first so a shorter one cannot leave stale chunks.
      await clearChunks(key, await readChunkCount(key));

      const chunks: string[] = [];
      for (let offset = 0; offset < value.length; offset += CHUNK_SIZE) {
        chunks.push(value.slice(offset, offset + CHUNK_SIZE));
      }

      await Promise.all(
        chunks.map((chunk, index) =>
          SecureStore.setItemAsync(chunkKey(key, index), chunk)
        )
      );
      await SecureStore.setItemAsync(countKey(key), String(chunks.length));
    } catch (error) {
      // Never log the value itself -- it contains tokens.
      log.error('could not store the session securely', { message: String(error) });
    }
  },

  async removeItem(key: string): Promise<void> {
    try {
      await clearChunks(key, await readChunkCount(key));
    } catch (error) {
      log.error('could not clear the stored session', { message: String(error) });
    }
  },
};
