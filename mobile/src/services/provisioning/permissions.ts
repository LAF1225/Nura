/**
 * Bluetooth permission handling (PRD 2, sections 8-9).
 *
 * Asked for only when the user taps "Find my Nura" -- never during sign-up.
 *
 * Android differs by version:
 *
 * | Android              | API    | Runtime permissions requested                 |
 * | -------------------- | ------ | --------------------------------------------- |
 * | 12 and later         | 31+    | BLUETOOTH_SCAN, BLUETOOTH_CONNECT             |
 * | 6 to 11              | 23-30  | ACCESS_FINE_LOCATION (the OS requires it to scan) |
 *
 * On 12+ the manifest marks BLUETOOTH_SCAN `neverForLocation`, so no location
 * permission is requested at all. On 6-11 the location permission is an
 * Android requirement for BLE scanning, not something Nura uses; the device's
 * Location setting must also be on for scan results to arrive.
 *
 * iOS has no runtime request call: CoreBluetooth shows the system prompt the
 * first time the Bluetooth manager starts, and reports `unauthorized` if the
 * user declined.
 */
import { PermissionsAndroid, type Permission } from 'react-native';

export type PermissionOutcome = 'granted' | 'denied' | 'blocked';

export interface PlatformInfo {
  OS: string;
  Version: number | string;
}

export function permissionsFor(platform: PlatformInfo): Permission[] {
  if (platform.OS !== 'android') return [];
  const api = Number(platform.Version);
  if (api >= 31) {
    return [
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN,
      PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT,
    ];
  }
  return [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
}

export async function requestBluetoothPermissions(
  platform: PlatformInfo
): Promise<PermissionOutcome> {
  const needed = permissionsFor(platform);
  if (needed.length === 0) return 'granted';

  const results = await PermissionsAndroid.requestMultiple(needed);
  const values = needed.map((permission) => results[permission]);
  if (values.every((value) => value === PermissionsAndroid.RESULTS.GRANTED)) {
    return 'granted';
  }
  // "Don't ask again": only the system settings can change it now.
  if (values.some((value) => value === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN)) {
    return 'blocked';
  }
  return 'denied';
}
