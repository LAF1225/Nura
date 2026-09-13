/**
 * "Find my Nura": permission, Bluetooth state, then a time-limited scan
 * (PRD 2, sections 8-9 and 18-19).
 *
 * Kept free of React so every branch -- permission denied, Bluetooth off, no
 * robot found -- is unit-testable.
 */
import type { AdapterState, BleTransport } from './bleTransport';
import { mergeScanResult, type DiscoveredNura } from './discovery';
import type { FlowErrorKind } from './flowErrors';
import type { PermissionOutcome } from './permissions';
import { SCAN_DURATION_SECONDS } from './protocol';

export type DiscoveryState =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'scanning'; devices: DiscoveredNura[] }
  | { status: 'finished'; devices: DiscoveredNura[] }
  | { status: 'blocked'; reason: FlowErrorKind };

export interface DiscoveryDependencies {
  transport: BleTransport;
  requestPermissions: () => Promise<PermissionOutcome>;
  scanSeconds?: number;
}

export function blockedReasonFor(
  permission: PermissionOutcome,
  adapter: AdapterState | null
): FlowErrorKind | null {
  if (permission === 'blocked') return 'permissionBlocked';
  if (permission === 'denied') return 'permissionDenied';
  if (adapter === 'unauthorized') return 'permissionBlocked';
  if (adapter === 'unsupported') return 'bluetoothUnsupported';
  if (adapter === 'off') return 'bluetoothOff';
  return null;
}

/**
 * Runs one discovery attempt, reporting progress through `onUpdate`, and
 * resolves with the final state. Retrying is always a manual action
 * (PRD 2, section 51).
 */
export async function discoverNura(
  deps: DiscoveryDependencies,
  onUpdate: (state: DiscoveryState) => void
): Promise<DiscoveryState> {
  const report = (state: DiscoveryState) => {
    onUpdate(state);
    return state;
  };

  report({ status: 'checking' });

  // Permission first: on Android 12+ even reading the adapter state needs it.
  const permission = await deps.requestPermissions();
  const permissionBlock = blockedReasonFor(permission, null);
  if (permissionBlock) return report({ status: 'blocked', reason: permissionBlock });

  let adapter: AdapterState;
  try {
    adapter = await deps.transport.adapterState();
  } catch {
    adapter = 'unknown';
  }
  const adapterBlock = blockedReasonFor(permission, adapter);
  if (adapterBlock) return report({ status: 'blocked', reason: adapterBlock });

  let devices: DiscoveredNura[] = [];
  report({ status: 'scanning', devices });
  try {
    await deps.transport.scan(deps.scanSeconds ?? SCAN_DURATION_SECONDS, (result) => {
      const next = mergeScanResult(devices, result);
      if (next !== devices) {
        devices = next;
        report({ status: 'scanning', devices });
      }
    });
  } catch {
    // A scan that could not start behaves like Bluetooth being unavailable.
    return report({ status: 'blocked', reason: 'bluetoothOff' });
  }
  return report({ status: 'finished', devices });
}
