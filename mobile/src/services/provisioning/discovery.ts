/**
 * Turning raw scan results into the list the user chooses from (PRD 2, section 18).
 *
 * Only advertisements carrying the Nura provisioning service UUID count. A
 * device merely *named* "Nura-..." is ignored, so an unrelated gadget can never
 * be listed as a Nura. Raw BLE addresses are kept for connecting but never
 * shown outside developer diagnostics.
 */
import type { ScanResult } from './bleTransport';
import { BLE_NAME_PREFIX, sameUuid, UUIDS } from './protocol';

export interface DiscoveredNura {
  /** Platform peripheral id (MAC on Android, a UUID on iOS). Not shown to users. */
  peripheralId: string;
  /** The four characters shown on the robot's screen, e.g. `1B2C`. */
  shortId: string | null;
  rssi: number;
}

export type SignalStrength = 'strong' | 'nearby' | 'weak';

export function isNuraAdvertisement(result: ScanResult): boolean {
  return result.serviceUuids.some((uuid) => sameUuid(uuid, UUIDS.service));
}

export function shortIdFromName(name: string | null): string | null {
  if (!name?.startsWith(BLE_NAME_PREFIX)) return null;
  const suffix = name.slice(BLE_NAME_PREFIX.length);
  return /^[0-9A-F]{4}$/.test(suffix) ? suffix : null;
}

/** Adds or updates a scan result in the list. Returns the same list if it isn't a Nura. */
export function mergeScanResult(
  list: DiscoveredNura[],
  result: ScanResult
): DiscoveredNura[] {
  if (!isNuraAdvertisement(result)) return list;
  const entry: DiscoveredNura = {
    peripheralId: result.id,
    shortId: shortIdFromName(result.name),
    rssi: result.rssi,
  };
  const others = list.filter((item) => item.peripheralId !== result.id);
  return sortByProximity([...others, { ...entry, shortId: entry.shortId ?? findShortId(list, result.id) }]);
}

function findShortId(list: DiscoveredNura[], id: string): string | null {
  return list.find((item) => item.peripheralId === id)?.shortId ?? null;
}

/** Strongest signal first -- usually the robot right next to the phone. */
export function sortByProximity(list: DiscoveredNura[]): DiscoveredNura[] {
  return [...list].sort((a, b) => b.rssi - a.rssi);
}

export function signalStrength(rssi: number): SignalStrength {
  if (rssi >= -60) return 'strong';
  if (rssi >= -80) return 'nearby';
  return 'weak';
}

export const SIGNAL_LABELS: Record<SignalStrength, string> = {
  strong: 'Strong signal',
  nearby: 'Nearby',
  weak: 'Weak signal',
};
