/**
 * Wires the provisioning flow to the real Bluetooth stack, backend and
 * random number generator. Screens get everything from here.
 *
 * There is one flow at a time: pairing screens hand off to each other, so the
 * connection and verified session must outlive any single screen.
 */
import * as Crypto from 'expo-crypto';
import { Platform } from 'react-native';

import {
  createProvisioningSession,
  fetchDeviceStatus,
  fetchProvisioningSession,
} from '../api/devices';
import { createBleManagerTransport, type BleTransport } from './bleTransport';
import { discoverNura, type DiscoveryState } from './discoverySession';
import { requestBluetoothPermissions } from './permissions';
import { ProvisioningFlow } from './provisioningFlow';

let transport: BleTransport | null = null;
let flow: ProvisioningFlow | null = null;

export function getBleTransport(): BleTransport {
  transport ??= createBleManagerTransport(Platform.OS);
  return transport;
}

export function getProvisioningFlow(): ProvisioningFlow {
  flow ??= new ProvisioningFlow({
    transport: getBleTransport(),
    api: {
      createSession: createProvisioningSession,
      fetchSession: (id) => fetchProvisioningSession(id),
      fetchDeviceStatus: (id) => fetchDeviceStatus(id),
    },
    randomBytes: (length) => Crypto.getRandomBytes(length),
  });
  return flow;
}

export function findNura(onUpdate: (state: DiscoveryState) => void) {
  return discoverNura(
    {
      transport: getBleTransport(),
      requestPermissions: () => requestBluetoothPermissions(Platform),
    },
    onUpdate
  );
}

export type { DiscoveryState } from './discoverySession';
export type { DiscoveredNura } from './discovery';
export type { FlowState, ProgressStep } from './provisioningFlow';
export { FLOW_ERRORS, type FlowErrorKind, type RecoveryAction } from './flowErrors';
