/**
 * The Bluetooth boundary (PRD 2, section 10; ADR 0005).
 *
 * `BleTransport` is the only thing provisioning code knows about Bluetooth.
 * The real implementation wraps react-native-ble-manager; tests pass a fake
 * that plays the robot, so the whole flow can be exercised without a radio.
 *
 * Nothing in this file logs characteristic values: they can carry encrypted
 * Wi-Fi details and pairing messages (PRD 2, section 24).
 */
import BleManager, {
  BleScanCallbackType,
  BleScanMatchMode,
  BleScanMode,
  BleState,
  type Peripheral,
} from 'react-native-ble-manager';

import { createLogger } from '../../utils/logger';
import { toByteArray, toNumberArray } from './bytes';
import { MAX_ATTRIBUTE_LENGTH, REQUESTED_MTU, UUIDS } from './protocol';

const log = createLogger('ble');

export type AdapterState = 'on' | 'off' | 'unauthorized' | 'unsupported' | 'unknown';

export interface ScanResult {
  id: string;
  name: string | null;
  rssi: number;
  serviceUuids: string[];
}

export type Unsubscribe = () => void;

export interface BleTransport {
  adapterState(): Promise<AdapterState>;
  /** Android only: asks the user to switch Bluetooth on. */
  requestEnable(): Promise<boolean>;
  scan(seconds: number, onResult: (result: ScanResult) => void): Promise<void>;
  stopScan(): Promise<void>;
  connect(id: string): Promise<void>;
  disconnect(id: string): Promise<void>;
  read(id: string, characteristic: string): Promise<Uint8Array>;
  write(id: string, characteristic: string, value: Uint8Array): Promise<void>;
  subscribe(
    id: string,
    characteristic: string,
    listener: (value: Uint8Array) => void
  ): Promise<Unsubscribe>;
  onDisconnect(id: string, listener: () => void): Unsubscribe;
}

function adapterStateFrom(state: BleState): AdapterState {
  switch (state) {
    case BleState.On:
      return 'on';
    case BleState.Off:
    case BleState.TurningOff:
    case BleState.TurningOn:
      return 'off';
    case BleState.Unauthorized:
      return 'unauthorized';
    case BleState.Unsupported:
      return 'unsupported';
    default:
      return 'unknown';
  }
}

function toScanResult(peripheral: Peripheral): ScanResult {
  return {
    id: peripheral.id,
    name: peripheral.advertising?.localName ?? peripheral.name ?? null,
    rssi: peripheral.rssi,
    serviceUuids: peripheral.advertising?.serviceUUIDs ?? [],
  };
}

/** react-native-ble-manager, which supports React Native's New Architecture. */
export function createBleManagerTransport(platformOS: string): BleTransport {
  let started: Promise<void> | null = null;
  const ensureStarted = () => {
    started ??= BleManager.start({ showAlert: false });
    return started;
  };

  return {
    async adapterState() {
      await ensureStarted();
      return adapterStateFrom(await BleManager.checkState());
    },

    async requestEnable() {
      if (platformOS !== 'android') return false;
      try {
        await BleManager.enableBluetooth();
        return true;
      } catch {
        return false;
      }
    },

    async scan(seconds, onResult) {
      await ensureStarted();
      const discovered = BleManager.onDiscoverPeripheral((peripheral) =>
        onResult(toScanResult(peripheral))
      );
      try {
        await new Promise<void>((resolve, reject) => {
          const stopped = BleManager.onStopScan(() => {
            stopped.remove();
            resolve();
          });
          BleManager.scan({
            // Filtered by the OS as well as re-checked by the caller.
            serviceUUIDs: [UUIDS.service],
            seconds,
            allowDuplicates: false,
            // Foreground discovery the user is waiting on: favour speed.
            scanMode: BleScanMode.LowLatency,
            matchMode: BleScanMatchMode.Aggressive,
            callbackType: BleScanCallbackType.AllMatches,
          }).catch((error: unknown) => {
            stopped.remove();
            reject(error instanceof Error ? error : new Error(String(error)));
          });
        });
      } finally {
        discovered.remove();
      }
    },

    async stopScan() {
      await BleManager.stopScan().catch(() => undefined);
    },

    async connect(id) {
      await ensureStarted();
      await BleManager.connect(id);
      if (platformOS === 'android') {
        // PAKE_RESPONSE is 98 bytes. iOS negotiates a large MTU by itself.
        try {
          await BleManager.requestMTU(id, REQUESTED_MTU);
        } catch {
          log.warn('MTU request was refused');
        }
      }
      await BleManager.retrieveServices(id, [UUIDS.service]);
    },

    async disconnect(id) {
      await BleManager.disconnect(id).catch(() => undefined);
    },

    async read(id, characteristic) {
      return toByteArray(await BleManager.read(id, UUIDS.service, characteristic));
    },

    async write(id, characteristic, value) {
      // maxByteSize must cover the whole message. The library's default of 20
      // splits a value into separate ATT writes, which would break every
      // message boundary in the protocol. One write lets the OS perform a
      // proper long write when the value exceeds the MTU.
      await BleManager.write(
        id,
        UUIDS.service,
        characteristic,
        toNumberArray(value),
        MAX_ATTRIBUTE_LENGTH
      );
    },

    async subscribe(id, characteristic, listener) {
      const subscription = BleManager.onDidUpdateValueForCharacteristic((event) => {
        if (
          event.peripheral === id &&
          event.characteristic.toLowerCase() === characteristic.toLowerCase()
        ) {
          listener(toByteArray(event.value));
        }
      });
      try {
        await BleManager.startNotification(id, UUIDS.service, characteristic);
      } catch (error) {
        subscription.remove();
        throw error;
      }
      return () => subscription.remove();
    },

    onDisconnect(id, listener) {
      const subscription = BleManager.onDisconnectPeripheral((event) => {
        if (event.peripheral === id) listener();
      });
      return () => subscription.remove();
    },
  };
}
