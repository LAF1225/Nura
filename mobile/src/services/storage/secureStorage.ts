/**
 * Secure storage for sensitive values (PRD 0, section 18).
 *
 * Authentication tokens and anything else secret go here -- backed by the iOS
 * Keychain and Android Keystore -- never into AsyncStorage, which is plain
 * text on disk. AsyncStorage is only for harmless preferences like the theme.
 */
import * as SecureStore from 'expo-secure-store';

import { createLogger } from '../../utils/logger';

const log = createLogger('secure-storage');

/** Keys are centralised so a typo cannot silently orphan a stored value. */
export const SecureStorageKey = {
  accessToken: 'nura.auth.accessToken',
  refreshToken: 'nura.auth.refreshToken',
} as const;

export type SecureStorageKeyName =
  (typeof SecureStorageKey)[keyof typeof SecureStorageKey];

/**
 * Secure storage has no implementation on web. Callers get `null` rather than
 * a crash, so the same code can run in a browser during development.
 */
async function isAvailable(): Promise<boolean> {
  try {
    return await SecureStore.isAvailableAsync();
  } catch {
    return false;
  }
}

export async function getSecureItem(key: SecureStorageKeyName): Promise<string | null> {
  if (!(await isAvailable())) {
    log.warn('secure storage unavailable on this platform; returning null');
    return null;
  }
  try {
    return await SecureStore.getItemAsync(key);
  } catch (error) {
    // Never log the value itself -- only that the read failed.
    log.error('failed to read a secure item', { key });
    throw error;
  }
}

export async function setSecureItem(
  key: SecureStorageKeyName,
  value: string
): Promise<void> {
  if (!(await isAvailable())) {
    log.warn('secure storage unavailable on this platform; value not stored');
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function deleteSecureItem(key: SecureStorageKeyName): Promise<void> {
  if (!(await isAvailable())) {
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

/** Clears every secret Nura holds. Used on sign-out. */
export async function clearSecureStorage(): Promise<void> {
  await Promise.all(Object.values(SecureStorageKey).map((key) => deleteSecureItem(key)));
}
